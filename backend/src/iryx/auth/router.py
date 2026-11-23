"""IRYX Authentication API Router."""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from iryx.api.dependencies import get_db
from iryx.auth.dependencies import get_current_user
from iryx.auth.models import User
from iryx.auth.schemas import LoginRequest, TokenResponse, UserResponse
from iryx.auth.services import UserService
from iryx.core.config import get_settings
from iryx.core.security import create_access_token

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authentification utilisateur et émission de jeton JWT",
    description=(
        "Authentifie un utilisateur via email et mot de passe, "
        "et délivre un jeton JWT Bearer valide 3600 secondes."
    ),
)
def login(
    login_data: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    """Authenticate user credentials and return JWT bearer access token."""
    user_service = UserService(db)
    user = user_service.authenticate_user(
        email=login_data.email,
        password=login_data.password,
    )

    settings = get_settings()
    expires_minutes = settings.jwt_access_token_expire_minutes
    expires_seconds = expires_minutes * 60

    payload = {
        "sub": str(user.id),
        "email": user.email,
    }
    access_token = create_access_token(
        data=payload,
        expires_delta=timedelta(minutes=expires_minutes),
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_seconds,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Profil de l'utilisateur connecté",
    description="Retourne les informations du compte utilisateur pour le jeton Bearer fourni.",
)
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Return profile representation of currently authenticated user."""
    return UserResponse.model_validate(current_user)
