import json
from datetime import datetime

from api.data.models import (
    AuditEvent,
    BlobKind,
    DownloadSession,
    Layer,
    Manifest,
    Repo,
    Role,
    SessionStatus,
    Tag,
    UploadSession,
    User,
    UserToken,
)
from api.infraestructure.sqlite.database import SQLiteDatabase
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


def _to_text(value: datetime | None) -> str | None:
    """Serialize a moment as ISO 8601 text.

    Args:
        value: Moment to store, or None.

    Returns:
        The ISO 8601 text, or None.
    """
    return value.isoformat() if value is not None else None


def _to_datetime(value: str | None) -> datetime | None:
    """Parse a moment stored as ISO 8601 text.

    Args:
        value: Stored text, or None.

    Returns:
        The moment, or None.
    """
    return datetime.fromisoformat(value) if value is not None else None


# ------------------------------------------------------------------
# Users and tokens
# ------------------------------------------------------------------


def _user(row) -> User | None:
    """Convert a database row into a user.

    Args:
        row: Row returned by SQLite, or None.

    Returns:
        The user, or None if there is no row.
    """
    if row is None:
        return None

    return User(
        id=row["id"],
        nickname=row["nickname"],
        password=row["password"],
        salt=row["salt"],
        role=Role(row["role"]),
        must_change_password=bool(row["must_change_password"]),
    )


class SQLiteUserRepository(UserRepository):
    """SQLite implementation of :class:`~api.persistence.repository.user.UserRepository`.

    Attributes:
        database: Database used for every operation.
    """

    def __init__(self, database: SQLiteDatabase):
        """Create the repository.

        Args:
            database: Database used for every operation.
        """
        self.database = database

    def create(self, user: User) -> int:
        """Persist a new user.

        Args:
            user: User to store; its ``id`` is ignored.

        Returns:
            The identifier assigned to the user.
        """
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users
                    (nickname, password, salt, role, must_change_password)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user.nickname, user.password, user.salt,
                 user.role.value, int(user.must_change_password)),
            )
            return cursor.lastrowid

    def get_by_id(self, user_id: int) -> User | None:
        """Find a user by identifier.

        Args:
            user_id: User identifier.

        Returns:
            The user, or None if it does not exist.
        """
        with self.database.connect() as connection:
            return _user(connection.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone())

    def get_by_nickname(self, nickname: str) -> User | None:
        """Find a user by nickname.

        Args:
            nickname: Login name.

        Returns:
            The user, or None if it does not exist.
        """
        with self.database.connect() as connection:
            return _user(connection.execute(
                "SELECT * FROM users WHERE nickname = ?", (nickname,)
            ).fetchone())

    def update(self, user: User) -> None:
        """Persist the password, salt, role and password flag of a user.

        Args:
            user: User with the new values.
        """
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE users
                SET nickname = ?, password = ?, salt = ?, role = ?,
                    must_change_password = ?
                WHERE id = ?
                """,
                (user.nickname, user.password, user.salt, user.role.value,
                 int(user.must_change_password), user.id),
            )

    def list_by_role(self, role: Role) -> list[User]:
        """List the users that have a role.

        Args:
            role: Role to filter by.

        Returns:
            Every user with that role.
        """
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM users WHERE role = ? ORDER BY id", (role.value,)
            ).fetchall()
            return [_user(row) for row in rows]


def _token(row) -> UserToken | None:
    """Convert a database row into a token.

    Args:
        row: Row returned by SQLite, or None.

    Returns:
        The token, or None if there is no row.
    """
    if row is None:
        return None

    return UserToken(
        signature=row["signature"],
        user_id=row["user_id"],
        created_at=_to_datetime(row["created_at"]),
        expires_at=_to_datetime(row["expires_at"]),
        revoked_at=_to_datetime(row["revoked_at"]),
    )


class SQLiteUserTokenRepository(UserTokenRepository):
    """SQLite implementation of :class:`~api.persistence.repository.user_token.UserTokenRepository`.

    Attributes:
        database: Database used for every operation.
    """

    def __init__(self, database: SQLiteDatabase):
        """Create the repository.

        Args:
            database: Database used for every operation.
        """
        self.database = database

    def create(self, token: UserToken) -> None:
        """Persist a newly issued token.

        Args:
            token: Token whose ``signature`` is the hash of the raw token.
        """
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO user_tokens
                    (signature, user_id, created_at, expires_at, revoked_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (token.signature, token.user_id, _to_text(token.created_at),
                 _to_text(token.expires_at), _to_text(token.revoked_at)),
            )

    def get_by_signature(self, signature: str) -> UserToken | None:
        """Find a token by its stored hash.

        Args:
            signature: SHA-256 of the raw token.

        Returns:
            The token, or None if it does not exist.
        """
        with self.database.connect() as connection:
            return _token(connection.execute(
                "SELECT * FROM user_tokens WHERE signature = ?", (signature,)
            ).fetchone())

    def revoke(self, signature: str, revoked_at: datetime) -> None:
        """Revoke a token.

        Args:
            signature: SHA-256 of the raw token.
            revoked_at: Moment of the revocation.
        """
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE user_tokens SET revoked_at = ? WHERE signature = ?",
                (_to_text(revoked_at), signature),
            )

    def revoke_all_for_user(self, user_id: int, revoked_at: datetime) -> None:
        """Revoke every active token of a user.

        Args:
            user_id: Owner of the tokens.
            revoked_at: Moment of the revocation.
        """
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE user_tokens SET revoked_at = ?
                WHERE user_id = ? AND revoked_at IS NULL
                """,
                (_to_text(revoked_at), user_id),
            )


# ------------------------------------------------------------------
# Registry: repos, layers, manifests, tags
# ------------------------------------------------------------------


class SQLiteRepoRepository(RepoRepository):
    """SQLite implementation of :class:`~api.persistence.repository.repo.RepoRepository`.

    Attributes:
        database: Database used for every operation.
    """

    def __init__(self, database: SQLiteDatabase):
        """Create the repository.

        Args:
            database: Database used for every operation.
        """
        self.database = database

    def create(self, repo: Repo) -> int:
        """Persist a new repository.

        Args:
            repo: Repository to store; its ``id`` is ignored.

        Returns:
            The identifier assigned to the repository.
        """
        with self.database.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO repos (name) VALUES (?)", (repo.name,)
            )
            return cursor.lastrowid

    def get_by_id(self, repo_id: int) -> Repo | None:
        """Find a repository by identifier.

        Args:
            repo_id: Repository identifier.

        Returns:
            The repository, or None if it does not exist.
        """
        return self._one("SELECT * FROM repos WHERE id = ?", repo_id)

    def get_by_name(self, name: str) -> Repo | None:
        """Find a repository by name.

        Args:
            name: Repository name, ``<organization>/<repo>``.

        Returns:
            The repository, or None if it does not exist.
        """
        return self._one("SELECT * FROM repos WHERE name = ?", name)

    def _one(self, query: str, value) -> Repo | None:
        """Run a query that returns at most one repository.

        Args:
            query: SQL query with one parameter.
            value: Value of the parameter.

        Returns:
            The repository, or None if there is no row.
        """
        with self.database.connect() as connection:
            row = connection.execute(query, (value,)).fetchone()
            return Repo(id=row["id"], name=row["name"]) if row else None


class SQLiteLayerRepository(LayerRepository):
    """SQLite implementation of :class:`~api.persistence.repository.layer.LayerRepository`.

    Attributes:
        database: Database used for every operation.
    """

    def __init__(self, database: SQLiteDatabase):
        """Create the repository.

        Args:
            database: Database used for every operation.
        """
        self.database = database

    def add(self, layer: Layer) -> None:
        """Register a layer in a repository.

        Does nothing if the layer is already registered there.

        Args:
            layer: Layer to register.
        """
        with self.database.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO layers (signature, repo_id) VALUES (?, ?)",
                (layer.signature, layer.repo_id),
            )

    def get(self, signature: str, repo_id: int) -> Layer | None:
        """Find a layer registered in a repository.

        Args:
            signature: SHA-256 of the layer.
            repo_id: Repository identifier.

        Returns:
            The layer, or None if the repository does not register it.
        """
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM layers WHERE signature = ? AND repo_id = ?",
                (signature, repo_id),
            ).fetchone()
            return Layer(row["signature"], row["repo_id"]) if row else None

    def delete(self, signature: str, repo_id: int) -> None:
        """Remove a layer from a repository.

        Args:
            signature: SHA-256 of the layer.
            repo_id: Repository identifier.
        """
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM layers WHERE signature = ? AND repo_id = ?",
                (signature, repo_id),
            )

    def exists_anywhere(self, signature: str) -> bool:
        """Check whether any repository still registers a layer.

        Args:
            signature: SHA-256 of the layer.

        Returns:
            True if at least one repository registers it.
        """
        with self.database.connect() as connection:
            return connection.execute(
                "SELECT 1 FROM layers WHERE signature = ? LIMIT 1",
                (signature,),
            ).fetchone() is not None


class SQLiteManifestRepository(ManifestRepository):
    """SQLite implementation of :class:`~api.persistence.repository.manifest.ManifestRepository`.

    Attributes:
        database: Database used for every operation.
    """

    def __init__(self, database: SQLiteDatabase):
        """Create the repository.

        Args:
            database: Database used for every operation.
        """
        self.database = database

    def add(self, manifest: Manifest) -> None:
        """Register a manifest and its ordered layers.

        Does nothing if the manifest is already registered.

        Args:
            manifest: Manifest to register.
        """
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO manifests (signature, repo_id)
                VALUES (?, ?)
                """,
                (manifest.signature, manifest.repo_id),
            )

            if cursor.rowcount == 0:
                return

            connection.executemany(
                """
                INSERT INTO manifest_layers
                    (manifest_signature, repo_id, position, layer_signature)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (manifest.signature, manifest.repo_id, position, layer)
                    for position, layer in enumerate(manifest.layers)
                ],
            )

    def get(self, signature: str, repo_id: int) -> Manifest | None:
        """Find a manifest of a repository.

        Args:
            signature: SHA-256 of the manifest.
            repo_id: Repository identifier.

        Returns:
            The manifest with its layers, or None if it does not exist.
        """
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM manifests WHERE signature = ? AND repo_id = ?",
                (signature, repo_id),
            ).fetchone()

            if row is None:
                return None

            layers = connection.execute(
                """
                SELECT layer_signature FROM manifest_layers
                WHERE manifest_signature = ? AND repo_id = ?
                ORDER BY position
                """,
                (signature, repo_id),
            ).fetchall()

            return Manifest(
                signature=signature,
                repo_id=repo_id,
                layers=[layer["layer_signature"] for layer in layers],
            )

    def delete(self, signature: str, repo_id: int) -> None:
        """Remove a manifest and its layer references from a repository.

        Args:
            signature: SHA-256 of the manifest.
            repo_id: Repository identifier.
        """
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM manifests WHERE signature = ? AND repo_id = ?",
                (signature, repo_id),
            )

    def references_layer(self, layer_signature: str, repo_id: int) -> bool:
        """Check whether any manifest of a repository needs a layer.

        Args:
            layer_signature: SHA-256 of the layer.
            repo_id: Repository identifier.

        Returns:
            True if at least one manifest references the layer.
        """
        with self.database.connect() as connection:
            return connection.execute(
                """
                SELECT 1 FROM manifest_layers
                WHERE layer_signature = ? AND repo_id = ? LIMIT 1
                """,
                (layer_signature, repo_id),
            ).fetchone() is not None

    def exists_anywhere(self, signature: str) -> bool:
        """Check whether any repository still registers a manifest.

        Args:
            signature: SHA-256 of the manifest.

        Returns:
            True if at least one repository registers it.
        """
        with self.database.connect() as connection:
            return connection.execute(
                "SELECT 1 FROM manifests WHERE signature = ? LIMIT 1",
                (signature,),
            ).fetchone() is not None


def _tag(row) -> Tag:
    """Convert a database row into a tag.

    Args:
        row: Row returned by SQLite, or None.

    Returns:
        The tag.
    """
    return Tag(
        manifest_signature=row["manifest_signature"],
        repo_id=row["repo_id"],
        tag=row["tag"],
    )


class SQLiteTagRepository(TagRepository):
    """SQLite implementation of :class:`~api.persistence.repository.tag.TagRepository`.

    Attributes:
        database: Database used for every operation.
    """

    def __init__(self, database: SQLiteDatabase):
        """Create the repository.

        Args:
            database: Database used for every operation.
        """
        self.database = database

    def set(self, tag: Tag) -> None:
        """Point a tag to a manifest, overwriting the tag if it exists.

        Args:
            tag: Tag to store.
        """
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO tags (repo_id, tag, manifest_signature)
                VALUES (?, ?, ?)
                ON CONFLICT (repo_id, tag)
                DO UPDATE SET manifest_signature = excluded.manifest_signature
                """,
                (tag.repo_id, tag.tag, tag.manifest_signature),
            )

    def get(self, repo_id: int, tag: str) -> Tag | None:
        """Find a tag of a repository.

        Args:
            repo_id: Repository identifier.
            tag: Tag name.

        Returns:
            The tag, or None if it does not exist.
        """
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM tags WHERE repo_id = ? AND tag = ?",
                (repo_id, tag),
            ).fetchone()
            return _tag(row) if row else None

    def list_by_repo(self, repo_id: int) -> list[Tag]:
        """List the tags of a repository.

        Args:
            repo_id: Repository identifier.

        Returns:
            Every tag of the repository.
        """
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM tags WHERE repo_id = ? ORDER BY tag",
                (repo_id,),
            ).fetchall()
            return [_tag(row) for row in rows]

    def delete_by_manifest(
        self, repo_id: int, manifest_signature: str
    ) -> None:
        """Delete every tag that points to a manifest.

        Args:
            repo_id: Repository identifier.
            manifest_signature: SHA-256 of the manifest.
        """
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM tags WHERE repo_id = ? AND manifest_signature = ?",
                (repo_id, manifest_signature),
            )


# ------------------------------------------------------------------
# Sessions and audit
# ------------------------------------------------------------------


def _upload(row) -> UploadSession | None:
    """Convert a database row into a upload session.

    Args:
        row: Row returned by SQLite, or None.

    Returns:
        The upload session, or None if there is no row.
    """
    if row is None:
        return None

    return UploadSession(
        id=row["id"],
        user_id=row["user_id"],
        repo_id=row["repo_id"],
        kind=BlobKind(row["kind"]),
        blob_signature=row["blob_signature"],
        total_size=row["total_size"],
        created_at=_to_datetime(row["created_at"]),
        last_activity=_to_datetime(row["last_activity"]),
        layers=json.loads(row["layers"]),
        # JSON keys are strings; piece indexes are integers.
        received={
            int(index): signature
            for index, signature in json.loads(row["received"]).items()
        },
        status=SessionStatus(row["status"]),
    )


class SQLiteUploadSessionRepository(UploadSessionRepository):
    """SQLite implementation of :class:`~api.persistence.repository.upload_session.UploadSessionRepository`.

    Attributes:
        database: Database used for every operation.
    """

    def __init__(self, database: SQLiteDatabase):
        """Create the repository.

        Args:
            database: Database used for every operation.
        """
        self.database = database

    def create(self, session: UploadSession) -> None:
        """Persist a new upload session.

        Args:
            session: Session to store.
        """
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO upload_sessions
                    (id, user_id, repo_id, kind, blob_signature, total_size,
                     layers, received, status, created_at, last_activity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session.id, session.user_id, session.repo_id,
                 session.kind.value, session.blob_signature,
                 session.total_size, json.dumps(session.layers),
                 json.dumps(session.received), session.status.value,
                 _to_text(session.created_at),
                 _to_text(session.last_activity)),
            )

    def get(self, session_id: str) -> UploadSession | None:
        """Find an upload session.

        Args:
            session_id: Session identifier.

        Returns:
            The session, or None if it does not exist.
        """
        with self.database.connect() as connection:
            return _upload(connection.execute(
                "SELECT * FROM upload_sessions WHERE id = ?", (session_id,)
            ).fetchone())

    def update(self, session: UploadSession) -> None:
        """Persist the status, received pieces and last activity of a session.

        Args:
            session: Session with the new values.
        """
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE upload_sessions
                SET received = ?, status = ?, last_activity = ?
                WHERE id = ?
                """,
                (json.dumps(session.received), session.status.value,
                 _to_text(session.last_activity), session.id),
            )

    def list_open(self) -> list[UploadSession]:
        """List the sessions that are still open.

        Returns:
            Every session whose status is ``OPEN``.
        """
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM upload_sessions WHERE status = ?",
                (SessionStatus.OPEN.value,),
            ).fetchall()
            return [_upload(row) for row in rows]


def _download(row) -> DownloadSession | None:
    """Convert a database row into a download session.

    Args:
        row: Row returned by SQLite, or None.

    Returns:
        The download session, or None if there is no row.
    """
    if row is None:
        return None

    return DownloadSession(
        id=row["id"],
        user_id=row["user_id"],
        repo_id=row["repo_id"],
        blob_signature=row["blob_signature"],
        created_at=_to_datetime(row["created_at"]),
        last_activity=_to_datetime(row["last_activity"]),
        status=SessionStatus(row["status"]),
    )


class SQLiteDownloadSessionRepository(DownloadSessionRepository):
    """SQLite implementation of :class:`~api.persistence.repository.download_session.DownloadSessionRepository`.

    Attributes:
        database: Database used for every operation.
    """

    def __init__(self, database: SQLiteDatabase):
        """Create the repository.

        Args:
            database: Database used for every operation.
        """
        self.database = database

    def create(self, session: DownloadSession) -> None:
        """Persist a new download session.

        Args:
            session: Session to store.
        """
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO download_sessions
                    (id, user_id, repo_id, blob_signature, status,
                     created_at, last_activity)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session.id, session.user_id, session.repo_id,
                 session.blob_signature, session.status.value,
                 _to_text(session.created_at),
                 _to_text(session.last_activity)),
            )

    def get(self, session_id: str) -> DownloadSession | None:
        """Find a download session.

        Args:
            session_id: Session identifier.

        Returns:
            The session, or None if it does not exist.
        """
        with self.database.connect() as connection:
            return _download(connection.execute(
                "SELECT * FROM download_sessions WHERE id = ?", (session_id,)
            ).fetchone())

    def update(self, session: DownloadSession) -> None:
        """Persist the status and last activity of a session.

        Args:
            session: Session with the new values.
        """
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE download_sessions SET status = ?, last_activity = ?
                WHERE id = ?
                """,
                (session.status.value, _to_text(session.last_activity),
                 session.id),
            )

    def list_open(self) -> list[DownloadSession]:
        """List the sessions that are still open.

        Returns:
            Every session whose status is ``OPEN``.
        """
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM download_sessions WHERE status = ?",
                (SessionStatus.OPEN.value,),
            ).fetchall()
            return [_download(row) for row in rows]


class SQLiteAuditLogRepository(AuditLogRepository):
    """SQLite implementation of :class:`~api.persistence.repository.audit_log.AuditLogRepository`.

    Attributes:
        database: Database used for every operation.
    """

    def __init__(self, database: SQLiteDatabase):
        """Create the repository.

        Args:
            database: Database used for every operation.
        """
        self.database = database

    def add(self, event: AuditEvent) -> None:
        """Append an event to the log.

        Args:
            event: Event to store.
        """
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_log
                    (user_id, session_id, event, result, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event.user_id, event.session_id, event.event, event.result,
                 event.detail, _to_text(event.created_at)),
            )

    def list_recent(self, limit: int = 100) -> list[AuditEvent]:
        """List the most recent events.

        Args:
            limit: Maximum number of events to return.

        Returns:
            The events, newest first.
        """
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()

            return [
                AuditEvent(
                    user_id=row["user_id"],
                    session_id=row["session_id"],
                    event=row["event"],
                    result=row["result"],
                    created_at=_to_datetime(row["created_at"]),
                    detail=row["detail"],
                )
                for row in rows
            ]
