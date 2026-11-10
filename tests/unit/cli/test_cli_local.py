from pathlib import Path

import pytest

from cli.application.create_template import CreateTemplate
from cli.application.inspect_template import InspectTemplate
from cli.application.list_templates import ListTemplates
from cli.application.lookup import TemplateLookup
from cli.application.rebuild_index import RebuildIndex
from cli.application.remove_template import RemoveTemplate
from cli.application.sessions import RegistrySessions
from cli.application.tag_template import TagTemplate
from cli.application.work_prefix import SetWorkPrefix, ShowWorkPrefix
from cli.data.models import Credentials
from cli.domain import references
from cli.domain.errors import (
    AmbiguousReferenceError,
    NotFoundError,
    NotLoggedInError,
    ValidationError,
)
from cli_fakes import project_world, template_document


pytestmark = pytest.mark.unit


def create(w, **document):
    w.fs.write_bytes(Path("proj/template.yaml"),
                     w.codec.dump(template_document(**document)))
    return CreateTemplate(
        fs=w.fs, codec=w.codec, archiver=w.archiver, manifests=w.manifests,
        layers=w.layers, index=w.index, settings=w.settings, clock=w.clock,
    ).execute(Path("proj/template.yaml"))


def lookup(w):
    return TemplateLookup(w.index, w.settings)


def remove(w, name, remote=False):
    return RemoveTemplate(
        index=w.index, manifests=w.manifests, layers=w.layers,
        lookup=lookup(w), sessions=RegistrySessions(w.credentials, w.connector),
    ).execute(name, remote)


# Lookup (C-20) ----------------------------------------------------------------

def test_find_by_reference_id_and_prefix():
    w = project_world()
    result = create(w)

    assert lookup(w).find("reg:5000/org/web:v1") == (
        result.manifest_id, result.reference)
    assert lookup(w).find(result.manifest_id) == (result.manifest_id, None)
    assert lookup(w).find(result.manifest_id[:4])[0] == result.manifest_id


def test_find_short_reference_with_prefix():
    w = project_world(prefix="reg:5000/org")
    result = create(w)

    assert lookup(w).find("web:v1")[0] == result.manifest_id


def test_find_errors():
    w = project_world()
    create(w)

    with pytest.raises(NotFoundError):
        lookup(w).find("reg:5000/org/web:v9")
    with pytest.raises(NotFoundError):
        lookup(w).find("abc")


def test_ambiguous_prefix():
    w = project_world()
    w.index.add_manifest("abcd" + "1" * 60, (), 1, w.clock())
    w.index.add_manifest("abcd" + "2" * 60, (), 1, w.clock())

    with pytest.raises(AmbiguousReferenceError):
        lookup(w).find("abcd")


# List and inspect (C-15, C-18, C-19) --------------------------------------------

def test_list_shows_tags_and_orphans():
    w = project_world()
    old = create(w).manifest_id
    new = create(w, description="changed").manifest_id

    records = ListTemplates(w.index).execute()

    assert [r.id for r in records] == [new, old]
    assert [str(t) for t in records[0].tags] == ["reg:5000/org/web:v1"]
    assert records[1].tags == ()
    assert records[0].size > 0


def test_inspect_returns_the_manifest():
    w = project_world()
    result = create(w)

    manifest_id, manifest = InspectTemplate(
        lookup(w), w.manifests, w.codec).execute("reg:5000/org/web:v1")

    assert manifest_id == result.manifest_id
    assert manifest.description == "Web service"
    assert [v.name for v in manifest.instantiation] == ["service", "port"]


# Tag (C-32) ---------------------------------------------------------------------

def test_tag_creates_another_reference():
    w = project_world(prefix="other:80/team")
    result = create(w)

    reference = TagTemplate(w.index, lookup(w)).execute(
        "reg:5000/org/web:v1", "web:prod")

    assert str(reference) == "other:80/team/web:prod"
    assert w.index.get_tag(reference) == result.manifest_id


# Remove (C-33, C-50) ------------------------------------------------------------

def test_removing_one_of_two_tags_keeps_the_manifest():
    w = project_world()
    result = create(w)
    TagTemplate(w.index, lookup(w)).execute(result.manifest_id, "reg:5000/org/web:v2")

    outcome = remove(w, "reg:5000/org/web:v1")

    assert outcome.untagged == ["reg:5000/org/web:v1"]
    assert outcome.deleted == []
    assert w.manifests.exists(result.manifest_id)


def test_removing_the_last_tag_deletes_manifest_and_unshared_layers():
    w = project_world()
    shared = create(w).manifest_id
    TagTemplate(w.index, lookup(w)).execute(shared, "reg:5000/org/keep:v1")
    w.fs.write_bytes(Path("proj/extra/x.txt"), b"x")
    layers = {"layers": [{"origin": "src", "objective": "app"},
                         {"origin": "extra", "objective": "x"}]}
    result = create(w, template=layers)

    outcome = remove(w, "reg:5000/org/web:v1")

    shared_layer, own_layer = w.index.layers_of(shared)[0], result.layers[1]
    assert outcome.deleted == [result.manifest_id, own_layer]
    assert not w.manifests.exists(result.manifest_id)
    assert not w.layers.exists(own_layer)
    assert w.layers.exists(shared_layer)
    assert not w.index.has_manifest(result.manifest_id)


def test_removing_by_id_deletes_every_tag():
    w = project_world()
    result = create(w)
    TagTemplate(w.index, lookup(w)).execute(result.manifest_id, "reg:5000/org/web:v2")

    outcome = remove(w, result.manifest_id[:6])

    assert sorted(outcome.untagged) == ["reg:5000/org/web:v1", "reg:5000/org/web:v2"]
    assert outcome.deleted[0] == result.manifest_id
    assert w.layers.blobs == {}


def test_remote_remove_needs_a_session_and_deletes_in_the_registry():
    w = project_world()
    result = create(w)

    with pytest.raises(NotLoggedInError):
        remove(w, "reg:5000/org/web:v1", remote=True)
    assert w.index.has_manifest(result.manifest_id)

    w.credentials.save(Credentials("reg:5000", "token-0", "dev"))
    w.server.tokens.add("token-0")
    remove(w, "reg:5000/org/web:v1", remote=True)

    assert ("delete", "org/web", "v1") in w.server.calls
    assert not w.index.has_manifest(result.manifest_id)


def test_remote_remove_by_id_deletes_by_signature_in_each_repository():
    w = project_world()
    result = create(w)
    w.credentials.save(Credentials("reg:5000", "token-0", "dev"))
    w.server.tokens.add("token-0")

    remove(w, result.manifest_id, remote=True)

    assert ("delete", "org/web", result.manifest_id) in w.server.calls


def test_remote_remove_of_an_orphan_is_an_error():
    w = project_world()
    old = create(w).manifest_id
    create(w, description="new")

    with pytest.raises(ValidationError):
        remove(w, old, remote=True)


# Work prefix (C-27) -------------------------------------------------------------

def test_work_prefix_is_validated_and_saved():
    w = project_world()

    assert SetWorkPrefix(w.settings).execute("reg:5000/org") == "reg:5000/org"
    assert ShowWorkPrefix(w.settings).execute() == "reg:5000/org"
    with pytest.raises(ValidationError):
        SetWorkPrefix(w.settings).execute("org/app:v1")
    assert w.settings.prefix == "reg:5000/org"


def test_work_prefix_can_be_removed():
    w = project_world(prefix="reg:5000")

    assert SetWorkPrefix(w.settings).execute(None) is None
    assert ShowWorkPrefix(w.settings).execute() is None


# Rebuild index (C-17) -----------------------------------------------------------

def test_rebuild_index_from_the_stored_manifests():
    w = project_world()
    old = create(w).manifest_id
    new = create(w, description="new").manifest_id
    w.index.clear_templates()
    w.index.record_dry_run(new, "build", w.clock())

    count = RebuildIndex(w.index, w.manifests, w.layers, w.codec).execute()

    assert count == 2
    reference = references.parse("reg:5000/org/web:v1")
    assert w.index.get_tag(reference) == new
    assert w.index.has_manifest(old)
    assert w.index.has_dry_run(new, "build")
