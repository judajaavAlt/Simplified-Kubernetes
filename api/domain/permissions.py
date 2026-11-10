from enum import Enum

from api.data.models import Role
from api.domain.errors import PermissionDenied


class Action(str, Enum):
    """Operation that requires a permission.

    Attributes:
        PULL: Download templates.
        PUSH: Upload templates and tag them.
        DELETE: Delete manifests and tags.
        ADMINISTER: Manage users and read the audit log.
    """

    PULL = "pull"
    PUSH = "push"
    DELETE = "delete"
    ADMINISTER = "administer"


_ALLOWED = {
    Role.ADMIN: {Action.PULL, Action.PUSH, Action.DELETE, Action.ADMINISTER},
    Role.DEVOPS: {Action.PULL, Action.PUSH, Action.DELETE},
    Role.DEVELOPER: {Action.PULL},
}


def can(role: Role, action: Action) -> bool:
    """Check whether a role allows an action.

    Args:
        role: Role of the user.
        action: Action to perform.

    Returns:
        True if the role allows the action.
    """
    return action in _ALLOWED.get(role, set())


def require(role: Role, action: Action) -> None:
    """Ensure that a role allows an action.

    Args:
        role: Role of the user.
        action: Action to perform.

    Raises:
        PermissionDenied: If the role does not allow the action.
    """
    if not can(role, action):
        raise PermissionDenied(
            f"Role '{role.value}' cannot {action.value}"
        )
