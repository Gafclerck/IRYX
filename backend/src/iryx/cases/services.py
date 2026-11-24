"""IRYX Case Domain Services and Lifecycle Management."""

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from iryx.auth.models import Membership, MembershipRole, Organization
from iryx.cases.models import Case, CaseStatus
from iryx.core.exceptions import (
    CaseNotFoundException,
    InsufficientPermissionsException,
    InvalidStatusTransitionException,
    OrganizationNotFoundException,
    ValidationException,
)

logger = logging.getLogger("iryx.cases.services")

# Immutable state transition matrix (Rule: Strict lifecycle validation)
VALID_STATUS_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.OPEN: {CaseStatus.IN_PROGRESS, CaseStatus.CLOSED},
    CaseStatus.IN_PROGRESS: {CaseStatus.REVIEW, CaseStatus.OPEN, CaseStatus.CLOSED},
    CaseStatus.REVIEW: {CaseStatus.CLOSED, CaseStatus.IN_PROGRESS},
    CaseStatus.CLOSED: set(),
}

OPERATIONAL_ROLES: set[str] = {
    MembershipRole.ADMIN.value,
    MembershipRole.INVESTIGATOR.value,
    MembershipRole.ANALYST.value,
}


class CaseService:
    """Service governing investigation cases lifecycle, permissions, and transitions."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_case(
        self,
        org_id: uuid.UUID,
        title: str,
        description: str | None,
        creator_id: uuid.UUID,
    ) -> Case:
        """Create a new case in the specified organization initialized with 'open' status.

        Raises:
            OrganizationNotFoundException: If the organization does not exist.
            ValidationException: If the title is empty or exceeds 255 chars.
        """
        org = self.db.get(Organization, org_id)
        if org is None:
            raise OrganizationNotFoundException()

        clean_title = title.strip() if title else ""
        if not clean_title:
            raise ValidationException("Le titre du dossier ne peut pas être vide.")
        if len(clean_title) > 255:
            raise ValidationException("Le titre du dossier ne peut pas dépasser 255 caractères.")

        case = Case(
            organization_id=org_id,
            title=clean_title,
            description=description,
            status=CaseStatus.OPEN,
            created_by=creator_id,
        )
        self.db.add(case)
        self.db.commit()
        self.db.refresh(case)

        logger.info(
            "Created case %s in organization %s by user %s",
            case.id,
            org_id,
            creator_id,
            extra={
                "context": {
                    "case_id": str(case.id),
                    "organization_id": str(org_id),
                    "created_by": str(creator_id),
                    "status": str(case.status),
                }
            },
        )
        return case

    def list_cases(
        self,
        org_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Case], int]:
        """List cases belonging to an organization with deterministic pagination."""
        if limit < 1 or limit > 100 or offset < 0:
            raise ValidationException(
                "Les paramètres de pagination sont invalides (1 <= limit <= 100, offset >= 0)."
            )

        count_stmt = select(func.count(Case.id)).where(Case.organization_id == org_id)
        total = self.db.scalar(count_stmt) or 0

        stmt = (
            select(Case)
            .where(Case.organization_id == org_id)
            .order_by(Case.created_at.desc(), Case.id.desc())
            .limit(limit)
            .offset(offset)
        )
        items = list(self.db.scalars(stmt).all())
        return items, total

    def list_user_cases(
        self,
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Case], int]:
        """List all cases across organizations where the user is an active member.

        Enforces multi-tenant isolation via an inner join with Membership on user_id.

        Raises:
            ValidationException: If pagination parameters are invalid
                (limit < 1 or limit > 100 or offset < 0).
        """
        if limit < 1 or limit > 100 or offset < 0:
            raise ValidationException(
                "Les paramètres de pagination sont invalides (1 <= limit <= 100, offset >= 0)."
            )

        count_stmt = (
            select(func.count(Case.id))
            .join(Membership, Case.organization_id == Membership.organization_id)
            .where(Membership.user_id == user_id)
        )
        total = self.db.scalar(count_stmt) or 0

        stmt = (
            select(Case)
            .join(Membership, Case.organization_id == Membership.organization_id)
            .where(Membership.user_id == user_id)
            .order_by(Case.created_at.desc(), Case.id.desc())
            .limit(limit)
            .offset(offset)
        )
        items = list(self.db.scalars(stmt).all())
        return items, total

    def get_case_by_id(
        self,
        case_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> Case:
        """Retrieve a case by ID enforcing organization membership (Zero Leak).

        Raises:
            CaseNotFoundException: If case does not exist.
            InsufficientPermissionsException: If user is not an active member of the org.
        """
        case = self.db.get(Case, case_id)
        if case is None:
            raise CaseNotFoundException()

        if user_id is not None:
            membership = self.db.scalar(
                select(Membership).where(
                    Membership.organization_id == case.organization_id,
                    Membership.user_id == user_id,
                )
            )
            if membership is None:
                raise InsufficientPermissionsException()

        return case

    def update_case_status(
        self,
        case_id: uuid.UUID,
        new_status: CaseStatus | str,
        user_id: uuid.UUID | None = None,
    ) -> Case:
        """Update case status following strict transition rules and RBAC.

        Raises:
            CaseNotFoundException: If case does not exist.
            InsufficientPermissionsException: If user lacks operational role (viewer excluded).
            InvalidStatusTransitionException: If transition is not allowed by the state matrix.
        """
        stmt = select(Case).where(Case.id == case_id).with_for_update()
        case = self.db.scalar(stmt)
        if case is None:
            raise CaseNotFoundException()

        if user_id is not None:
            membership = self.db.scalar(
                select(Membership).where(
                    Membership.organization_id == case.organization_id,
                    Membership.user_id == user_id,
                )
            )
            if membership is None or membership.role not in OPERATIONAL_ROLES:
                raise InsufficientPermissionsException()

        # Normalize target status enum
        target_status: CaseStatus
        if isinstance(new_status, CaseStatus):
            target_status = new_status
        else:
            try:
                target_status = CaseStatus(new_status)
            except ValueError:
                raise InvalidStatusTransitionException(
                    f"Statut cible invalide: '{new_status}'."
                ) from None

        allowed_transitions = VALID_STATUS_TRANSITIONS.get(case.status, set())
        if target_status not in allowed_transitions:
            logger.warning(
                "Invalid status transition attempted for case %s: %s -> %s",
                case.id,
                case.status,
                target_status,
                extra={
                    "context": {
                        "case_id": str(case.id),
                        "current_status": str(case.status),
                        "attempted_status": str(target_status),
                    }
                },
            )
            raise InvalidStatusTransitionException(
                f"Transition non autorisée du statut '{case.status}' vers '{target_status}'."
            )

        old_status = case.status
        case.status = target_status
        self.db.commit()
        self.db.refresh(case)

        logger.info(
            "Case %s status updated from %s to %s by user %s",
            case.id,
            old_status,
            target_status,
            user_id,
            extra={
                "context": {
                    "case_id": str(case.id),
                    "old_status": str(old_status),
                    "new_status": str(target_status),
                    "status": str(target_status),
                    "user_id": str(user_id) if user_id else None,
                }
            },
        )
        return case
