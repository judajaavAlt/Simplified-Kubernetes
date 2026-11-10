import pytest

from cli.data.models import Prefix, Reference
from cli.domain import references
from cli.domain.errors import ValidationError


pytestmark = pytest.mark.unit


def test_full_reference_with_and_without_tag():
    assert references.parse("reg.local:5000/org/app:v1") == Reference(
        "reg.local", 5000, "org", "app", "v1"
    )
    assert references.parse("localhost:8000/org/app").tag == "latest"


def test_full_reference_ignores_the_prefix():
    prefix = Prefix("other", 1, "x", "y")

    assert str(references.parse("h:80/org/app:v2", prefix)) == (
        "h:80/org/app:v2"
    )


@pytest.mark.parametrize(
    "prefix, text, expected",
    [
        (Prefix("h", 80), "org/app:v1", "h:80/org/app:v1"),
        (Prefix("h", 80, "org"), "app", "h:80/org/app:latest"),
        (Prefix("h", 80, "org"), "other/app:v1", "h:80/other/app:v1"),
        (Prefix("h", 80, "org", "app"), ":v1", "h:80/org/app:v1"),
        (Prefix("h", 80, "org", "app"), "v1", "h:80/org/v1:latest"),
    ],
)
def test_short_references_are_completed_from_the_left(prefix, text, expected):
    assert str(references.parse(text, prefix)) == expected


def test_short_reference_without_prefix_is_an_error():
    with pytest.raises(ValidationError, match="work set"):
        references.parse("org/app:v1")


def test_short_reference_needs_enough_prefix():
    with pytest.raises(ValidationError):
        references.parse("app", Prefix("h", 80))


@pytest.mark.parametrize(
    "text",
    ["h:80/Org/app", "h:80/org/app:", "h:99999/org/app", "h:80/org/a/b",
     "h:80/org/app:" + "a" * 64, "h:80/org/app:bad tag"],
)
def test_invalid_references(text):
    with pytest.raises(ValidationError):
        references.parse(text)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("h:80", Prefix("h", 80)),
        ("h:80/org", Prefix("h", 80, "org")),
        ("h:80/org/app", Prefix("h", 80, "org", "app")),
    ],
)
def test_parse_prefix(text, expected):
    assert references.parse_prefix(text) == expected


@pytest.mark.parametrize("text", ["org/app", "h:80/org/app:v1", "h", "h:x"])
def test_invalid_prefix(text):
    with pytest.raises(ValidationError):
        references.parse_prefix(text)


def test_format_prefix():
    assert references.format_prefix(Prefix("h", 80, "org")) == "h:80/org"


def test_parse_registry():
    assert references.parse_registry("h:80") == "h:80"
    with pytest.raises(ValidationError):
        references.parse_registry("h:80/org")
