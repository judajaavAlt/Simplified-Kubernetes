from collections.abc import Callable

import httpx

from cli.data.models import DownloadTicket, PieceInfo, RemoteManifest, UploadTicket
from cli.domain.errors import (
    ChecksumRejectedError,
    PasswordChangeRequiredError,
    RegistryError,
)
from cli.domain.ports import RegistryClient, RegistryConnector


def _default_factory(base_url: str) -> httpx.Client:
    """Create an HTTP client for a registry.

    Args:
        base_url: ``http(s)://host:port``.

    Returns:
        The client.
    """
    return httpx.Client(base_url=base_url, timeout=60)


class HttpRegistryConnector(RegistryConnector):
    """Creates clients of the easyK8s registry API (``/v1``).

    Attributes:
        factory: Creates the underlying HTTP client from a base URL.
    """

    def __init__(self, factory: Callable[[str], httpx.Client] = _default_factory):
        """Create the connector.

        Args:
            factory: Creates an HTTP client; tests pass a FastAPI
                ``TestClient``.
        """
        self.factory = factory

    def connect(self, registry, secure=True, token=None) -> RegistryClient:
        """Create a client for a registry.

        Args:
            registry: ``host:port``.
            secure: True for HTTPS, False for HTTP.
            token: Bearer token, or None.

        Returns:
            The client.
        """
        scheme = "https" if secure else "http"
        return HttpRegistryClient(
            self.factory(f"{scheme}://{registry}"), registry, token
        )


class HttpRegistryClient(RegistryClient):
    """Client of the registry HTTP API.

    Error responses ``{"error": code, "detail": text}`` become
    :class:`~cli.domain.errors.RegistryError` subclasses.

    Attributes:
        http: HTTP client with the registry base URL.
        registry: ``host:port``, used in the messages.
        token: Bearer token, or None.
    """

    def __init__(self, http: httpx.Client, registry: str, token: str | None):
        """Create the client.

        Args:
            http: HTTP client with the registry base URL.
            registry: ``host:port``.
            token: Bearer token, or None.
        """
        self.http, self.registry, self.token = http, registry, token

    def _request(self, method: str, url: str, expected=(200,), **kwargs):
        """Send a request and check its status.

        Args:
            method: HTTP method.
            url: Path under the base URL.
            expected: Accepted status codes.
            **kwargs: Arguments for ``httpx.Client.request``.

        Returns:
            The response.

        Raises:
            RegistryError: If the registry is unreachable or answers with
                an error.
        """
        headers = kwargs.pop("headers", {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            response = self.http.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as error:
            raise RegistryError(f"Cannot reach {self.registry}: {error}") from None
        if response.status_code in expected:
            return response
        try:
            body = response.json()
            code, detail = body.get("error", ""), body.get("detail", "")
        except ValueError:
            code, detail = "", response.text
        if code == "password_change_required":
            raise PasswordChangeRequiredError(detail)
        if code == "checksum_mismatch" and "/chunks/" in url:
            raise ChecksumRejectedError(detail)
        raise RegistryError(
            f"{self.registry} answered {response.status_code} {code}: {detail}"
        )

    def login(self, nickname, password) -> str:
        """Get a new token.

        Args:
            nickname: User name.
            password: Password.

        Returns:
            The token.
        """
        response = self._request("POST", "/v1/auth/token",
                                 json={"nickname": nickname, "password": password})
        return response.json()["token"]

    def change_password(self, nickname, current, new) -> None:
        """Change a password.

        Args:
            nickname: User name.
            current: Password in use.
            new: New password.
        """
        self._request("POST", "/v1/auth/password", (204,), json={
            "nickname": nickname, "current_password": current,
            "new_password": new})

    def logout(self) -> None:
        """Revoke the token of the client."""
        self._request("DELETE", "/v1/auth/token", (204,))

    def start_upload(self, repository, kind, signature, size, layers=()):
        """Announce a blob to upload.

        Args:
            repository: ``organization/repo``.
            kind: ``layer`` or ``manifest``.
            signature: SHA-256 of the blob.
            size: Size in bytes.
            layers: For a manifest, its layers.

        Returns:
            The upload ticket.
        """
        body = self._request("POST", "/v1/uploads", json={
            "repository": repository, "kind": kind, "signature": signature,
            "size": size, "layers": list(layers)}).json()
        return UploadTicket(body["status"], body["upload_id"], body["pieces"],
                            body["chunk_size"])

    def upload_chunk(self, upload_id, index, signature, content) -> None:
        """Send one piece.

        Args:
            upload_id: Upload session.
            index: Position of the piece.
            signature: SHA-256 of the piece.
            content: Bytes of the piece.
        """
        self._request("PUT", f"/v1/uploads/{upload_id}/chunks/{index}", (204,),
                      content=content, headers={"X-Chunk-Sha256": signature})

    def finish_upload(self, upload_id) -> str:
        """Ask the registry to verify and store the blob.

        Args:
            upload_id: Upload session.

        Returns:
            SHA-256 of the stored blob.
        """
        return self._request(
            "POST", f"/v1/uploads/{upload_id}/finish").json()["signature"]

    def cancel_upload(self, upload_id) -> None:
        """Cancel an upload.

        Args:
            upload_id: Upload session.
        """
        self._request("DELETE", f"/v1/uploads/{upload_id}", (204,))

    def set_tag(self, repository, tag, manifest) -> None:
        """Point a remote tag to a manifest.

        Args:
            repository: ``organization/repo``.
            tag: Tag name.
            manifest: SHA-256 of the manifest.
        """
        self._request("PUT", "/v1/tags", (204,), json={
            "repository": repository, "tag": tag, "manifest": manifest})

    def resolve(self, repository, reference) -> RemoteManifest:
        """Resolve a tag or ID to a manifest and its layers.

        Args:
            repository: ``organization/repo``.
            reference: Tag or manifest SHA-256.

        Returns:
            The manifest signature and layers.
        """
        body = self._request("GET", "/v1/manifests/resolve", params={
            "repository": repository, "reference": reference}).json()
        return RemoteManifest(body["signature"], tuple(body["layers"]))

    def start_download(self, repository, signature) -> DownloadTicket:
        """Open a download.

        Args:
            repository: ``organization/repo``.
            signature: SHA-256 of the blob.

        Returns:
            The download ticket.
        """
        body = self._request("POST", "/v1/downloads", json={
            "repository": repository, "signature": signature}).json()
        return DownloadTicket(
            body["download_id"], body["signature"], body["total_size"],
            tuple(PieceInfo(p["index"], p["signature"], p["size"])
                  for p in body["pieces"]),
        )

    def download_chunk(self, download_id, index) -> bytes:
        """Download one piece.

        Args:
            download_id: Download session.
            index: Position of the piece.

        Returns:
            Bytes of the piece.
        """
        return self._request(
            "GET", f"/v1/downloads/{download_id}/chunks/{index}").content

    def finish_download(self, download_id, signature) -> bool:
        """Report the SHA-256 rebuilt by the client.

        Args:
            download_id: Download session.
            signature: SHA-256 of the rebuilt blob.

        Returns:
            True if the registry confirms it.
        """
        return self._request(
            "POST", f"/v1/downloads/{download_id}/finish",
            json={"signature": signature}).json()["completed"]

    def delete_manifest(self, repository, reference) -> str:
        """Delete a remote manifest with its tags.

        Args:
            repository: ``organization/repo``.
            reference: Tag or manifest SHA-256.

        Returns:
            SHA-256 of the deleted manifest.
        """
        return self._request("DELETE", "/v1/manifests", params={
            "repository": repository, "reference": reference}).json()["deleted"]
