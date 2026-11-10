import pytest

from cli.data.models import Variable, VariableType
from cli.domain import env_file, values, variables
from cli.domain.errors import ValidationError


pytestmark = pytest.mark.unit


# Delimiter [% name %] (C-05, C-06, C-41) -----------------------------------

def test_substitute_replaces_declared_variables_with_optional_spaces():
    text = "a=[%name%] b=[% name %] c=[%  port%]"

    assert variables.substitute(text, {"name": "web", "port": "80"}) == (
        "a=web b=web c=80"
    )


def test_substitute_leaves_undeclared_placeholders_and_helm_syntax():
    text = "[%other%] {{ .Values.name }} {{name}}"

    assert variables.substitute(text, {"name": "web"}) == text


def test_escaped_placeholder_becomes_literal():
    assert variables.substitute(r"\[%name%] [%name%]", {"name": "web"}) == (
        "[%name%] web"
    )


def test_uses_lists_declared_names_once_and_ignores_escaped_ones():
    text = r"[%b%] [%a%] [% b %] \[%c%] [%unknown%]"

    assert variables.uses(text, ["a", "b", "c"]) == ("a", "b")


def test_needs_processing_with_variables_or_escapes():
    assert variables.needs_processing("[%a%]", ["a"])
    assert variables.needs_processing(r"\[%z%]", ["a"])
    assert not variables.needs_processing("[%z%] {{a}}", ["a"])


def test_is_text_rejects_binary_content():
    assert variables.is_text("hola [%a%]".encode("utf-8"))
    assert not variables.is_text(b"\x00\x01\x02")
    assert not variables.is_text(b"\xff\xfe\xfa")


def test_valid_names():
    assert variables.is_valid_name("service_name")
    assert not variables.is_valid_name("1name")
    assert not variables.is_valid_name("na-me")


# Types (C-08, C-09, C-51) --------------------------------------------------

@pytest.mark.parametrize(
    "raw, vtype, expected",
    [
        ("hello", VariableType.STR, "hello"),
        ("42", VariableType.INT, 42),
        ("-3", VariableType.INT, -3),
        ("0.5", VariableType.FLOAT, 0.5),
        ("2", VariableType.FLOAT, 2.0),
        ("true", VariableType.BOOL, True),
        ("false", VariableType.BOOL, False),
    ],
)
def test_convert_raw_values(raw, vtype, expected):
    assert values.convert("x", raw, vtype) == expected


@pytest.mark.parametrize(
    "raw, vtype",
    [
        ("True", VariableType.BOOL),
        ("1", VariableType.BOOL),
        ("yes", VariableType.BOOL),
        ("4.2", VariableType.INT),
        ("abc", VariableType.FLOAT),
    ],
)
def test_convert_rejects_values_of_another_type(raw, vtype):
    with pytest.raises(ValidationError, match="x"):
        values.convert("x", raw, vtype)


def test_check_default_requires_a_default_of_the_declared_type():
    assert values.check_default("a", "text", VariableType.STR) == []
    assert values.check_default("a", 3, VariableType.INT) == []
    assert values.check_default("a", 3, VariableType.FLOAT) == []
    assert values.check_default("a", True, VariableType.BOOL) == []
    assert values.check_default("a", None, VariableType.STR)
    assert values.check_default("a", 3, VariableType.STR)
    assert values.check_default("a", True, VariableType.INT)
    assert values.check_default("a", "true", VariableType.BOOL)


def test_format_value():
    assert values.format_value(True, VariableType.BOOL) == "true"
    assert values.format_value(False, VariableType.BOOL) == "false"
    assert values.format_value(3, VariableType.INT) == "3"
    assert values.format_value("x", VariableType.STR) == "x"


def test_resolve_uses_defaults_and_typed_overrides():
    declared = (
        Variable("name", VariableType.STR, "app"),
        Variable("replicas", VariableType.INT, 1),
    )

    assert values.resolve(declared, {"replicas": "3"}) == {
        "name": "app",
        "replicas": 3,
    }


def test_resolve_reports_every_error_together():
    declared = (Variable("replicas", VariableType.INT, 1),)

    with pytest.raises(ValidationError) as error:
        values.resolve(declared, {"replicas": "many", "typo": "x"})

    assert len(error.value.errors) == 2


# .env files (C-21) ---------------------------------------------------------

def test_parse_env_strips_spaces_quotes_and_comments():
    text = '# comment\n\nname = "web"\nport=80\nquote = \'a b\'\nempty =\n'

    assert env_file.parse(text) == {
        "name": "web",
        "port": "80",
        "quote": "a b",
        "empty": "",
    }


def test_parse_env_rejects_lines_without_equal_or_name():
    with pytest.raises(ValidationError) as error:
        env_file.parse("novalue\n = 3\n")

    assert len(error.value.errors) == 2


def test_render_env_writes_description_and_quotes_strings():
    declared = (
        Variable("name", VariableType.STR, "app", "Service name"),
        Variable("debug", VariableType.BOOL, False),
    )

    text = env_file.render(declared)

    assert text == '# Service name\nname = "app"\n\ndebug = false\n'
    assert env_file.parse(text) == {"name": "app", "debug": "false"}
