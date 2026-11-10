from pathlib import Path

import pytest

from cli.application.create_template import CreateTemplate
from cli.application.lookup import TemplateLookup
from cli.application.sample_files import WriteSampleFiles
from cli.application.setup_template import SetupTemplate
from cli.data.models import ArchiveEntry
from cli.domain import documents, env_file
from cli.domain.errors import CancelledError, NotFoundError, ValidationError
from cli_fakes import FakePrompter, project_world


pytestmark = pytest.mark.unit


def created_world(**kwargs):
    w = project_world(**kwargs)
    w.result = CreateTemplate(
        fs=w.fs, codec=w.codec, archiver=w.archiver, manifests=w.manifests,
        layers=w.layers, index=w.index, settings=w.settings, clock=w.clock,
    ).execute(Path("proj/template.yaml"))
    return w


def setup(w, values=None, force=False, output="out"):
    return SetupTemplate(
        fs=w.fs, codec=w.codec, archiver=w.archiver, manifests=w.manifests,
        layers=w.layers, lookup=TemplateLookup(w.index, w.settings),
        prompter=w.prompter,
    ).execute("reg:5000/org/web:v1", Path(output),
              Path(values) if values else None, force)


def test_setup_with_defaults():
    w = created_world()

    result = setup(w)

    assert w.fs.text("out/app/main.py") == "name = 'shop'\nport = 8080\n"
    assert w.fs.text("out/app/shop.txt") == "plain\n"
    assert w.fs.text("out/app/literal.txt") == "keep [%service%] as is\n"
    assert w.fs.read_bytes(Path("out/app/logo.png")) == b"\x89PNG\x00\x01[%service%]"
    assert w.fs.is_dir(Path("out/app/empty"))
    assert "app/main.py" in result.written
    assert "config.template" in result.written


def test_setup_with_values_file_quotes_and_types():
    w = created_world()
    w.fs.write_bytes(Path("values.env"), b'service = "api"\nport = 9000\n')

    setup(w)

    assert w.fs.text("out/app/main.py") == "name = 'api'\nport = 9000\n"
    assert w.fs.exists(Path("out/app/api.txt"))


def test_explicit_values_file_must_exist():
    w = created_world()

    with pytest.raises(NotFoundError):
        setup(w, values="missing.env")


def test_invalid_values_are_reported_and_nothing_is_written():
    w = created_world()
    w.fs.write_bytes(Path("my.env"), b"port = many\nother = 1\n")

    with pytest.raises(ValidationError) as error:
        setup(w, values="my.env")

    assert len(error.value.errors) == 2
    assert not w.fs.exists(Path("out"))


def test_config_template_keeps_build_deploy_and_chosen_values():
    w = created_world()
    w.fs.write_bytes(Path("values.env"), b"service = api\n")

    setup(w)

    config = documents.config_from_document(
        w.codec.load(w.fs.read_bytes(Path("out/config.template"))))
    assert config.template_id == w.result.manifest_id
    assert config.reference == "reg:5000/org/web:v1"
    assert {v.name: v.default for v in config.instantiation} == {
        "service": "api", "port": 8080}
    assert config.build.commands == ("docker build -t [%image%]:[%service%] .",)
    assert config.deploy.commands == ("kubectl apply -f k8s",)


def test_existing_files_cancel_writes_nothing():
    w = created_world()
    w.fs.write_bytes(Path("out/app/main.py"), b"mine")

    with pytest.raises(CancelledError):
        setup(w)

    assert w.prompter.asked == [("conflicts", ["app/main.py"])]
    assert w.fs.text("out/app/main.py") == "mine"
    assert not w.fs.exists(Path("out/app/shop.txt"))


def test_existing_files_overwrite_all():
    w = created_world()
    w.fs.write_bytes(Path("out/app/main.py"), b"mine")
    w.prompter = FakePrompter(action="all")

    setup(w)

    assert w.fs.text("out/app/main.py").startswith("name = 'shop'")


def test_existing_files_one_by_one():
    w = created_world()
    w.fs.write_bytes(Path("out/app/main.py"), b"mine")
    w.fs.write_bytes(Path("out/config.template"), b"old")
    w.prompter = FakePrompter(action="one", confirmations=[True, False])

    result = setup(w)

    assert w.prompter.asked[1:] == [("confirm", "app/main.py"),
                                    ("confirm", "config.template")]
    assert result.skipped == ["config.template"]
    assert w.fs.text("out/config.template") == "old"
    assert w.fs.text("out/app/main.py").startswith("name = 'shop'")


def test_force_overwrites_without_asking():
    w = created_world()
    w.fs.write_bytes(Path("out/app/main.py"), b"mine")

    setup(w, force=True)

    assert w.prompter.asked == []
    assert w.fs.text("out/app/main.py").startswith("name = 'shop'")


def test_unsafe_paths_are_rejected():
    w = created_world()
    layer_id = w.result.layers[0]
    w.layers.save(layer_id, w.archiver.pack([ArchiveEntry("../evil", b"x")]))

    with pytest.raises(ValidationError):
        setup(w)

    assert not w.fs.exists(Path("evil"))


def test_a_value_cannot_move_files_outside_the_output():
    w = created_world()
    w.fs.write_bytes(Path("values.env"), b"service = ../../evil\n")

    with pytest.raises(ValidationError):
        setup(w)


# setup -s (C-24) ----------------------------------------------------------------

def samples(w, force=False):
    return WriteSampleFiles(
        fs=w.fs, codec=w.codec, manifests=w.manifests,
        lookup=TemplateLookup(w.index, w.settings), prompter=w.prompter,
    ).execute("reg:5000/org/web:v1", Path("out"), force)


def test_samples_write_values_build_and_deploy_files():
    w = created_world()

    result = samples(w)

    assert result.written == ["values.env", "build.env", "deploy.env"]
    assert env_file.parse(w.fs.text("out/values.env")) == {
        "service": "shop", "port": "8080"}
    assert "# Service name" in w.fs.text("out/values.env")
    assert env_file.parse(w.fs.text("out/build.env")) == {"image": "img"}
    assert w.fs.text("out/deploy.env") == ""


def test_samples_do_not_overwrite_without_confirmation():
    w = created_world()
    w.fs.write_bytes(Path("out/values.env"), b"mine")

    with pytest.raises(CancelledError):
        samples(w)

    assert w.fs.text("out/values.env") == "mine"
    samples(w, force=True)
    assert w.fs.text("out/values.env") != "mine"
