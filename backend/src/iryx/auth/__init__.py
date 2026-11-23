"""IRYX Authentication and Identity Management Module."""

from iryx.auth.dependencies import get_current_user
from iryx.auth.models import Membership, MembershipRole, Organization, User
from iryx.auth.router import router
from iryx.auth.schemas import (
    LoginRequest,
    MembershipCreate,
    MembershipResponse,
    OrganizationCreate,
    OrganizationResponse,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from iryx.auth.services import (
    UserService,
    authenticate_user,
    create_user,
    get_user_by_email,
    get_user_by_id,
)

__all__ = [
    "LoginRequest",
    "Membership",
    "MembershipCreate",
    "MembershipResponse",
    "MembershipRole",
    "Organization",
    "OrganizationCreate",
    "OrganizationResponse",
    "TokenResponse",
    "User",
    "UserCreate",
    "UserResponse",
    "UserService",
    "authenticate_user",
    "create_user",
    "get_current_user",
    "get_user_by_email",
    "get_user_by_id",
    "router",
]
