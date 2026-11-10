"""``template setup -s``: sample ``.env`` files (C-24)."""
from dataclasses import dataclass
from pathlib import Path

from cli.application.file_writer import WriteResult, write_files
from cli.application.lookup import TemplateLookup, load_manifest
from cli.data.models import ArchiveEntry
from cli.domain import env_file
from cli.domain.ports import Prompter
from cli.persistence.blob_store import BlobStore
from cli.persistence.document_codec import DocumentCodec
from cli.persistence.file_system import FileSystem


@dataclass
class WriteSampleFiles:
    """Write ``values.env``, ``build.env`` and ``deploy.env`` with defaults.

    Attributes:
        fs: User files.
        codec: YAML codec.
        manifests: Manifest store.
        lookup: Finds local templates.
        prompter: Asks before overwriting files.
    """

    fs: FileSystem
    codec: DocumentCodec
    manifests: BlobStore
    lookup: TemplateLookup
    prompter: Prompter

    def execute(self, name: str, output: Path, force: bool = False) -> WriteResult:
        """Write the sample files of a template.

        Args:
            name: Reference, ID or ID prefix of the template.
            output: Destination folder.
            force: Overwrite existing files without asking.

        Returns:
            The written and skipped files.

        Raises:
            NotFoundError: If the template does not exist.
            CancelledError: If the user cancels because files exist.
        """
        manifest_id, _ = self.lookup.find(name)
        manifest = load_manifest(self.manifests, self.codec, manifest_id)
        entries = [
            ArchiveEntry(file, env_file.render(variables).encode("utf-8"))
            for file, variables in (
                ("values.env", manifest.instantiation),
                ("build.env", manifest.build.variables),
                ("deploy.env", manifest.deploy.variables),
            )
        ]
        return write_files(self.fs, self.prompter, output, entries, force)
