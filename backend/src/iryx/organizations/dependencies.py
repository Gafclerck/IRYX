"""IRYX Organization RBAC and Membership FastAPI Dependencies."""

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from iryx.api.dependencies import get_db
from iryx.auth.dependencies import get_current_user
from iryx.auth.models import Membership, Organization, User
from iryx.core.exceptions import (
    InsufficientPermissionsException,
    OrganizationNotFoundException,
)


def require_role(*allowed_roles: str) -> Callable[..., Membership]:
    """Dependency factory requiring the user to hold one of the specified roles.

    Raises:
        OrganizationNotFoundException (HTTP 404): If the organization does not exist.
        InsufficientPermissionsException (HTTP 403): If user lacks permitted role.
    """

    def dependency(
        org_id: uuid.UUID,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
    ) -> Membership:
        org = db.get(Organization, org_id)
        if org is None:
            raise OrganizationNotFoundException()

        membership = db.execute(
            select(Membership).where(
                Membership.organization_id == org_id,
                Membership.user_id == current_user.id,
            )
        ).scalar_one_or_none()

        if membership is None or (allowed_roles and membership.role not in allowed_roles):
            raise InsufficientPermissionsException()

        return membership

    return dependency


def verify_org_membership(
    org_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Membership:
    """Dependency ensuring the authenticated user is an active member of the specified organization.

    Raises:
        OrganizationNotFoundException (HTTP 404): If the organization does not exist.
        InsufficientPermissionsException (HTTP 403): If the user is not a member.
    """
    org = db.get(Organization, org_id)
    if org is None:
        raise OrganizationNotFoundException()

    membership = db.execute(
        select(Membership).where(
            Membership.organization_id == org_id,
            Membership.user_id == current_user.id,
        )
    ).scalar_one_or_none()

    if membership is None:
        raise InsufficientPermissionsException()

    return membership
