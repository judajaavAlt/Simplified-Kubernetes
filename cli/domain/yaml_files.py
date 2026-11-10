"""Which files of a template are checked as YAML (scope decided 2026-11-04).

Only the form of the YAML is checked (syntax, and keys or list items
without a value); the Kubernetes meaning of the values is out of scope.
"""

YAML_EXTENSIONS = (".yaml", ".yml")


def should_check(path: str, text: str) -> bool:
    """Decide whether a file must be a well formed YAML document.

    Go and Helm templates (``{{ }}``) are skipped: they only become YAML
    after they are rendered.

    Args:
        path: Path inside the template.
        text: Content of the file.

    Returns:
        True for ``.yaml`` and ``.yml`` files that are not Go templates.
    """
    return path.lower().endswith(YAML_EXTENSIONS) and "{{" not in text
