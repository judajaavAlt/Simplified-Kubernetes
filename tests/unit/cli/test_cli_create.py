import json
from pathlib import Path

import pytest

from cli.application.create_template import CreateTemplate
from cli.data.models import TemplatedFile
from cli.domain import documents, references
from cli.domain.errors import NotFoundError, ValidationError
from cli_fakes import project_world, sha, template_document


pytestmark = pytest.mark.unit


def create(w, template="proj/template.yaml", ignore=None):
    use_case = CreateTemplate(
        fs=w.fs, codec=w.codec, archiver=w.archiver, manifests=w.manifests,
        layers=w.layers, index=w.index, settings=w.settings, clock=w.clock,
    )
    return use_case.execute(Path(template), Path(ignore) if ignore else None)


def manifest_of(w, manifest_id):
    return documents.manifest_from_document(
        w.codec.load(w.manifests.read(manifest_id))
    )


def layer_paths(w, layer_id):
    return [e.path for e in w.archiver.unpack(w.layers.read(layer_id))]


def test_create_packs_layers_and_registers_the_manifest():
    w = project_world()

    result = create(w)

    manifest = manifest_of(w, result.manifest_id)
    assert result.manifest_id == sha(w.manifests.read(result.manifest_id))
    assert str(result.reference) == "reg:5000/org/web:v1"
    assert manifest.reference == "reg:5000/org/web:v1"
    assert manifest.description == "Web service"
    assert len(manifest.layers) == 1
    assert layer_paths(w, manifest.layers[0]) == [
        "app/[%service%].txt", "app/empty", "app/literal.txt",
        "app/logo.png", "app/main.py",
    ]
    assert manifest.files == (
        TemplatedFile("app/literal.txt", ()),
        TemplatedFile("app/main.py", ("port", "service")),
    )
    assert w.index.get_tag(result.reference) == result.manifest_id
    assert w.index.layers_of(result.manifest_id) == manifest.layers


def test_same_project_gives_the_same_ids():
    w = project_world()

    first, second = create(w), create(w)

    assert first.manifest_id == second.manifest_id
    assert len(w.index.manifest_ids()) == 1


def test_file_origin_goes_inside_the_objective():
    document = template_document(template={"layers": [
        {"origin": "src/main.py", "objective": "."},
        {"origin": "src/main.py", "objective": "conf/"},
    ]})
    w = project_world(document)

    manifest = manifest_of(w, create(w).manifest_id)

    assert layer_paths(w, manifest.layers[0]) == ["main.py"]
    assert layer_paths(w, manifest.layers[1]) == ["conf/main.py"]


def test_templateignore_wins_over_gitignore_and_is_relative_to_its_folder():
    w = project_world(extra={
        "proj/.gitignore": "*.txt\n",
        "proj/.templateignore": "src/*.png\nempty/\n",
    })

    manifest = manifest_of(w, create(w).manifest_id)

    assert layer_paths(w, manifest.layers[0]) == [
        "app/[%service%].txt", "app/literal.txt", "app/main.py",
    ]


def test_gitignore_is_used_when_there_is_no_templateignore():
    w = project_world(extra={"proj/.gitignore": "*.txt\n"})

    manifest = manifest_of(w, create(w).manifest_id)

    assert "app/literal.txt" not in layer_paths(w, manifest.layers[0])


def test_explicit_ignore_file_must_exist():
    w = project_world()

    with pytest.raises(NotFoundError):
        create(w, ignore="proj/missing.ignore")


def test_readme_is_embedded():
    document = template_document(readme="docs/README.md")
    w = project_world(document, {"proj/docs/README.md": "# Usage\n"})

    assert manifest_of(w, create(w).manifest_id).readme == "# Usage\n"


def test_short_tag_is_completed_with_the_prefix():
    w = project_world(template_document(tag="web:v2"),
                      prefix="reg:5000/org")

    result = create(w)

    assert str(result.reference) == "reg:5000/org/web:v2"
    assert manifest_of(w, result.manifest_id).reference == str(result.reference)


def test_short_tag_without_prefix_is_an_error():
    w = project_world(template_document(tag="web:v2"))

    with pytest.raises(ValidationError, match="work set"):
        create(w)


def test_every_problem_is_reported_and_nothing_is_stored():
    document = template_document(template={"layers": [
        {"origin": "nope", "objective": "."}]})
    document["instantiation"]["arguments"][1]["default"] = "8080"
    w = project_world(document)

    with pytest.raises(ValidationError) as error:
        create(w)

    assert len(error.value.errors) == 2
    assert w.index.manifest_ids() == []
    assert not w.layers.blobs


def test_invalid_yaml_is_a_validation_error():
    w = project_world()
    w.fs.write_bytes(Path("proj/template.yaml"), b"{not json")

    with pytest.raises(ValidationError):
        create(w)


def test_missing_template_file():
    w = project_world()

    with pytest.raises(NotFoundError):
        create(w, template="other/template.yaml")


def test_repeated_tag_moves_and_leaves_the_old_manifest_orphan():
    w = project_world()
    old = create(w).manifest_id
    w.fs.write_bytes(Path("proj/src/main.py"), b"changed [%service%]\n")

    new = create(w).manifest_id

    assert new != old
    assert w.index.get_tag(references.parse("reg:5000/org/web:v1")) == new
    assert w.index.tags_of(old) == []
    assert w.index.has_manifest(old)
