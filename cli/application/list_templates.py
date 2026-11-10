"""``template list`` (C-18, C-19)."""
from dataclasses import dataclass

from cli.data.models import ManifestRecord
from cli.persistence.template_index import TemplateIndex


@dataclass
class ListTemplates:
    """List the local templates, orphans included.

    Attributes:
        index: Local index.
    """

    index: TemplateIndex

    def execute(self) -> list[ManifestRecord]:
        """List every local template.

        Returns:
            The records, newest first; an orphan has no tags.
        """
        return self.index.list_manifests()
