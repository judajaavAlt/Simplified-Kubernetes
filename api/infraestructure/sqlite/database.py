import sqlite3
from contextlib import contextmanager
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nickname TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    salt TEXT NOT NULL,
    role TEXT NOT NULL,
    must_change_password INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS user_tokens (
    signature TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS repos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS layers (
    signature TEXT NOT NULL,
    repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    PRIMARY KEY (signature, repo_id)
);

CREATE TABLE IF NOT EXISTS manifests (
    signature TEXT NOT NULL,
    repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    PRIMARY KEY (signature, repo_id)
);

CREATE TABLE IF NOT EXISTS manifest_layers (
    manifest_signature TEXT NOT NULL,
    repo_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    layer_signature TEXT NOT NULL,
    PRIMARY KEY (manifest_signature, repo_id, position),
    FOREIGN KEY (manifest_signature, repo_id)
        REFERENCES manifests(signature, repo_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tags (
    repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    manifest_signature TEXT NOT NULL,
    PRIMARY KEY (repo_id, tag)
);

CREATE TABLE IF NOT EXISTS upload_sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    repo_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    blob_signature TEXT NOT NULL,
    total_size INTEGER NOT NULL,
    layers TEXT NOT NULL,
    received TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_activity TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS download_sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    repo_id INTEGER NOT NULL,
    blob_signature TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_activity TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    session_id TEXT,
    event TEXT NOT NULL,
    result TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class SQLiteDatabase:
    """SQLite database of the registry.

    Opens one short lived connection per operation, so it is safe to use
    from the FastAPI worker threads.

    Attributes:
        path: Database file.
    """

    def __init__(self, path: Path):
        """Create the handle; nothing is opened yet.

        Args:
            path: Database file; its folder is created on connect.
        """
        self.path = Path(path)

    @contextmanager
    def connect(self):
        """Open a connection inside a transaction.

        The transaction commits on success and rolls back on error, and the
        connection is closed at the end. Foreign keys are enabled.

        Yields:
            A connection whose rows can be read by column name.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")

        try:
            with connection:  # commit on success, rollback on error
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create the tables that do not exist yet."""
        with self.connect() as connection:
            connection.executescript(SCHEMA)
