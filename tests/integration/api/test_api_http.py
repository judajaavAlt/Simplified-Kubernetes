import hashlib

import pytest
from fastapi.testclient import TestClient

from api.__main__ import main as api_main
from api.infraestructure.composition import bootstrap_admin, build_app
from api.infraestructure.settings import Settings


pytestmark = pytest.mark.integration

MB = 1024 * 1024
LAYER = b"L" * (2 * MB) + b"tail"  # 3 pieces
MANIFEST = b"tag: org/app\nlayers: []\n"


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def pieces(content: bytes) -> list[bytes]:
    return [content[i:i + MB] for i in range(0, len(content), MB)]


@pytest.fixture
def settings(tmp_path):
    return Settings(
        data_dir=tmp_path / "api-data", pepper=b"test-pepper",
        hash_iterations=1_000,
    )


@pytest.fixture
def client(settings):
    bootstrap_admin(settings, "root", "rootpassword")

    with TestClient(build_app(settings)) as test_client:
        yield test_client


def login(client, nickname, password) -> dict:
    response = client.post(
        "/v1/auth/token", json={"nickname": nickname, "password": password}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def add_user(client, admin, nickname, role, password="definitive1"):
    response = client.post(
        "/v1/users", headers=admin,
        json={"nickname": nickname, "password": "temporal123", "role": role},
    )
    assert response.status_code == 201, response.text
    response = client.post("/v1/auth/password", json={
        "nickname": nickname,
        "current_password": "temporal123",
        "new_password": password,
    })
    assert response.status_code == 204, response.text
    return login(client, nickname, password)


@pytest.fixture
def users(client):
    admin = login(client, "root", "rootpassword")
    return {
        "admin": admin,
        "devops": add_user(client, admin, "devops", "devops"),
        "developer": add_user(client, admin, "dev", "developer"),
    }


def push(client, headers, content, kind="layer", layers=None,
         repository="org/app") -> str:
    response = client.post("/v1/uploads", headers=headers, json={
        "repository": repository, "kind": kind,
        "signature": sha(content), "size": len(content),
        "layers": layers or [],
    })
    assert response.status_code == 200, response.text
    ticket = response.json()

    if ticket["status"] == "exists":
        return sha(content)

    for index, piece in enumerate(pieces(content)):
        response = client.put(
            f"/v1/uploads/{ticket['upload_id']}/chunks/{index}",
            headers={**headers, "X-Chunk-Sha256": sha(piece)},
            content=piece,
        )
        assert response.status_code == 204, response.text

    response = client.post(
        f"/v1/uploads/{ticket['upload_id']}/finish", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["signature"]


def pull(client, headers, signature, repository="org/app") -> bytes:
    response = client.post("/v1/downloads", headers=headers, json={
        "repository": repository, "signature": signature,
    })
    assert response.status_code == 200, response.text
    ticket = response.json()

    content = b""
    for piece in ticket["pieces"]:
        response = client.get(
            f"/v1/downloads/{ticket['download_id']}/chunks/{piece['index']}",
            headers=headers,
        )
        assert response.status_code == 200
        assert sha(response.content) == response.headers["X-Chunk-Sha256"]
        content += response.content

    response = client.post(
        f"/v1/downloads/{ticket['download_id']}/finish",
        headers=headers, json={"signature": sha(content)},
    )
    assert response.json() == {"completed": True}
    return content


# ------------------------------------------------------------------
# Authentication and users
# ------------------------------------------------------------------


def test_requests_without_valid_token_are_rejected(client):
    assert client.post("/v1/uploads", json={}).status_code == 401
    response = client.get(
        "/v1/tags", params={"repository": "org/app"},
        headers={"Authorization": "Bearer nope"},
    )
    assert response.status_code == 401
    assert response.json()["error"] == "authentication_error"


def test_new_user_must_change_password_before_getting_a_token(client):
    admin = login(client, "root", "rootpassword")
    client.post("/v1/users", headers=admin, json={
        "nickname": "ana", "password": "temporal123", "role": "developer",
    })

    response = client.post(
        "/v1/auth/token", json={"nickname": "ana", "password": "temporal123"}
    )

    assert response.status_code == 403
    assert response.json()["error"] == "password_change_required"


def test_only_admin_creates_users(client, users):
    response = client.post("/v1/users", headers=users["devops"], json={
        "nickname": "x-user", "password": "temporal123", "role": "devops",
    })

    assert response.status_code == 403
    assert response.json()["error"] == "permission_denied"


def test_logout_revokes_the_token(client, users):
    assert client.delete(
        "/v1/auth/token", headers=users["developer"]
    ).status_code == 204

    assert client.get(
        "/v1/tags", params={"repository": "org/app"},
        headers=users["developer"],
    ).status_code == 401


def test_invalid_payload_is_a_422(client, users):
    response = client.post("/v1/users", headers=users["admin"], json={
        "nickname": "ana", "password": "temporal123", "role": "king",
    })

    assert response.status_code == 422


# ------------------------------------------------------------------
# Upload: start -> chunk -> finish
# ------------------------------------------------------------------


def test_upload_rejects_bad_chunks_and_can_resume(client, users):
    devops = users["devops"]
    ticket = client.post("/v1/uploads", headers=devops, json={
        "repository": "org/app", "kind": "layer",
        "signature": sha(LAYER), "size": len(LAYER),
    }).json()
    upload = f"/v1/uploads/{ticket['upload_id']}"
    first = pieces(LAYER)[0]

    assert ticket["status"] == "started"
    assert ticket["pieces"] == 3
    assert ticket["chunk_size"] == MB

    bad = client.put(f"{upload}/chunks/0", content=first,
                     headers={**devops, "X-Chunk-Sha256": "f" * 64})
    assert bad.status_code == 422
    assert bad.json()["error"] == "checksum_mismatch"

    good = client.put(f"{upload}/chunks/0", content=first,
                      headers={**devops, "X-Chunk-Sha256": sha(first)})
    assert good.status_code == 204

    status = client.get(upload, headers=devops).json()
    assert status == {"status": "open", "received": [0], "missing": [1, 2]}

    early = client.post(f"{upload}/finish", headers=devops)
    assert early.status_code == 422


def test_chunk_bigger_than_one_megabyte_is_refused(client, users):
    devops = users["devops"]
    ticket = client.post("/v1/uploads", headers=devops, json={
        "repository": "org/app", "kind": "layer",
        "signature": sha(LAYER), "size": len(LAYER),
    }).json()
    big = b"x" * (MB + 1)

    response = client.put(
        f"/v1/uploads/{ticket['upload_id']}/chunks/0", content=big,
        headers={**devops, "X-Chunk-Sha256": sha(big)},
    )

    assert response.status_code == 413


def test_cancel_upload(client, users):
    devops = users["devops"]
    ticket = client.post("/v1/uploads", headers=devops, json={
        "repository": "org/app", "kind": "layer",
        "signature": sha(LAYER), "size": len(LAYER),
    }).json()
    upload = f"/v1/uploads/{ticket['upload_id']}"

    assert client.delete(upload, headers=devops).status_code == 204
    assert client.get(upload, headers=devops).json()["status"] == "cancelled"
    assert client.delete(upload, headers=devops).status_code == 409


def test_developer_cannot_push(client, users):
    response = client.post("/v1/uploads", headers=users["developer"], json={
        "repository": "org/app", "kind": "layer",
        "signature": sha(LAYER), "size": len(LAYER),
    })

    assert response.status_code == 403


def test_unknown_upload_is_404(client, users):
    response = client.get("/v1/uploads/nope", headers=users["devops"])

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


# ------------------------------------------------------------------
# Full push -> tag -> pull -> delete cycle
# ------------------------------------------------------------------


def test_push_tag_pull_and_delete(client, users):
    devops, developer, admin = (
        users["devops"], users["developer"], users["admin"]
    )

    layer = push(client, devops, LAYER)
    manifest = push(client, devops, MANIFEST, kind="manifest", layers=[layer])
    assert push(client, devops, LAYER) == layer  # already stored

    tagged = client.put("/v1/tags", headers=devops, json={
        "repository": "org/app", "tag": "latest", "manifest": manifest,
    })
    assert tagged.status_code == 204

    resolved = client.get("/v1/manifests/resolve", headers=developer, params={
        "repository": "org/app", "reference": "latest",
    }).json()
    assert resolved == {"signature": manifest, "layers": [layer]}

    tags = client.get(
        "/v1/tags", headers=developer, params={"repository": "org/app"}
    ).json()
    assert tags == {"tags": [{"tag": "latest", "manifest": manifest}]}

    assert pull(client, developer, manifest) == MANIFEST
    assert pull(client, developer, layer) == LAYER

    deleted = client.delete("/v1/manifests", headers=devops, params={
        "repository": "org/app", "reference": "latest",
    })
    assert deleted.json() == {"deleted": manifest}

    gone = client.post("/v1/downloads", headers=developer, json={
        "repository": "org/app", "signature": layer,
    })
    assert gone.status_code == 404


def test_admin_sees_active_downloads_and_audit(client, users):
    devops, developer, admin = (
        users["devops"], users["developer"], users["admin"]
    )
    layer = push(client, devops, LAYER)
    ticket = client.post("/v1/downloads", headers=developer, json={
        "repository": "org/app", "signature": layer,
    }).json()

    active = client.get("/v1/downloads", headers=admin).json()
    assert [d["download_id"] for d in active["downloads"]] == [
        ticket["download_id"]
    ]
    assert client.get("/v1/downloads", headers=developer).status_code == 403

    audit = client.get("/v1/audit", headers=admin).json()["events"]
    assert audit[0]["event"] == "download.start"
    assert {"upload.chunk", "upload.finish"} <= {e["event"] for e in audit}

    assert client.post(
        "/v1/admin/cleanup", headers=admin
    ).json() == {"expired": 0}


# ------------------------------------------------------------------
# Server command line (bootstrap of the first admin)
# ------------------------------------------------------------------


def test_create_admin_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EASYK8S_API_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("EASYK8S_API_PEPPER", "pepper")
    monkeypatch.setenv("EASYK8S_API_HASH_ITERATIONS", "1000")

    code = api_main(
        ["create-admin", "--nickname", "root", "--password", "rootpassword"]
    )

    assert code == 0
    assert "root" in capsys.readouterr().out
    assert api_main(
        ["create-admin", "--nickname", "other", "--password", "rootpassword"]
    ) == 1


def test_settings_generate_and_keep_a_pepper(tmp_path, monkeypatch):
    monkeypatch.setenv("EASYK8S_API_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("EASYK8S_API_PEPPER", raising=False)

    first = Settings.from_env()
    second = Settings.from_env()

    assert len(first.pepper) >= 32
    assert first.pepper == second.pepper
