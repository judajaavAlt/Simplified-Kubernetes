"""``template create`` (C-07, C-10 to C-15)."""
import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from cli.application.lookup import current_prefix
from cli.application.yaml_check import check_yaml_files
from cli.data.models import ArchiveEntry, Manifest, Reference, TemplatedFile
from cli.domain import documents, ignore_rules, paths, references, values, variables
from cli.domain.errors import NotFoundError
from cli.domain.template_spec import parse_template
from cli.persistence.archiver import Archiver
from cli.persistence.blob_store import BlobStore
from cli.persistence.document_codec import DocumentCodec
from cli.persistence.file_system import FileSystem
from cli.persistence.settings_store import SettingsStore
from cli.persistence.template_index import TemplateIndex


IGNORE_FILES = (".templateignore", ".gitignore")


@dataclass(frozen=True)
class CreateResult:
    """Outcome of ``template create``.

    Attributes:
        manifest_id: SHA-256 of the stored manifest.
        reference: Reference the template was tagged with.
        layers: SHA-256 of each layer.
    """

    manifest_id: str
    reference: Reference
    layers: tuple[str, ...]


@dataclass
class CreateTemplate:
    """Build a template from a ``template.yaml`` and store it locally.

    Attributes:
        fs: User files.
        codec: YAML codec.
        archiver: Packs the layers.
        manifests: Manifest store.
        layers: Layer store.
        index: Local index.
        settings: Settings with the default prefix.
        clock: Returns the current moment.
    """

    fs: FileSystem
    codec: DocumentCodec
    archiver: Archiver
    manifests: BlobStore
    layers: BlobStore
    index: TemplateIndex
    settings: SettingsStore
    clock: Callable[[], datetime]

    def execute(
        self, template_path: Path, ignore_path: Path | None = None
    ) -> CreateResult:
        """Validate, pack and register a template.

        Paths in ``template.yaml`` are relative to its folder. The exclusion
        rules come from ``ignore_path`` or, by default, ``.templateignore``
        or else ``.gitignore`` next to ``template.yaml``; without any of
        them nothing is excluded. The template is tagged with its reference;
        a repeated tag moves to the new manifest and the old one stays as an
        orphan. Every ``.yaml``/``.yml`` file must be well formed once its
        placeholders take their defaults; Go/Helm templates are skipped.

        Args:
            template_path: Path of ``template.yaml``.
            ignore_path: Explicit ignore file, or None for the default.

        Returns:
            The manifest ID, the reference and the layers.

        Raises:
            NotFoundError: If ``template.yaml`` or the explicit ignore file
                do not exist.
            ValidationError: With every problem of ``template.yaml``, or
                with every malformed YAML file of the layers.
        """
        base = template_path.parent
        spec = parse_template(
            self.codec.load(self.fs.read_bytes(template_path)),
            lambda relative: self.fs.exists(base / relative),
        )
        reference = references.parse(spec.tag, current_prefix(self.settings))
        rules, rules_base = self._rules(base, ignore_path)
        names = [variable.name for variable in spec.instantiation]
        layers = [
            self._entries(base / layer.origin, layer.objective, rules, rules_base)
            for layer in spec.layers
        ]
        defaults = {
            v.name: values.format_value(v.default, v.type) for v in spec.instantiation
        }
        check_yaml_files(self.codec, (
            _with_values(entry, defaults) for entries in layers for entry in entries
        ))

        layer_ids, files, total = [], [], 0
        for entries in layers:
            files.extend(_templated(entries, names))
            content = self.archiver.pack(entries)
            layer_id = _sha256(content)
            if not self.layers.exists(layer_id):
                self.layers.save(layer_id, content)
            layer_ids.append(layer_id)
            total += len(content)

        readme = ""
        if spec.readme:
            readme = self.fs.read_bytes(base / spec.readme).decode("utf-8")
        manifest = Manifest(
            reference=str(reference),
            layers=tuple(layer_ids),
            files=tuple(files),
            instantiation=spec.instantiation,
            build=spec.build,
            deploy=spec.deploy,
            description=spec.description,
            readme=readme,
        )
        content = self.codec.dump(documents.manifest_to_document(manifest))
        manifest_id = _sha256(content)
        if not self.manifests.exists(manifest_id):
            self.manifests.save(manifest_id, content)
        self.index.add_manifest(
            manifest_id, manifest.layers, total + len(content), self.clock()
        )
        self.index.set_tag(reference, manifest_id)
        return CreateResult(manifest_id, reference, manifest.layers)

    def _rules(self, base: Path, ignore_path: Path | None):
        """Load the exclusion rules.

        Args:
            base: Folder of ``template.yaml``.
            ignore_path: Explicit ignore file, or None.

        Returns:
            The rules and the folder they are relative to.

        Raises:
            NotFoundError: If the explicit ignore file does not exist.
        """
        if ignore_path is not None:
            if not self.fs.exists(ignore_path):
                raise NotFoundError(f"Ignore file not found: {ignore_path}")
            candidates = [ignore_path]
        else:
            candidates = [base / name for name in IGNORE_FILES]
        for candidate in candidates:
            if self.fs.exists(candidate):
                text = self.fs.read_bytes(candidate).decode("utf-8")
                return ignore_rules.parse(text), candidate.parent
        return [], base

    def _entries(self, origin: Path, objective: str, rules, rules_base):
        """List the files and folders of one layer, in sorted order.

        Args:
            origin: File or folder to pack.
            objective: Folder of the layer inside the project.
            rules: Exclusion rules.
            rules_base: Folder the rules are relative to.

        Returns:
            The archive entries.
        """
        if not self.fs.is_dir(origin):
            path = paths.join(objective, origin.name)
            return [ArchiveEntry(path, self.fs.read_bytes(origin))]
        entries = []

        def walk(folder: Path) -> None:
            """Add the content of a folder recursively.

            Args:
                folder: Folder to walk.
            """
            for name in self.fs.list_dir(folder):
                child = folder / name
                is_dir = self.fs.is_dir(child)
                if _excluded(child, is_dir, rules, rules_base):
                    continue
                path = paths.join(objective, child.relative_to(origin).as_posix())
                if is_dir:
                    entries.append(ArchiveEntry(path))
                    walk(child)
                else:
                    entries.append(ArchiveEntry(path, self.fs.read_bytes(child)))

        walk(origin)
        return entries


def _excluded(path: Path, is_dir: bool, rules, rules_base: Path) -> bool:
    """Apply the exclusion rules to a path.

    Args:
        path: Path to check.
        is_dir: True if it is a folder.
        rules: Exclusion rules.
        rules_base: Folder the rules are relative to.

    Returns:
        True if the path is excluded; paths outside ``rules_base`` never are.
    """
    if not rules:
        return False
    try:
        relative = path.relative_to(rules_base).as_posix()
    except ValueError:
        return False
    return ignore_rules.is_excluded(relative, is_dir, rules)


def _with_values(entry: ArchiveEntry, text_values: dict[str, str]) -> ArchiveEntry:
    """Replace the placeholders of a text file, to check it as it will be.

    Args:
        entry: Entry of a layer.
        text_values: Value of each variable, as text.

    Returns:
        The entry with its placeholders replaced; folders and binary files
        are returned unchanged.
    """
    if entry.content is None or not variables.is_text(entry.content):
        return entry
    text = variables.substitute(entry.content.decode("utf-8"), text_values)
    return ArchiveEntry(entry.path, text.encode("utf-8"))


def _templated(entries, names) -> list[TemplatedFile]:
    """Find the files whose content changes when the template is set up.

    Args:
        entries: Entries of a layer.
        names: Names of the instantiation variables.

    Returns:
        Text files that use variables or have escaped placeholders.
    """
    result = []
    for entry in entries:
        if entry.content is None or not variables.is_text(entry.content):
            continue
        text = entry.content.decode("utf-8")
        if variables.needs_processing(text, names):
            result.append(TemplatedFile(entry.path, variables.uses(text, names)))
    return result


def _sha256(content: bytes) -> str:
    """Compute the SHA-256 of some content.

    Args:
        content: Bytes to hash.

    Returns:
        The digest in hexadecimal.
    """
    return hashlib.sha256(content).hexdigest()
