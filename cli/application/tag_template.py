"""``template tag`` (C-32)."""
from dataclasses import dataclass

from cli.application.lookup import TemplateLookup
from cli.data.models import Reference
from cli.persistence.template_index import TemplateIndex


@dataclass
class TagTemplate:
    """Give a local template another reference, like ``docker tag``.

    Attributes:
        index: Local index.
        lookup: Finds local templates.
    """

    index: TemplateIndex
    lookup: TemplateLookup

    def execute(self, source: str, target: str) -> Reference:
        """Point a new reference to the manifest of another one.

        A reference that already exists is moved, like any repeated tag.

        Args:
            source: Reference, ID or ID prefix of the template.
            target: New reference, complete or short.

        Returns:
            The complete new reference.

        Raises:
            NotFoundError: If the source does not exist.
            ValidationError: If the target is not a valid reference.
        """
        manifest_id, _ = self.lookup.find(source)
        reference = self.lookup.parse(target)
        self.index.set_tag(reference, manifest_id)
        return reference
