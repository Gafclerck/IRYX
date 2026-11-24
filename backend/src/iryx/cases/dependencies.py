"""FastAPI security and RBAC dependencies for Cases domain."""

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from iryx.api.dependencies import get_db
from iryx.auth.dependencies import get_current_user
from iryx.auth.models import Membership, MembershipRole, User
from iryx.cases.models import Case
from iryx.core.exceptions import (
    CaseNotFoundException,
    InsufficientPermissionsException,
)


def verify_case_access(
    case_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Case:
    """Dependency verifying that the authenticated user belongs to the organization owning the case.

    Raises:
        CaseNotFoundException (HTTP 404): If the case does not exist.
        InsufficientPermissionsException (HTTP 403): If the user is not a member
            of the case's organization.
    """
    case = db.get(Case, case_id)
    if case is None:
        raise CaseNotFoundException()

    membership = db.scalar(
        select(Membership).where(
            Membership.organization_id == case.organization_id,
            Membership.user_id == current_user.id,
        )
    )
    if membership is None:
        raise InsufficientPermissionsException(message="Accès refusé à ce dossier.")

    return case


def require_case_role(
    *allowed_roles: str | MembershipRole,
) -> Callable[..., Case]:
    """Dependency factory requiring the user to hold one of the specified roles
    within the case's organization.

    Raises:
        CaseNotFoundException (HTTP 404): If the case does not exist.
        InsufficientPermissionsException (HTTP 403): If user lacks membership or permitted role.
    """
    normalized_roles = {
        r.value.lower() if isinstance(r, MembershipRole) else str(r).lower()
        for r in allowed_roles
    }

    def dependency(
        case_id: uuid.UUID,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
    ) -> Case:
        case = db.get(Case, case_id)
        if case is None:
            raise CaseNotFoundException()

        membership = db.scalar(
            select(Membership).where(
                Membership.organization_id == case.organization_id,
                Membership.user_id == current_user.id,
            )
        )
        if membership is None or (
            normalized_roles and str(membership.role).lower() not in normalized_roles
        ):
            raise InsufficientPermissionsException(message="Accès refusé à ce dossier.")

        return case

    return dependency
