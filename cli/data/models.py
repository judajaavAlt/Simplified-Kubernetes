from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class VariableType(str, Enum):
    """Type of a template variable.

    Attributes:
        STR: Any text.
        INT: Whole number.
        BOOL: ``true`` or ``false``, in lowercase.
        FLOAT: Decimal number.
    """

    STR = "str"
    INT = "int"
    BOOL = "bool"
    FLOAT = "float"


@dataclass(frozen=True)
class Variable:
    """Variable declared by a template.

    Attributes:
        name: Name used in the ``[%name%]`` placeholders.
        type: Declared type.
        default: Default value; always present and of the declared type.
        description: Explanation shown to the user.
    """

    name: str
    type: VariableType
    default: object
    description: str = ""


@dataclass(frozen=True)
class Stage:
    """Build or deploy stage.

    Attributes:
        variables: Variables of the stage.
        commands: Command lines, run in order.
    """

    variables: tuple[Variable, ...] = ()
    commands: tuple[str, ...] = ()


@dataclass(frozen=True)
class LayerSource:
    """Layer declared in ``template.yaml``.

    Attributes:
        origin: File or folder to pack, relative to ``template.yaml``.
        objective: Folder of the layer inside the instantiated project.
    """

    origin: str
    objective: str


@dataclass(frozen=True)
class TemplateSpec:
    """Validated content of a ``template.yaml``.

    Attributes:
        tag: Reference of the template as written by the DevOps.
        layers: Layers in order.
        instantiation: Variables asked when the template is set up.
        build: Build stage.
        deploy: Deploy stage.
        description: General documentation of the template.
        readme: Path of a Markdown file with more documentation, if any.
    """

    tag: str
    layers: tuple[LayerSource, ...]
    instantiation: tuple[Variable, ...]
    build: Stage
    deploy: Stage
    description: str = ""
    readme: str | None = None


@dataclass(frozen=True)
class Prefix:
    """Default location used to complete short references (``work set``).

    Attributes:
        host: Registry host.
        port: Registry port.
        organization: Organization, if the prefix includes it.
        repository: Repository, if the prefix includes it.
    """

    host: str
    port: int
    organization: str | None = None
    repository: str | None = None


@dataclass(frozen=True)
class Reference:
    """Complete template reference ``host:port/organization/repo:tag``.

    Attributes:
        host: Registry host.
        port: Registry port.
        organization: Organization.
        repository: Repository name.
        tag: Tag name.
    """

    host: str
    port: int
    organization: str
    repository: str
    tag: str = "latest"

    @property
    def registry(self) -> str:
        """``host:port`` of the registry."""
        return f"{self.host}:{self.port}"

    @property
    def repository_path(self) -> str:
        """``organization/repo``, the repository name used by the API."""
        return f"{self.organization}/{self.repository}"

    def __str__(self) -> str:
        """Return the reference as ``host:port/organization/repo:tag``.

        Returns:
            The complete reference.
        """
        return f"{self.registry}/{self.repository_path}:{self.tag}"


@dataclass(frozen=True)
class TemplatedFile:
    """File whose content must be processed when the template is set up.

    Attributes:
        path: Path inside the layers, with ``/`` separators.
        variables: Variables used by the content.
    """

    path: str
    variables: tuple[str, ...] = ()


@dataclass(frozen=True)
class Manifest:
    """Manifest of a stored template; its ID is the SHA-256 of its YAML.

    Attributes:
        reference: Reference the template was created with.
        layers: SHA-256 of each layer, in order.
        files: Files whose content uses variables or escapes.
        instantiation: Variables asked when the template is set up.
        build: Build stage.
        deploy: Deploy stage.
        description: General documentation.
        readme: Markdown documentation.
    """

    reference: str
    layers: tuple[str, ...]
    files: tuple[TemplatedFile, ...]
    instantiation: tuple[Variable, ...]
    build: Stage
    deploy: Stage
    description: str = ""
    readme: str = ""


@dataclass(frozen=True)
class InstanceConfig:
    """Content of the ``config.template`` written by ``template setup``.

    Attributes:
        template_id: ID of the manifest the project came from, if known.
        reference: Reference of that manifest.
        instantiation: Instantiation variables whose defaults are the values
            chosen during the setup, so build and deploy can use them.
        build: Build stage.
        deploy: Deploy stage.
    """

    template_id: str | None
    reference: str
    instantiation: tuple[Variable, ...]
    build: Stage
    deploy: Stage


@dataclass(frozen=True)
class ArchiveEntry:
    """File or folder inside a layer.

    Attributes:
        path: Path with ``/`` separators.
        content: Bytes of a file, or None for a folder.
    """

    path: str
    content: bytes | None = None


@dataclass(frozen=True)
class ManifestRecord:
    """Template registered in the local index.

    Attributes:
        id: SHA-256 of the manifest.
        created_at: Moment it was created or pulled.
        size: Size of the manifest plus its layers, in bytes.
        tags: References that point to it; empty for an orphan.
    """

    id: str
    created_at: datetime
    size: int
    tags: tuple[Reference, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Credentials:
    """Session with a registry.

    Attributes:
        registry: ``host:port`` of the registry.
        token: Bearer token.
        nickname: User that logged in.
        secure: True for HTTPS, False for HTTP (``--insecure``).
    """

    registry: str
    token: str
    nickname: str
    secure: bool = True


@dataclass(frozen=True)
class UploadTicket:
    """Answer of the registry to the start of an upload.

    Attributes:
        status: ``started``, or ``exists`` if nothing must be sent.
        upload_id: Session identifier, or None.
        pieces: Number of pieces to send.
        chunk_size: Size of every piece except the last one.
    """

    status: str
    upload_id: str | None
    pieces: int
    chunk_size: int


@dataclass(frozen=True)
class PieceInfo:
    """One piece of a remote blob.

    Attributes:
        index: Position, starting at 0.
        signature: SHA-256 of the piece.
        size: Size in bytes.
    """

    index: int
    signature: str
    size: int


@dataclass(frozen=True)
class DownloadTicket:
    """Answer of the registry to the start of a download.

    Attributes:
        download_id: Session identifier.
        signature: SHA-256 of the blob.
        total_size: Size of the blob in bytes.
        pieces: Pieces in order.
    """

    download_id: str
    signature: str
    total_size: int
    pieces: tuple[PieceInfo, ...]


@dataclass(frozen=True)
class RemoteManifest:
    """Manifest resolved by the registry.

    Attributes:
        signature: SHA-256 of the manifest.
        layers: SHA-256 of its layers, in order.
    """

    signature: str
    layers: tuple[str, ...]
