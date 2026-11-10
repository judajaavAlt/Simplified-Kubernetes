"""YAML files of a template must be well formed (scope decided 2026-11-04)."""
from pathlib import Path

import pytest

from cli.application.create_template import CreateTemplate
from cli.application.lookup import TemplateLookup
from cli.application.setup_template import SetupTemplate
from cli.domain import yaml_files
from cli.domain.errors import ValidationError
from cli_fakes import project_world


pytestmark = pytest.mark.unit


def create(w):
    return CreateTemplate(
        fs=w.fs, codec=w.codec, archiver=w.archiver, manifests=w.manifests,
        layers=w.layers, index=w.index, settings=w.settings, clock=w.clock,
    ).execute(Path("proj/template.yaml"))


def setup(w):
    return SetupTemplate(
        fs=w.fs, codec=w.codec, archiver=w.archiver, manifests=w.manifests,
        layers=w.layers, lookup=TemplateLookup(w.index, w.settings),
        prompter=w.prompter,
    ).execute("reg:5000/org/web:v1", Path("out"), None, False)


def test_which_files_are_checked():
    assert yaml_files.should_check("k8s/deploy.yaml", "a: 1")
    assert yaml_files.should_check("k8s/deploy.YML", "a: 1")
    assert not yaml_files.should_check("main.py", "a:")
    assert not yaml_files.should_check("chart/templates/d.yaml",
                                       "image: {{ .Values.image }}")


def test_create_rejects_broken_yaml_and_stores_nothing():
    w = project_world(extra={
        "proj/src/k8s/deploy.yaml": "BROKEN",
        "proj/src/k8s/service.yml": "BROKEN",
    })

    with pytest.raises(ValidationError) as error:
        create(w)

    assert len(error.value.errors) == 2
    assert error.value.errors[0].startswith("app/k8s/deploy.yaml: ")
    assert w.index.manifest_ids() == [] and not w.layers.blobs


def test_create_checks_yaml_after_replacing_the_defaults():
    w = project_world(extra={"proj/src/k8s/svc.yaml": "name: [%service%]\n"})

    assert create(w).manifest_id


def test_go_templates_and_other_files_are_not_checked():
    w = project_world(extra={
        "proj/src/chart/templates/d.yaml": "BROKEN {{ .Values.x }}",
        "proj/src/notes.txt": "BROKEN",
    })

    assert create(w).manifest_id


def test_setup_rejects_yaml_broken_by_a_chosen_value():
    w = project_world(extra={"proj/src/k8s/cfg.yaml": "value: [%service%]\n"})
    create(w)
    w.fs.write_bytes(Path("values.env"), b"service = BROKEN\n")

    with pytest.raises(ValidationError, match="app/k8s/cfg.yaml"):
        setup(w)

    assert not w.fs.exists(Path("out"))
