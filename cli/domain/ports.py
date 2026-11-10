"""Ports to external services; the implementations are infrastructure."""
from abc import ABC, abstractmethod
from pathlib import Path

from cli.data.models import DownloadTicket, RemoteManifest, UploadTicket


class RegistryClient(ABC):
    """Client of one registry API, bound to an optional bearer token.

    Every method raises :class:`~cli.domain.errors.RegistryError` (or a
    subclass) when the registry refuses the request or cannot be reached.
    """

    @abstractmethod
    def login(self, nickname: str, password: str) -> str:
        """Get a new token.

        Args:
            nickname: User name.
            password: Password.

        Returns:
            The token.

        Raises:
            PasswordChangeRequiredError: If the password must be changed.
        """

    @abstractmethod
    def change_password(self, nickname: str, current: str, new: str) -> None:
        """Change a password.

        Args:
            nickname: User name.
            current: Password in use.
            new: New password.
        """

    @abstractmethod
    def logout(self) -> None:
        """Revoke the token of the client."""

    @abstractmethod
    def start_upload(
        self,
        repository: str,
        kind: str,
        signature: str,
        size: int,
        layers: tuple[str, ...] = (),
    ) -> UploadTicket:
        """Announce a blob to upload.

        Args:
            repository: ``organization/repo``.
            kind: ``layer`` or ``manifest``.
            signature: SHA-256 of the blob.
            size: Size of the blob in bytes.
            layers: For a manifest, the SHA-256 of its layers.

        Returns:
            The upload ticket.
        """

    @abstractmethod
    def upload_chunk(
        self, upload_id: str, index: int, signature: str, content: bytes
    ) -> None:
        """Send one piece.

        Args:
            upload_id: Upload session.
            index: Position of the piece.
            signature: SHA-256 of the piece.
            content: Bytes of the piece.

        Raises:
            ChecksumRejectedError: If the registry rejected the checksum.
        """

    @abstractmethod
    def finish_upload(self, upload_id: str) -> str:
        """Ask the registry to verify and store the blob.

        Args:
            upload_id: Upload session.

        Returns:
            SHA-256 of the stored blob.
        """

    @abstractmethod
    def cancel_upload(self, upload_id: str) -> None:
        """Cancel an upload.

        Args:
            upload_id: Upload session.
        """

    @abstractmethod
    def set_tag(self, repository: str, tag: str, manifest: str) -> None:
        """Point a remote tag to a manifest.

        Args:
            repository: ``organization/repo``.
            tag: Tag name.
            manifest: SHA-256 of the manifest.
        """

    @abstractmethod
    def resolve(self, repository: str, reference: str) -> RemoteManifest:
        """Resolve a tag or ID to a manifest and its layers.

        Args:
            repository: ``organization/repo``.
            reference: Tag or manifest SHA-256.

        Returns:
            The manifest signature and layers.
        """

    @abstractmethod
    def start_download(self, repository: str, signature: str) -> DownloadTicket:
        """Open a download.

        Args:
            repository: ``organization/repo``.
            signature: SHA-256 of the blob.

        Returns:
            The download ticket with the piece list.
        """

    @abstractmethod
    def download_chunk(self, download_id: str, index: int) -> bytes:
        """Download one piece.

        Args:
            download_id: Download session.
            index: Position of the piece.

        Returns:
            Bytes of the piece.
        """

    @abstractmethod
    def finish_download(self, download_id: str, signature: str) -> bool:
        """Report the SHA-256 rebuilt by the client.

        Args:
            download_id: Download session.
            signature: SHA-256 of the rebuilt blob.

        Returns:
            True if the registry confirms it.
        """

    @abstractmethod
    def delete_manifest(self, repository: str, reference: str) -> str:
        """Delete a remote manifest with its tags.

        Args:
            repository: ``organization/repo``.
            reference: Tag or manifest SHA-256.

        Returns:
            SHA-256 of the deleted manifest.
        """


class RegistryConnector(ABC):
    """Creates registry clients."""

    @abstractmethod
    def connect(
        self, registry: str, secure: bool = True, token: str | None = None
    ) -> RegistryClient:
        """Create a client for a registry.

        Args:
            registry: ``host:port``.
            secure: True for HTTPS, False for HTTP.
            token: Bearer token, or None before logging in.

        Returns:
            The client.
        """


class CommandRunner(ABC):
    """Runs external programs of build and deploy commands."""

    @abstractmethod
    def system(self) -> str:
        """Name the operating system.

        Returns:
            ``Windows``, ``Linux`` or another ``platform.system()`` value.
        """

    @abstractmethod
    def environment(self) -> dict[str, str]:
        """Return the environment the commands start with.

        Returns:
            A copy of the process environment.
        """

    @abstractmethod
    def check_admin(self) -> None:
        """Ensure programs can run with administrator rights (``--admin``).

        Raises:
            CliError: If that is not possible.
        """

    @abstractmethod
    def run(
        self, argv: list[str], cwd: Path, env: dict[str, str], admin: bool
    ) -> int:
        """Run a program without a shell and wait for it.

        Args:
            argv: Program and its arguments.
            cwd: Working directory.
            env: Environment variables.
            admin: Run with administrator rights.

        Returns:
            The exit code.

        Raises:
            CommandFailedError: If the program does not exist.
        """


class Prompter(ABC):
    """Asks the user when a decision is needed."""

    @abstractmethod
    def choose_conflict_action(self, paths: list[str]) -> str:
        """Ask what to do with files that already exist (C-43).

        Args:
            paths: Files that would be overwritten.

        Returns:
            ``all`` to overwrite every file, ``one`` to decide file by file
            or ``cancel``.
        """

    @abstractmethod
    def confirm_overwrite(self, path: str) -> bool:
        """Ask whether to overwrite one file.

        Args:
            path: File that already exists.

        Returns:
            True to overwrite it.
        """

    @abstractmethod
    def ask_new_password(self) -> str:
        """Ask a new password when the registry requires a change.

        Returns:
            The new password.
        """
