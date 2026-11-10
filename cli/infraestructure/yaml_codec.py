import yaml

from cli.domain.errors import ValidationError
from cli.persistence.document_codec import DocumentCodec


class YamlCodec(DocumentCodec):
    """YAML documents in UTF-8, keeping the key order."""

    def dump(self, document) -> bytes:
        """Write a document as YAML.

        Args:
            document: Plain dictionaries, lists and scalars.

        Returns:
            The YAML bytes.
        """
        return yaml.safe_dump(
            document, sort_keys=False, allow_unicode=True
        ).encode("utf-8")

    def load(self, content: bytes):
        """Read a YAML document.

        Args:
            content: YAML bytes.

        Returns:
            Plain dictionaries, lists and scalars.

        Raises:
            ValidationError: If the YAML is invalid.
        """
        try:
            return yaml.safe_load(content)
        except yaml.YAMLError as error:
            raise ValidationError(f"Invalid YAML: {error}") from None

    def problems(self, content: bytes) -> list[str]:
        """Find syntax errors, keys without value and empty list items.

        Args:
            content: YAML bytes.

        Returns:
            One ``line N: …`` message per problem.
        """
        try:
            documents = list(yaml.compose_all(content, Loader=yaml.SafeLoader))
        except yaml.MarkedYAMLError as error:
            mark = error.problem_mark or error.context_mark
            line = mark.line + 1 if mark else 1
            return [f"line {line}: {error.problem or error.context}"]
        except yaml.YAMLError as error:
            return [f"line 1: {error}"]
        found = []
        for document in documents:
            if document is not None:
                _walk(document, found)
        return found


def _is_missing(node) -> bool:
    """Tell whether a node is an implicit empty value (nothing written).

    Args:
        node: YAML node.

    Returns:
        True for an empty scalar resolved as null; ``null`` and ``~`` are
        written values and return False.
    """
    return (
        isinstance(node, yaml.ScalarNode)
        and node.tag == "tag:yaml.org,2002:null"
        and node.value == ""
    )


def _walk(node, found: list[str]) -> None:
    """Collect the empty values of a node and its children.

    Args:
        node: YAML node.
        found: List that receives the messages.
    """
    if isinstance(node, yaml.MappingNode):
        for key, value in node.value:
            if _is_missing(value):
                found.append(
                    f"line {key.start_mark.line + 1}: '{key.value}' has no value"
                )
            _walk(value, found)
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            if _is_missing(item):
                found.append(f"line {item.start_mark.line + 1}: empty list item")
            _walk(item, found)
