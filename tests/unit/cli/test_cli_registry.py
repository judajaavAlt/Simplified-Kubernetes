from pathlib import Path

import pytest

from cli.application.create_template import CreateTemplate
from cli.application.login import Login, Logout
from cli.application.lookup import TemplateLookup
from cli.application.pull_template import PullTemplate
from cli.application.push_template import PushTemplate
from cli.application.sessions import RegistrySessions
from cli.data.models import Credentials
from cli.domain import references
from cli.domain.errors import (
    NotFoundError,
    NotLoggedInError,
    RegistryError,
    ValidationError,
)
from cli_fakes import make_world, project_world


pytestmark = pytest.mark.unit


def login(w, insecure=False, nickname="dev", password="secret12"):
    return Login(w.credentials, w.connector, w.prompter).execute(
        "reg:5000", nickname, password, insecure)


def created_world():
    w = project_world()
    w.result = CreateTemplate(
        fs=w.fs, codec=w.codec, archiver=w.archiver, manifests=w.manifests,
        layers=w.layers, index=w.index, settings=w.settings, clock=w.clock,
    ).execute(Path("proj/template.yaml"))
    login(w)
    return w


def push(w, name="reg:5000/org/web:v1"):
    events = []
    result = PushTemplate(
        lookup=TemplateLookup(w.index, w.settings), manifests=w.manifests,
        layers=w.layers, codec=w.codec,
        sessions=RegistrySessions(w.credentials, w.connector),
    ).execute(name, events.append)
    return result, events


def pull(w, name="reg:5000/org/web:v1"):
    return PullTemplate(
        lookup=TemplateLookup(w.index, w.settings), index=w.index,
        manifests=w.manifests, layers=w.layers, codec=w.codec,
        sessions=RegistrySessions(w.credentials, w.connector), clock=w.clock,
    ).execute(name, lambda event: None)


# Login (C-28, C-29) ---------------------------------------------------------------

def test_login_saves_a_token_per_registry():
    w = make_world()

    login(w)

    saved = w.credentials.get("reg:5000")
    assert saved == Credentials("reg:5000", "token-0", "dev", True)
    assert w.connector.connections[0] == ("reg:5000", True, None)


def test_insecure_login_uses_http():
    w = make_world()

    login(w, insecure=True)

    assert w.credentials.get("reg:5000").secure is False


def test_login_asks_for_a_new_password_when_required():
    w = make_world()
    w.server.users["new"] = ["temporary1", True]

    login(w, nickname="new", password="temporary1")

    assert w.prompter.asked == [("password",)]
    assert w.server.users["new"] == ["newsecret1", False]
    assert w.credentials.get("reg:5000").nickname == "new"


def test_login_rejects_an_invalid_registry():
    w = make_world()

    with pytest.raises(ValidationError):
        Login(w.credentials, w.connector, w.prompter).execute(
            "reg/org", "dev", "secret12")


def test_logout_revokes_and_forgets_the_token():
    w = make_world()
    login(w)

    assert Logout(w.credentials, w.connector).execute("reg:5000") is True

    assert w.credentials.get("reg:5000") is None
    assert w.server.tokens == set()


def test_logout_without_session():
    w = make_world()

    with pytest.raises(NotLoggedInError):
        Logout(w.credentials, w.connector).execute("reg:5000")


def test_logout_forgets_the_token_even_if_the_registry_fails():
    w = make_world()
    login(w)
    w.server.tokens.clear()

    class Failing(type(w.connector.connect("x"))):
        def logout(self):
            raise RegistryError("unreachable")

    w.connector.connect = lambda *a, **k: Failing(w.server, None)

    assert Logout(w.credentials, w.connector).execute("reg:5000") is False
    assert w.credentials.get("reg:5000") is None


# Push (C-30) ---------------------------------------------------------------------

def test_push_uploads_layers_then_manifest_then_tag():
    w = created_world()

    result, events = push(w)

    server = w.server
    manifest_id = w.result.manifest_id
    layer_id = w.result.layers[0]
    assert server.blobs[layer_id] == w.layers.read(layer_id)
    assert server.blobs[manifest_id] == w.manifests.read(manifest_id)
    assert server.manifests[("org/web", manifest_id)] == (layer_id,)
    assert server.tags[("org/web", "v1")] == manifest_id
    kinds = [c[1] for c in server.calls if c[0] == "start_upload"]
    assert kinds == ["layer", "manifest"]
    assert result.uploaded == 2 and result.skipped == 0
    assert any("layer 1/1" in e for e in events)


def test_push_sends_pieces_in_order_and_skips_existing_blobs():
    w = created_world()
    push(w)
    w.server.calls.clear()

    result, _ = push(w)

    assert result.uploaded == 0 and result.skipped == 2
    assert not [c for c in w.server.calls if c[0] == "chunk"]


def test_push_retries_a_rejected_piece():
    w = created_world()
    w.server.reject_next_chunk = 2

    push(w)

    assert w.server.blobs[w.result.manifest_id]


def test_push_cancels_after_three_rejections():
    w = created_world()
    w.server.reject_next_chunk = 3

    with pytest.raises(RegistryError):
        push(w)

    assert any(c[0] == "cancel" for c in w.server.calls)
    assert w.server.uploads == {}


def test_push_needs_a_reference_and_a_session():
    w = created_world()

    with pytest.raises(ValidationError):
        push(w, w.result.manifest_id)
    w.credentials.delete("reg:5000")
    with pytest.raises(NotLoggedInError):
        push(w)


# Pull (C-31) ---------------------------------------------------------------------

def pushed_and_cleared():
    w = created_world()
    push(w)
    w.index.clear_templates()
    w.manifests.blobs.clear()
    w.layers.blobs.clear()
    return w


def test_pull_downloads_verifies_and_registers():
    w = pushed_and_cleared()

    result = pull(w)

    manifest_id = w.result.manifest_id
    assert result.manifest_id == manifest_id
    assert result.downloaded == 2
    assert w.manifests.exists(manifest_id)
    assert w.layers.exists(w.result.layers[0])
    reference = references.parse("reg:5000/org/web:v1")
    assert w.index.get_tag(reference) == manifest_id
    assert w.index.layers_of(manifest_id) == w.result.layers


def test_pull_skips_layers_it_already_has():
    w = pushed_and_cleared()
    pull(w)
    w.index.clear_templates()
    w.manifests.blobs.clear()

    assert pull(w).downloaded == 1


def test_pull_retries_a_corrupted_piece():
    w = pushed_and_cleared()
    w.server.corrupt_next_download = 2

    pull(w)

    assert w.manifests.exists(w.result.manifest_id)


def test_pull_fails_after_three_corrupted_pieces():
    w = pushed_and_cleared()
    w.server.corrupt_next_download = 3

    with pytest.raises(RegistryError):
        pull(w)

    assert not w.index.manifest_ids()


def test_pull_of_an_unknown_tag():
    w = pushed_and_cleared()

    with pytest.raises(RegistryError):
        pull(w, "reg:5000/org/web:missing")


def test_pull_short_reference_needs_a_prefix():
    w = pushed_and_cleared()

    with pytest.raises(ValidationError):
        pull(w, "web:v1")
    w.settings.prefix = "reg:5000/org"
    assert pull(w, "web:v1").manifest_id == w.result.manifest_id


def test_pull_rejects_an_id_without_registry():
    w = pushed_and_cleared()

    with pytest.raises((ValidationError, NotFoundError)):
        pull(w, w.result.manifest_id)
