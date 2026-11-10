import hashlib

import pytest

from api.application.auth.authenticate_user import AuthenticateUser
from api.application.auth.bootstrap_admin import BootstrapAdmin
from api.application.auth.change_password import ChangePassword
from api.application.auth.create_user import CreateUser
from api.application.auth.revoke_token import RevokeToken
from api.application.auth.validate_token import ValidateToken
from api.data.models import Role
from api.domain.errors import (
    AuthenticationError,
    Conflict,
    InvalidInput,
    PasswordChangeRequired,
    PermissionDenied,
)


pytestmark = pytest.mark.unit


def bootstrap(w):
    return BootstrapAdmin(users=w.users, password_hasher=w.hasher, pepper=w.PEPPER)


def create_user(w):
    return CreateUser(users=w.users, password_hasher=w.hasher, pepper=w.PEPPER)


def change_password(w):
    return ChangePassword(
        users=w.users,
        tokens=w.tokens,
        password_hasher=w.hasher,
        pepper=w.PEPPER,
        clock=w.clock,
    )


def authenticate(w):
    return AuthenticateUser(
        users=w.users,
        tokens=w.tokens,
        password_hasher=w.hasher,
        pepper=w.PEPPER,
        clock=w.clock,
        token_factory=lambda: "raw-token",
    )


def validate(w):
    return ValidateToken(tokens=w.tokens, users=w.users, clock=w.clock)


# ------------------------------------------------------------------
# BootstrapAdmin
# ------------------------------------------------------------------


def test_bootstrap_creates_the_first_admin(world):
    world.users.items.clear()

    user_id = bootstrap(world).execute("root", "supersecret")

    admin = world.users.get_by_id(user_id)
    assert admin.role is Role.ADMIN
    # The admin chose the password locally, no change needed.
    assert admin.must_change_password is False


def test_bootstrap_fails_if_an_admin_already_exists(world):
    with pytest.raises(Conflict):
        bootstrap(world).execute("root", "supersecret")


def test_bootstrap_validates_credentials(world):
    world.users.items.clear()

    with pytest.raises(InvalidInput):
        bootstrap(world).execute("root", "short")


# ------------------------------------------------------------------
# CreateUser
# ------------------------------------------------------------------


def test_admin_creates_a_user_that_must_change_password(world):
    user_id = create_user(world).execute(
        world.admin, "ana", "temporal123", Role.DEVELOPER
    )

    user = world.users.get_by_id(user_id)
    assert user.nickname == "ana"
    assert user.role is Role.DEVELOPER
    assert user.must_change_password is True
    assert user.password != "temporal123"


@pytest.mark.parametrize("actor", ["devops", "developer"])
def test_only_admin_creates_users(world, actor):
    with pytest.raises(PermissionDenied):
        create_user(world).execute(
            getattr(world, actor), "ana", "temporal123", Role.DEVELOPER
        )


def test_nickname_must_be_unique(world):
    with pytest.raises(Conflict):
        create_user(world).execute(
            world.admin, "devops", "temporal123", Role.DEVOPS
        )


def test_create_user_validates_nickname_and_password(world):
    with pytest.raises(InvalidInput):
        create_user(world).execute(world.admin, "a b", "temporal123", Role.DEVOPS)

    with pytest.raises(InvalidInput):
        create_user(world).execute(world.admin, "ana", "short", Role.DEVOPS)


# ------------------------------------------------------------------
# AuthenticateUser
# ------------------------------------------------------------------


def test_authenticate_returns_raw_token_and_stores_only_its_hash(world):
    raw = authenticate(world).execute("devops", "password")

    assert raw == "raw-token"
    stored = world.tokens.get_by_signature(
        hashlib.sha256(b"raw-token").hexdigest()
    )
    assert stored.user_id == world.devops.id
    assert stored.expires_at is None  # tokens do not expire for now


@pytest.mark.parametrize(
    "nickname,password", [("devops", "wrong-pass"), ("ghost", "password")]
)
def test_authenticate_rejects_bad_credentials(world, nickname, password):
    with pytest.raises(AuthenticationError):
        authenticate(world).execute(nickname, password)


def test_no_token_until_the_password_is_changed(world):
    world.add_user("new", Role.DEVELOPER, "temporal123", must_change=True)

    with pytest.raises(PasswordChangeRequired):
        authenticate(world).execute("new", "temporal123")


# ------------------------------------------------------------------
# ChangePassword
# ------------------------------------------------------------------


def test_change_password_unlocks_token_issuing(world):
    world.add_user("new", Role.DEVELOPER, "temporal123", must_change=True)

    change_password(world).execute("new", "temporal123", "definitive1")

    assert authenticate(world).execute("new", "definitive1") == "raw-token"


def test_change_password_requires_the_current_password(world):
    with pytest.raises(AuthenticationError):
        change_password(world).execute("devops", "wrong-pass", "definitive1")


def test_new_password_must_be_valid_and_different(world):
    with pytest.raises(InvalidInput):
        change_password(world).execute("devops", "password", "short")

    with pytest.raises(InvalidInput):
        change_password(world).execute("devops", "password", "password")


def test_change_password_revokes_existing_tokens(world):
    raw = authenticate(world).execute("devops", "password")

    change_password(world).execute("devops", "password", "definitive1")

    with pytest.raises(AuthenticationError):
        validate(world).execute(raw)


# ------------------------------------------------------------------
# ValidateToken / RevokeToken
# ------------------------------------------------------------------


def test_validate_token_returns_its_user(world):
    raw = authenticate(world).execute("devops", "password")

    assert validate(world).execute(raw).id == world.devops.id


@pytest.mark.parametrize("raw", ["", "unknown"])
def test_validate_rejects_unknown_tokens(world, raw):
    with pytest.raises(AuthenticationError):
        validate(world).execute(raw)


def test_revoked_token_is_no_longer_valid(world):
    raw = authenticate(world).execute("devops", "password")

    RevokeToken(tokens=world.tokens, clock=world.clock).execute(raw)

    with pytest.raises(AuthenticationError):
        validate(world).execute(raw)


def test_token_of_a_user_that_must_change_password_is_rejected(world):
    raw = authenticate(world).execute("devops", "password")
    user = world.users.get_by_id(world.devops.id)
    user.must_change_password = True
    world.users.update(user)

    with pytest.raises(PasswordChangeRequired):
        validate(world).execute(raw)
