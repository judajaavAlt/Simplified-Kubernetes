"""``template setup``: instantiate a template (C-07, C-21 to C-26)."""
from dataclasses import dataclass, replace
from pathlib import Path

from cli.application.file_writer import WriteResult, write_files
from cli.application.lookup import TemplateLookup, load_manifest
from cli.application.yaml_check import check_yaml_files
from cli.data.models import ArchiveEntry, InstanceConfig
from cli.domain import documents, env_file, paths, values, variables
from cli.domain.errors import NotFoundError
from cli.domain.ports import Prompter
from cli.persistence.archiver import Archiver
from cli.persistence.blob_store import BlobStore
from cli.persistence.document_codec import DocumentCodec
from cli.persistence.file_system import FileSystem


DEFAULT_VALUES = Path("values.env")
CONFIG_FILE = "config.template"


@dataclass
class SetupTemplate:
    """Unpack a template, replace its variables and write ``config.template``.

    Attributes:
        fs: User files.
        codec: YAML codec.
        archiver: Unpacks the layers.
        manifests: Manifest store.
        layers: Layer store.
        lookup: Finds local templates.
        prompter: Asks before overwriting files.
    """

    fs: FileSystem
    codec: DocumentCodec
    archiver: Archiver
    manifests: BlobStore
    layers: BlobStore
    lookup: TemplateLookup
    prompter: Prompter

    def execute(
        self,
        name: str,
        output: Path,
        values_path: Path | None = None,
        force: bool = False,
    ) -> WriteResult:
        """Instantiate a local template in a folder.

        Variables are replaced in file and folder names and in the content
        of the files recorded by the manifest. ``config.template`` keeps the
        build and deploy sections plus the chosen values, so build and
        deploy can use them. Every value is validated before anything is
        written.

        Args:
            name: Reference, ID or ID prefix of the template.
            output: Destination folder.
            values_path: ``.env`` file with the values; None reads
                ``values.env`` if it exists and uses the defaults otherwise.
            force: Overwrite existing files without asking.

        Returns:
            The written and skipped files.

        Raises:
            NotFoundError: If the template or the explicit values file do
                not exist.
            ValidationError: If a value is invalid, a path would leave
                the output folder or a YAML file becomes malformed with the
                chosen values.
            CancelledError: If the user cancels because files exist.
        """
        manifest_id, _ = self.lookup.find(name)
        manifest = load_manifest(self.manifests, self.codec, manifest_id)
        chosen = values.resolve(manifest.instantiation, self._overrides(values_path))
        text = {
            v.name: values.format_value(chosen[v.name], v.type)
            for v in manifest.instantiation
        }
        templated = {f.path for f in manifest.files}

        entries: dict[str, ArchiveEntry] = {}
        for layer_id in manifest.layers:
            for entry in self.archiver.unpack(self.layers.read(layer_id)):
                paths.check_relative(entry.path)
                path = paths.check_relative(variables.substitute(entry.path, text))
                content = entry.content
                if content is not None and entry.path in templated:
                    content = variables.substitute(
                        content.decode("utf-8"), text).encode("utf-8")
                entries[path] = ArchiveEntry(path, content)
        check_yaml_files(self.codec, entries.values())

        config = InstanceConfig(
            template_id=manifest_id,
            reference=manifest.reference,
            instantiation=tuple(
                replace(v, default=chosen[v.name]) for v in manifest.instantiation
            ),
            build=manifest.build,
            deploy=manifest.deploy,
        )
        entries[CONFIG_FILE] = ArchiveEntry(
            CONFIG_FILE, self.codec.dump(documents.config_to_document(config))
        )
        return write_files(self.fs, self.prompter, output,
                           list(entries.values()), force)

    def _overrides(self, values_path: Path | None) -> dict[str, str]:
        """Read the values file.

        Args:
            values_path: Explicit file, or None for the default.

        Returns:
            The values as text.

        Raises:
            NotFoundError: If the explicit file does not exist.
        """
        path = values_path or DEFAULT_VALUES
        if not self.fs.exists(path):
            if values_path is not None:
                raise NotFoundError(f"Values file not found: {values_path}")
            return {}
        return env_file.parse(self.fs.read_bytes(path).decode("utf-8"))
