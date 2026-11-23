"""IRYX Organization and Membership Domain Services."""

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from iryx.auth.models import Membership, MembershipRole, Organization, User
from iryx.core.exceptions import (
    CannotRemoveLastAdminException,
    MemberAlreadyExistsException,
    MemberNotFoundException,
    OrganizationNotFoundException,
    UserNotFoundException,
    ValidationException,
)

logger = logging.getLogger("iryx.organizations.services")


class OrganizationService:
    """Service managing organizations lifecycle, memberships, and RBAC invariants."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_organization(self, name: str, creator_id: uuid.UUID) -> Organization:
        """Create a new organization and automatically assign the creator as admin.

        Ensures atomic persistence of the organization and initial administrative membership.
        """
        clean_name = name.strip()
        if not clean_name:
            raise ValidationException("Le nom de l'organisation ne peut pas être vide.")

        org = Organization(name=clean_name)
        self.db.add(org)
        self.db.flush()

        admin_membership = Membership(
            organization_id=org.id,
            user_id=creator_id,
            role=MembershipRole.ADMIN.value,
        )
        self.db.add(admin_membership)
        self.db.commit()
        self.db.refresh(org)

        logger.info(
            "Created organization %s with initial admin %s",
            org.id,
            creator_id,
            extra={"context": {"organization_id": str(org.id), "creator_id": str(creator_id)}},
        )
        return org

    def get_organization_by_id(
        self, org_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> Organization:
        """Retrieve an organization by ID with Zero-Leak tenant isolation.

        Raises:
            OrganizationNotFoundException (HTTP 404): If organization does not exist
                or if user_id is provided and the user is not a member.
        """
        org = self.db.get(Organization, org_id)
        if org is None:
            raise OrganizationNotFoundException()

        if user_id is not None:
            membership = self.db.scalar(
                select(Membership).where(
                    Membership.organization_id == org_id,
                    Membership.user_id == user_id,
                )
            )
            if membership is None:
                # Zero Leak principle: non-members must not discover organization existence
                raise OrganizationNotFoundException()

        return org

    def list_user_organizations(
        self, user_id: uuid.UUID, limit: int = 20, offset: int = 0
    ) -> tuple[list[Organization], int]:
        """Return paginated list of organizations where the user has active membership."""
        count_stmt = (
            select(func.count(Organization.id))
            .join(Membership, Membership.organization_id == Organization.id)
            .where(Membership.user_id == user_id)
        )
        total = self.db.scalar(count_stmt) or 0

        stmt = (
            select(Organization)
            .join(Membership, Membership.organization_id == Organization.id)
            .where(Membership.user_id == user_id)
            .order_by(Organization.created_at.desc(), Organization.id.desc())
            .offset(offset)
            .limit(limit)
        )
        items = list(self.db.scalars(stmt).all())
        return items, total

    def list_members(
        self, org_id: uuid.UUID, limit: int = 20, offset: int = 0
    ) -> tuple[list[Membership], int]:
        """Return paginated list of members for an organization."""
        org = self.db.get(Organization, org_id)
        if org is None:
            raise OrganizationNotFoundException()

        count_stmt = select(func.count(Membership.id)).where(
            Membership.organization_id == org_id
        )
        total = self.db.scalar(count_stmt) or 0

        stmt = (
            select(Membership)
            .options(joinedload(Membership.user))
            .where(Membership.organization_id == org_id)
            .order_by(Membership.created_at.asc(), Membership.id.asc())
            .offset(offset)
            .limit(limit)
        )
        items = list(self.db.scalars(stmt).all())
        return items, total

    def add_member(
        self, org_id: uuid.UUID, user_id: uuid.UUID, role: MembershipRole | str
    ) -> Membership:
        """Add an existing active user to an organization with a specified role.

        Raises:
            OrganizationNotFoundException (HTTP 404): If organization does not exist.
            UserNotFoundException (HTTP 404): If user does not exist or is inactive.
            MemberAlreadyExistsException (HTTP 409): If user is already a member.
        """
        org = self.db.get(Organization, org_id)
        if org is None:
            raise OrganizationNotFoundException()

        user = self.db.get(User, user_id)
        if user is None or not user.is_active:
            raise UserNotFoundException()

        existing = self.db.scalar(
            select(Membership).where(
                Membership.organization_id == org_id,
                Membership.user_id == user_id,
            )
        )
        if existing is not None:
            raise MemberAlreadyExistsException()

        role_str = role.value if isinstance(role, MembershipRole) else str(role)
        membership = Membership(
            organization_id=org_id,
            user_id=user_id,
            role=role_str,
        )
        self.db.add(membership)
        try:
            self.db.commit()
            self.db.refresh(membership)
        except IntegrityError as exc:
            self.db.rollback()
            raise MemberAlreadyExistsException() from exc

        # Ensure user relationship is accessible for email serialization
        membership.user = user

        logger.info(
            "Added user %s to organization %s with role %s",
            user_id,
            org_id,
            role_str,
            extra={
                "context": {
                    "organization_id": str(org_id),
                    "user_id": str(user_id),
                    "role": role_str,
                }
            },
        )
        return membership

    def update_member_role(
        self, org_id: uuid.UUID, target_user_id: uuid.UUID, new_role: MembershipRole | str
    ) -> Membership:
        """Update an existing member's role while enforcing last admin safety.

        Raises:
            OrganizationNotFoundException (HTTP 404): If organization does not exist.
            MemberNotFoundException (HTTP 404): If membership does not exist.
            CannotRemoveLastAdminException (HTTP 400): If demoting the last active administrator.
        """
        org = self.db.get(Organization, org_id)
        if org is None:
            raise OrganizationNotFoundException()

        membership = self.db.scalar(
            select(Membership)
            .options(joinedload(Membership.user))
            .where(
                Membership.organization_id == org_id,
                Membership.user_id == target_user_id,
            )
        )
        if membership is None:
            raise MemberNotFoundException()

        new_role_str = new_role.value if isinstance(new_role, MembershipRole) else str(new_role)

        # Invariant: Never demote the last active admin
        is_current_admin = membership.role == MembershipRole.ADMIN.value
        is_demotion = new_role_str != MembershipRole.ADMIN.value
        if is_current_admin and is_demotion:
            admin_count = (
                self.db.scalar(
                    select(func.count(Membership.id))
                    .join(User, Membership.user_id == User.id)
                    .where(
                        Membership.organization_id == org_id,
                        Membership.role == MembershipRole.ADMIN.value,
                        User.is_active.is_(True),
                    )
                )
                or 0
            )
            if admin_count <= 1:
                raise CannotRemoveLastAdminException()

        membership.role = new_role_str
        self.db.commit()
        self.db.refresh(membership)

        logger.info(
            "Updated role for user %s in organization %s to %s",
            target_user_id,
            org_id,
            new_role_str,
            extra={
                "context": {
                    "organization_id": str(org_id),
                    "user_id": str(target_user_id),
                    "role": new_role_str,
                }
            },
        )
        return membership

    def remove_member(self, org_id: uuid.UUID, target_user_id: uuid.UUID) -> None:
        """Remove a member from an organization while enforcing last admin safety.

        Raises:
            OrganizationNotFoundException (HTTP 404): If organization does not exist.
            MemberNotFoundException (HTTP 404): If membership does not exist.
            CannotRemoveLastAdminException (HTTP 400): If removing the last active administrator.
        """
        org = self.db.get(Organization, org_id)
        if org is None:
            raise OrganizationNotFoundException()

        membership = self.db.scalar(
            select(Membership).where(
                Membership.organization_id == org_id,
                Membership.user_id == target_user_id,
            )
        )
        if membership is None:
            raise MemberNotFoundException()

        # Invariant: Never delete the last active admin
        if membership.role == MembershipRole.ADMIN.value:
            admin_count = (
                self.db.scalar(
                    select(func.count(Membership.id))
                    .join(User, Membership.user_id == User.id)
                    .where(
                        Membership.organization_id == org_id,
                        Membership.role == MembershipRole.ADMIN.value,
                        User.is_active.is_(True),
                    )
                )
                or 0
            )
            if admin_count <= 1:
                raise CannotRemoveLastAdminException()

        self.db.delete(membership)
        self.db.commit()

        logger.info(
            "Removed user %s from organization %s",
            target_user_id,
            org_id,
            extra={
                "context": {
                    "organization_id": str(org_id),
                    "user_id": str(target_user_id),
                }
            },
        )
