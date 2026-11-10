"""In-memory fakes of the API contracts, used by the application tests."""
import copy
import itertools
from datetime import datetime, timedelta, timezone

import pytest

from api.data.models import BlobMetadata, Role, User
from api.domain.password_hasher import PasswordHasher
from api.persistence.blob_storage import BlobStorage
from api.persistence.repository.audit_log import AuditLogRepository
from api.persistence.repository.download_session import (
    DownloadSessionRepository,
)
from api.persistence.repository.layer import LayerRepository
from api.persistence.repository.manifest import ManifestRepository
from api.persistence.repository.repo import RepoRepository
from api.persistence.repository.tag import TagRepository
from api.persistence.repository.upload_session import UploadSessionRepository
from api.persistence.repository.user import UserRepository
from api.persistence.repository.user_token import UserTokenRepository


class FakeClock:
    def __init__(self):
        self.current = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


class FakeHasher(PasswordHasher):
    def hash_password(self, password, pepper):
        return f"hash({password}|{pepper.decode()})", "salt"

    def verify_password(self, password, salt, expected_hash, pepper):
        return expected_hash == f"hash({password}|{pepper.decode()})"


class FakeUsers(UserRepository):
    def __init__(self):
        self.items = {}
        self._ids = itertools.count(1)

    def create(self, user):
        user = copy.deepcopy(user)
        user.id = next(self._ids)
        self.items[user.id] = user
        return user.id

    def get_by_id(self, user_id):
        return copy.deepcopy(self.items.get(user_id))

    def get_by_nickname(self, nickname):
        for user in self.items.values():
            if user.nickname == nickname:
                return copy.deepcopy(user)
        return None

    def update(self, user):
        self.items[user.id] = copy.deepcopy(user)

    def list_by_role(self, role):
        return [u for u in self.items.values() if u.role is role]


class FakeTokens(UserTokenRepository):
    def __init__(self):
        self.items = {}

    def create(self, token):
        self.items[token.signature] = copy.deepcopy(token)

    def get_by_signature(self, signature):
        return copy.deepcopy(self.items.get(signature))

    def revoke(self, signature, revoked_at):
        self.items[signature].revoked_at = revoked_at

    def revoke_all_for_user(self, user_id, revoked_at):
        for token in self.items.values():
            if token.user_id == user_id and token.revoked_at is None:
                token.revoked_at = revoked_at


class FakeRepos(RepoRepository):
    def __init__(self):
        self.items = {}
        self._ids = itertools.count(1)

    def create(self, repo):
        repo = copy.deepcopy(repo)
        repo.id = next(self._ids)
        self.items[repo.id] = repo
        return repo.id

    def get_by_id(self, repo_id):
        return copy.deepcopy(self.items.get(repo_id))

    def get_by_name(self, name):
        for repo in self.items.values():
            if repo.name == name:
                return copy.deepcopy(repo)
        return None


class FakeLayers(LayerRepository):
    def __init__(self):
        self.items = {}

    def add(self, layer):
        self.items[(layer.signature, layer.repo_id)] = copy.deepcopy(layer)

    def get(self, signature, repo_id):
        return copy.deepcopy(self.items.get((signature, repo_id)))

    def delete(self, signature, repo_id):
        self.items.pop((signature, repo_id), None)

    def exists_anywhere(self, signature):
        return any(sig == signature for sig, _ in self.items)


class FakeManifests(ManifestRepository):
    def __init__(self):
        self.items = {}

    def add(self, manifest):
        key = (manifest.signature, manifest.repo_id)
        self.items.setdefault(key, copy.deepcopy(manifest))

    def get(self, signature, repo_id):
        return copy.deepcopy(self.items.get((signature, repo_id)))

    def delete(self, signature, repo_id):
        self.items.pop((signature, repo_id), None)

    def references_layer(self, layer_signature, repo_id):
        return any(
            layer_signature in m.layers
            for (_, rid), m in self.items.items()
            if rid == repo_id
        )

    def exists_anywhere(self, signature):
        return any(sig == signature for sig, _ in self.items)


class FakeTags(TagRepository):
    def __init__(self):
        self.items = {}

    def set(self, tag):
        self.items[(tag.repo_id, tag.tag)] = copy.deepcopy(tag)

    def get(self, repo_id, tag):
        return copy.deepcopy(self.items.get((repo_id, tag)))

    def list_by_repo(self, repo_id):
        return [t for (rid, _), t in self.items.items() if rid == repo_id]

    def delete_by_manifest(self, repo_id, manifest_signature):
        for key, tag in list(self.items.items()):
            if key[0] == repo_id and tag.manifest_signature == manifest_signature:
                del self.items[key]


class FakeSessions(UploadSessionRepository, DownloadSessionRepository):
    def __init__(self):
        self.items = {}

    def create(self, session):
        self.items[session.id] = copy.deepcopy(session)

    def get(self, session_id):
        return copy.deepcopy(self.items.get(session_id))

    def update(self, session):
        self.items[session.id] = copy.deepcopy(session)

    def list_open(self):
        from api.data.models import SessionStatus
        return [
            copy.deepcopy(s)
            for s in self.items.values()
            if s.status is SessionStatus.OPEN
        ]


class FakeAudit(AuditLogRepository):
    def __init__(self):
        self.events = []

    def add(self, event):
        self.events.append(event)

    def list_recent(self, limit=100):
        return list(reversed(self.events))[:limit]

    def names(self):
        return [(e.event, e.result) for e in self.events]


class FakeBlobStorage(BlobStorage):
    def __init__(self):
        self.temp = {}
        self.blobs = {}

    def save_temp_piece(self, session_id, signature, content):
        self.temp.setdefault(session_id, {})[signature] = content

    def read_temp_piece(self, session_id, signature):
        return self.temp[session_id][signature]

    def commit(self, session_id, metadata):
        pieces = self.temp.pop(session_id, {})  # empty blobs have no pieces
        self.blobs[metadata.signature] = (copy.deepcopy(metadata), pieces)

    def discard(self, session_id):
        self.temp.pop(session_id, None)

    def exists(self, signature):
        return signature in self.blobs

    def read_metadata(self, signature) -> BlobMetadata | None:
        blob = self.blobs.get(signature)
        return copy.deepcopy(blob[0]) if blob else None

    def read_piece(self, signature, piece_signature):
        return self.blobs[signature][1][piece_signature]

    def delete(self, signature):
        self.blobs.pop(signature, None)


class World:
    """Every fake wired together, plus a user per role."""

    PEPPER = b"pepper"

    def __init__(self):
        self.clock = FakeClock()
        self.hasher = FakeHasher()
        self.users = FakeUsers()
        self.tokens = FakeTokens()
        self.repos = FakeRepos()
        self.layers = FakeLayers()
        self.manifests = FakeManifests()
        self.tags = FakeTags()
        self.uploads = FakeSessions()
        self.downloads = FakeSessions()
        self.audit = FakeAudit()
        self.storage = FakeBlobStorage()
        self._ids = itertools.count(1)

        self.admin = self.add_user("admin", Role.ADMIN)
        self.devops = self.add_user("devops", Role.DEVOPS)
        self.developer = self.add_user("developer", Role.DEVELOPER)

    def new_id(self) -> str:
        return f"id-{next(self._ids)}"

    def add_user(self, nickname, role, password="password", must_change=False):
        password_hash, salt = self.hasher.hash_password(password, self.PEPPER)
        user = User(0, nickname, password_hash, salt, role, must_change)
        user.id = self.users.create(user)
        return user


@pytest.fixture
def world():
    return World()
