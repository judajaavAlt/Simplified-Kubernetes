import pytest

from cli.data.models import Stage, Variable, VariableType
from cli.domain import commands, ids, paths
from cli.domain.errors import ValidationError


pytestmark = pytest.mark.unit


# Tokenizer (C-44, C-46) ---------------------------------------------------------

def test_tokenize_groups_quotes_and_keeps_backslashes():
    assert commands.tokenize(r'docker build -t "my app" C:\src') == [
        "docker", "build", "-t", "my app", r"C:\src",
    ]
    assert commands.tokenize("print ''") == ["print", ""]


@pytest.mark.parametrize(
    "line", ["a | b", "a > out", "a && b", "a; b", "a < in", "say 'open"]
)
def test_tokenize_rejects_shell_syntax(line):
    with pytest.raises(ValidationError):
        commands.tokenize(line)


def test_quoted_operators_are_plain_text():
    assert commands.tokenize('print "a | b > c"') == ["print", "a | b > c"]


# Stage resolution (C-26) -------------------------------------------------------

STAGE = Stage(
    variables=(
        Variable("image", VariableType.STR, "default-image"),
        Variable("push", VariableType.BOOL, False),
    ),
    commands=(
        "docker build -t [%image%]:[%version%] [%path%]",
        "print [%push%] [% service %]",
    ),
)
SHARED = (
    Variable("service", VariableType.STR, "shop"),
    Variable("version", VariableType.INT, 2),
    Variable("path", VariableType.STR, "my folder"),
)


def test_resolve_stage_combines_stage_shared_and_env_values():
    argvs = commands.resolve_stage(STAGE, SHARED, {"image": "web", "version": "3"})

    assert argvs == [
        ["docker", "build", "-t", "web:3", "my folder"],
        ["print", "false", "shop"],
    ]


def test_shared_values_override_stage_defaults():
    stage = Stage((Variable("service", VariableType.STR, "x"),),
                  ("print [%service%]",))

    assert commands.resolve_stage(stage, SHARED, {}) == [["print", "shop"]]


def test_resolve_stage_rejects_unknown_keys_and_bad_types():
    with pytest.raises(ValidationError) as error:
        commands.resolve_stage(STAGE, SHARED, {"push": "yes", "typo": "1"})

    assert len(error.value.errors) == 2


# Dry run view (C-47) -----------------------------------------------------------

def test_describe_standard_command_per_system():
    windows = commands.describe(["makeDirectory", "out dir"], "Windows")
    linux = commands.describe(["makeDirectory", "out dir"], "Linux")

    assert windows.text == 'makeDirectory "out dir"'
    assert "New-Item" in windows.native
    assert linux.native == "mkdir -p 'out dir'"
    assert not windows.destructive


def test_describe_external_program_has_no_translation():
    view = commands.describe(["kubectl", "apply", "-f", "k8s"], "Linux")

    assert view.native is None
    assert view.text == "kubectl apply -f k8s"


@pytest.mark.parametrize(
    "argv",
    [
        ["removePath", "x"],
        ["kubectl", "delete", "pod", "a"],
        ["docker", "rmi", "img"],
        ["docker", "system", "prune"],
        ["helm", "uninstall", "app"],
        ["rm", "-rf", "x"],
        [r"C:\tools\kubectl.exe", "delete", "ns", "a"],
    ],
)
def test_destructive_commands(argv):
    assert commands.describe(argv, "Linux").destructive


@pytest.mark.parametrize(
    "argv", [["kubectl", "apply"], ["docker", "build", "."], ["print", "rm"]]
)
def test_safe_commands(argv):
    assert not commands.describe(argv, "Linux").destructive


# Paths and IDs -----------------------------------------------------------------

def test_join_objective():
    assert paths.join("." , "a/b.txt") == "a/b.txt"
    assert paths.join("", "a") == "a"
    assert paths.join("app/", "src/x") == "app/src/x"
    assert paths.join("./app", "x") == "app/x"


@pytest.mark.parametrize("path", ["../x", "/etc/passwd", "a/../../b", "C:/x"])
def test_unsafe_paths_are_rejected(path):
    with pytest.raises(ValidationError):
        paths.check_relative(path)


def test_ids():
    full = "ab" * 32
    assert ids.is_id(full)
    assert ids.is_id_prefix("abab")
    assert not ids.is_id_prefix("aba")
    assert not ids.is_id_prefix("org/app")
    assert ids.short(full) == full[:12]
