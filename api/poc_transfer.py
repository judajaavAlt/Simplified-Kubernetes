"""
Proof of concept: upload a file to the easyK8s API in 1 MB pieces and
download it back, verifying SHA-256 per piece and for the whole file.

    python -m api.poc_transfer upload FILE           -> prints its sha256
    python -m api.poc_transfer download SHA256 --out FILE
    python -m api.poc_transfer roundtrip FILE        upload + download

Add --embedded to run the API in-process (no server needed). Its data is
kept in --data (default: <temp>/easyk8s-poc), so a file uploaded in one
run can be downloaded in a later run. Without --embedded it talks to a
running API at --url (python -m api serve); the user must be devops or
admin to upload.
"""
import argparse
import hashlib
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import httpx


MAX_RETRIES = 3


def sha256(content: bytes) -> str:
    """Compute the SHA-256 of some content.

    Args:
        content: Bytes to hash.

    Returns:
        The digest in hexadecimal.
    """
    return hashlib.sha256(content).hexdigest()


def check(response: httpx.Response, *expected: int) -> httpx.Response:
    """Stop the program if a response has an unexpected status code.

    Args:
        response: HTTP response.
        *expected: Accepted status codes.

    Returns:
        The same response.

    Raises:
        SystemExit: If the status code is not expected.
    """
    if response.status_code not in expected:
        raise SystemExit(
            f"HTTP {response.status_code} on {response.request.method} "
            f"{response.request.url.path}: {response.text}"
        )
    return response


def login(client: httpx.Client, user: str, password: str) -> None:
    """Get a token and add it to every following request of the client.

    Args:
        client: HTTP client pointing at the API.
        user: Nickname.
        password: Password.
    """
    response = check(client.post(
        "/v1/auth/token", json={"nickname": user, "password": password}
    ), 200)
    client.headers["Authorization"] = f"Bearer {response.json()['token']}"
    print(f"[login] logged in as '{user}'")


def upload(client: httpx.Client, repository: str, content: bytes) -> str:
    """Upload content as a layer: start, send every piece, finish.

    Each piece is sent with its SHA-256 and retried up to
    ``MAX_RETRIES`` times on a checksum error.

    Args:
        client: Authenticated HTTP client.
        repository: Destination repository, ``<organization>/<repo>``.
        content: Bytes to upload.

    Returns:
        SHA-256 of the stored content.
    """
    signature = sha256(content)

    # 1. Start: announce the file.
    ticket = check(client.post("/v1/uploads", json={
        "repository": repository,
        "kind": "layer",
        "signature": signature,
        "size": len(content),
    }), 200).json()

    if ticket["status"] == "exists":
        print(f"[upload] already stored, nothing to send ({signature[:12]}...)")
        return signature

    upload_id, chunk_size = ticket["upload_id"], ticket["chunk_size"]
    print(f"[upload] started: {ticket['pieces']} piece(s) of up to "
          f"{chunk_size} bytes")

    # 2. Chunks: each piece goes with its own SHA-256.
    for index in range(ticket["pieces"]):
        piece = content[index * chunk_size:(index + 1) * chunk_size]

        for attempt in range(1, MAX_RETRIES + 1):
            response = client.put(
                f"/v1/uploads/{upload_id}/chunks/{index}",
                content=piece,
                headers={"X-Chunk-Sha256": sha256(piece)},
            )
            if response.status_code == 204:
                break
            if response.status_code != 422 or attempt == MAX_RETRIES:
                client.delete(f"/v1/uploads/{upload_id}")  # cancel
                check(response, 204)

        print(f"[upload] piece {index + 1}/{ticket['pieces']} ok")

    # 3. Finish: the API verifies the whole file once.
    result = check(
        client.post(f"/v1/uploads/{upload_id}/finish"), 200
    ).json()
    print(f"[upload] finished, server verified sha256 {result['signature']}")
    return result["signature"]


def download(client: httpx.Client, repository: str, signature: str) -> bytes:
    # 1. Start: get the ordered list of pieces.
    """Download a blob piece by piece, verifying every piece.

    Args:
        client: Authenticated HTTP client.
        repository: Repository, ``<organization>/<repo>``.
        signature: SHA-256 of the blob.

    Returns:
        The rebuilt content.

    Raises:
        SystemExit: If a piece does not match its SHA-256.
    """
    ticket = check(client.post("/v1/downloads", json={
        "repository": repository, "signature": signature,
    }), 200).json()
    download_id = ticket["download_id"]
    print(f"[download] started: {len(ticket['pieces'])} piece(s)")

    # 2. Chunks: verify every piece against the expected SHA-256.
    parts = []
    for piece in ticket["pieces"]:
        response = check(client.get(
            f"/v1/downloads/{download_id}/chunks/{piece['index']}"
        ), 200)

        if sha256(response.content) != piece["signature"]:
            raise SystemExit(f"Piece {piece['index']} is corrupted")

        parts.append(response.content)
        print(f"[download] piece {piece['index'] + 1}/"
              f"{len(ticket['pieces'])} ok")

    content = b"".join(parts)

    # 3. Finish: report what was rebuilt; the API logs the result.
    result = check(client.post(
        f"/v1/downloads/{download_id}/finish",
        json={"signature": sha256(content)},
    ), 200).json()
    print(f"[download] finished, server confirms: {result['completed']}")
    return content


@contextmanager
def embedded_api(data_dir: Path, user: str, password: str):
    """Run the real API in-process on a data folder kept between runs.

    The admin is created on the first run.

    Args:
        data_dir: Data folder of the embedded API.
        user: Nickname of the admin.
        password: Password of the admin.

    Yields:
        A test client that talks to the in-process API.
    """
    from fastapi.testclient import TestClient

    from api.domain.errors import Conflict
    from api.infraestructure.composition import bootstrap_admin, build_app
    from api.infraestructure.settings import Settings

    settings = Settings(
        data_dir=data_dir, pepper=b"poc-pepper", hash_iterations=1_000
    )

    try:
        bootstrap_admin(settings, user, password)
        print(f"[embedded] created admin '{user}'")
    except Conflict:
        pass  # admin created in a previous run

    print(f"[embedded] API running in-process, data in {data_dir}")

    with TestClient(build_app(settings)) as client:
        yield client


def save(path: Path, content: bytes) -> None:
    """Write content to a file and report it.

    Args:
        path: Destination file.
        content: Bytes to write.
    """
    path.write_bytes(content)
    print(f"[result] saved {len(content)} bytes to {path}")


def main() -> int:
    """Run the proof of concept command line.

    Returns:
        The exit code: 0 on success, 1 if the downloaded file differs.
    """
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--url", default="http://127.0.0.1:8000")
    common.add_argument("--user", default="root")
    common.add_argument("--password", default="rootpassword")
    common.add_argument("--repository", default="poc/files")
    common.add_argument("--embedded", action="store_true",
                        help="no server needed: run the API in-process")
    common.add_argument(
        "--data", type=Path,
        default=Path(tempfile.gettempdir()) / "easyk8s-poc",
        help="data folder of the embedded API (kept between runs)",
    )

    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("\n\n", 1)[1],
    )
    commands = parser.add_subparsers(dest="command", required=True)

    up = commands.add_parser("upload", parents=[common])
    up.add_argument("file", type=Path)

    down = commands.add_parser("download", parents=[common])
    down.add_argument("signature", help="sha256 printed by 'upload'")
    down.add_argument("--out", type=Path, required=True)

    both = commands.add_parser("roundtrip", parents=[common])
    both.add_argument("file", type=Path)
    both.add_argument("--out", type=Path,
                      help="default: <file>.downloaded")

    args = parser.parse_args()

    clients = (
        embedded_api(args.data, args.user, args.password)
        if args.embedded
        else httpx.Client(base_url=args.url, timeout=60)
    )

    with clients as client:
        login(client, args.user, args.password)

        if args.command == "download":
            save(args.out, download(client, args.repository, args.signature))
            return 0

        content = args.file.read_bytes()
        print(f"[file] {args.file} ({len(content)} bytes, "
              f"sha256 {sha256(content)})")
        signature = upload(client, args.repository, content)

        if args.command == "upload":
            print(f"[result] uploaded; download it with:\n  python -m "
                  f"api.poc_transfer download {signature} --out <file>"
                  f"{' --embedded' if args.embedded else ''}")
            return 0

        downloaded = download(client, args.repository, signature)

    out = args.out or args.file.with_name(args.file.name + ".downloaded")
    save(out, downloaded)
    same = downloaded == content
    print(f"[result] identical to the original: {same}")
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
