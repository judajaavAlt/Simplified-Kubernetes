from fastapi import APIRouter, Depends, status

from api.data.models import User
from api.presentation.dependencies import (
    bearer_token,
    current_user,
    get_services,
)
from api.presentation.schemas import (
    ChangePasswordRequest,
    CreatedUserResponse,
    CreateUserRequest,
    TokenRequest,
    TokenResponse,
)
from api.presentation.services import ApiServices


router = APIRouter(tags=["auth"])


@router.post("/auth/token", response_model=TokenResponse)
def login(
    body: TokenRequest, services: ApiServices = Depends(get_services)
):
    """Exchange credentials for a bearer token.

    Args:
        body: Nickname and password.
        services: Use cases, injected by FastAPI.

    Returns:
        The raw token.
    """
    token = services.authenticate.execute(body.nickname, body.password)
    return TokenResponse(token=token)


@router.delete("/auth/token", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    token: str = Depends(bearer_token),
    services: ApiServices = Depends(get_services),
):
    """Revoke the token used in the request.

    Args:
        token: Raw bearer token.
        services: Use cases, injected by FastAPI.
    """
    services.revoke_token.execute(token)


@router.post("/auth/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordRequest,
    services: ApiServices = Depends(get_services),
):
    """Change a password; the user's tokens are revoked.

    Args:
        body: Nickname, current password and new password.
        services: Use cases, injected by FastAPI.
    """
    services.change_password.execute(
        body.nickname, body.current_password, body.new_password
    )


@router.post(
    "/users",
    response_model=CreatedUserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    body: CreateUserRequest,
    user: User = Depends(current_user),
    services: ApiServices = Depends(get_services),
):
    """Create a user with a temporary password (admin only).

    Args:
        body: Nickname, temporary password and role.
        user: Authenticated user, injected by FastAPI.
        services: Use cases, injected by FastAPI.

    Returns:
        The identifier of the new user.
    """
    user_id = services.create_user.execute(
        user, body.nickname, body.password, body.role
    )
    return CreatedUserResponse(id=user_id)
