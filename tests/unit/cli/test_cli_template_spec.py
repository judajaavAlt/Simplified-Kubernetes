import copy

import pytest

from cli.data.models import (
    InstanceConfig,
    LayerSource,
    Manifest,
    Stage,
    TemplatedFile,
    Variable,
    VariableType,
)
from cli.domain import documents, ignore_rules
from cli.domain.errors import ValidationError
from cli.domain.template_spec import parse_template


pytestmark = pytest.mark.unit

VALID = {
    "tag": "h:80/org/app:v1",
    "description": "Web service",
    "readme": "README.md",
    "template": {"layers": [{"origin": "src", "objective": "."}]},
    "instantiation": {"arguments": [
        {"name": "service", "type": "str", "default": "web",
         "description": "Service name"},
    ]},
    "build": {
        "arguments": [{"name": "replicas", "type": "int", "default": 1}],
        "commands": ["docker build -t [%service%] ."],
    },
    "deploy": {"commands": ["kubectl apply -f k8s"]},
}


def exists(path):
    return path in {"src", "README.md"}


def errors_of(document, origin_exists=exists):
    with pytest.raises(ValidationError) as error:
        parse_template(document, origin_exists)
    return error.value.errors


def test_valid_template():
    spec = parse_template(copy.deepcopy(VALID), exists)

    assert spec.tag == "h:80/org/app:v1"
    assert spec.layers == (LayerSource("src", "."),)
    assert spec.instantiation == (
        Variable("service", VariableType.STR, "web", "Service name"),
    )
    assert spec.build.variables[0].default == 1
    assert spec.deploy == Stage((), ("kubectl apply -f k8s",))
    assert spec.description == "Web service"
    assert spec.readme == "README.md"


@pytest.mark.parametrize("key", ["tag", "template", "instantiation",
                                 "build", "deploy"])
def test_required_sections(key):
    document = copy.deepcopy(VALID)
    del document[key]

    assert any(key in error for error in errors_of(document))


def test_layers_cannot_be_empty_and_origins_must_exist():
    document = copy.deepcopy(VALID)
    document["template"]["layers"] = []
    assert errors_of(document)

    document["template"]["layers"] = [{"origin": "missing", "objective": "."}]
    assert any("missing" in error for error in errors_of(document))


def test_variables_are_optional():
    document = copy.deepcopy(VALID)
    document["instantiation"] = {}
    document["build"] = {"commands": []}

    spec = parse_template(document, exists)

    assert spec.instantiation == ()


def test_every_problem_is_reported_together():
    document = copy.deepcopy(VALID)
    document["instantiation"]["arguments"] += [
        {"name": "a", "type": "int", "default": "x"},
        {"name": "a", "type": "str", "default": "y"},
        {"name": "b", "type": "list", "default": []},
        {"name": "c", "type": "bool"},
        {"name": "1bad", "type": "str", "default": ""},
    ]
    document["readme"] = "missing.md"

    assert len(errors_of(document)) == 6


def test_commands_are_validated():
    document = copy.deepcopy(VALID)
    document["build"]["commands"] = [
        "docker build . | tee log",
        "makeDirectory",
        "docker run [%unknown%]",
        "unknownCommand x",
    ]

    assert len(errors_of(document)) == 4


# Ignore rules (C-13) --------------------------------------------------------

def test_ignore_rules_like_gitignore():
    rules = ignore_rules.parse(
        "# comment\n*.log\nbuild/\n/root.txt\n!keep.log\ndocs/**/*.tmp\n"
    )

    assert ignore_rules.is_excluded("a/b.log", False, rules)
    assert not ignore_rules.is_excluded("keep.log", False, rules)
    assert ignore_rules.is_excluded("x/build", True, rules)
    assert not ignore_rules.is_excluded("x/build", False, rules)
    assert ignore_rules.is_excluded("root.txt", False, rules)
    assert not ignore_rules.is_excluded("a/root.txt", False, rules)
    assert ignore_rules.is_excluded("docs/a/b/c.tmp", False, rules)
    assert not ignore_rules.is_excluded("main.py", False, rules)


def test_no_rules_excludes_nothing():
    assert not ignore_rules.is_excluded("a.log", False, [])


# Documents --------------------------------------------------------------------

def test_manifest_document_roundtrip_keeps_order_and_values():
    manifest = Manifest(
        reference="h:80/org/app:v1",
        layers=("a" * 64,),
        files=(TemplatedFile("app/main.py", ("service",)),),
        instantiation=(Variable("service", VariableType.STR, "web", "d"),),
        build=Stage((Variable("n", VariableType.INT, 1),), ("docker build .",)),
        deploy=Stage((), ("kubectl apply -f k8s",)),
        description="Web",
        readme="# Readme",
    )

    document = documents.manifest_to_document(manifest)

    assert list(document) == ["tag", "description", "readme", "layers",
                              "files", "instantiation", "build", "deploy"]
    assert documents.manifest_from_document(document) == manifest


def test_instance_config_document_roundtrip():
    config = InstanceConfig(
        template_id="b" * 64,
        reference="h:80/org/app:v1",
        instantiation=(Variable("service", VariableType.STR, "shop"),),
        build=Stage((), ("docker build -t [%service%] .",)),
        deploy=Stage(),
    )

    document = documents.config_to_document(config)

    assert documents.config_from_document(document) == config


def test_old_config_without_template_section_is_accepted():
    config = documents.config_from_document(
        {"build": {"commands": ["echo"]}, "deploy": {}}
    )

    assert config.template_id is None
    assert config.build.commands == ("echo",)


def test_invalid_documents_raise_validation_errors():
    with pytest.raises(ValidationError):
        documents.manifest_from_document({"tag": "x"})
    with pytest.raises(ValidationError):
        documents.config_from_document(["not", "a", "mapping"])
