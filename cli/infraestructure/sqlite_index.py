import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from cli.data.models import ManifestRecord, Reference
from cli.persistence.template_index import TemplateIndex


SCHEMA = """
CREATE TABLE IF NOT EXISTS manifests (
    id TEXT PRIMARY KEY,
    size INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS manifest_layers (
    manifest_id TEXT NOT NULL REFERENCES manifests(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    layer_id TEXT NOT NULL,
    PRIMARY KEY (manifest_id, position)
);
CREATE TABLE IF NOT EXISTS tags (
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    organization TEXT NOT NULL,
    repository TEXT NOT NULL,
    tag TEXT NOT NULL,
    manifest_id TEXT NOT NULL REFERENCES manifests(id) ON DELETE CASCADE,
    PRIMARY KEY (host, port, organization, repository, tag)
);
CREATE TABLE IF NOT EXISTS dry_runs (
    key TEXT NOT NULL,
    stage TEXT NOT NULL,
    at TEXT NOT NULL,
    PRIMARY KEY (key, stage)
);
"""

_REFERENCE = "host = ? AND port = ? AND organization = ? AND repository = ? AND tag = ?"


def _key(reference: Reference) -> tuple:
    """Split a reference into its index columns.

    Args:
        reference: Complete reference.

    Returns:
        Host, port, organization, repository and tag.
    """
    return (reference.host, reference.port, reference.organization,
            reference.repository, reference.tag)


class SQLiteTemplateIndex(TemplateIndex):
    """Local index in SQLite; one short connection per operation.

    Attributes:
        path: Database file.
    """

    def __init__(self, path: Path):
        """Create the index handle; nothing is opened yet.

        Args:
            path: Database file; its folder is created on connect.
        """
        self.path = Path(path)

    @contextmanager
    def _connect(self):
        """Open a connection inside a transaction.

        Yields:
            A connection with foreign keys enabled.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create the tables that do not exist yet."""
        with self._connect() as db:
            db.executescript(SCHEMA)

    def add_manifest(self, manifest_id, layers, size, created_at) -> None:
        """Register a manifest; does nothing if it is already registered.

        Args:
            manifest_id: SHA-256 of the manifest.
            layers: SHA-256 of its layers, in order.
            size: Size of the manifest plus its layers.
            created_at: Moment it was created or pulled.
        """
        with self._connect() as db:
            inserted = db.execute(
                "INSERT OR IGNORE INTO manifests VALUES (?, ?, ?)",
                (manifest_id, size, created_at.isoformat()),
            ).rowcount
            if inserted:
                db.executemany(
                    "INSERT INTO manifest_layers VALUES (?, ?, ?)",
                    [(manifest_id, i, layer) for i, layer in enumerate(layers)],
                )

    def has_manifest(self, manifest_id) -> bool:
        """Check whether a manifest is registered.

        Args:
            manifest_id: SHA-256 of the manifest.

        Returns:
            True if it is registered.
        """
        with self._connect() as db:
            return db.execute(
                "SELECT 1 FROM manifests WHERE id = ?", (manifest_id,)
            ).fetchone() is not None

    def manifest_ids(self) -> list[str]:
        """List the IDs of every registered manifest.

        Returns:
            The IDs.
        """
        with self._connect() as db:
            return [row[0] for row in db.execute("SELECT id FROM manifests")]

    def layers_of(self, manifest_id) -> tuple[str, ...]:
        """List the layers of a manifest.

        Args:
            manifest_id: SHA-256 of the manifest.

        Returns:
            The layers in order.
        """
        with self._connect() as db:
            return tuple(row[0] for row in db.execute(
                "SELECT layer_id FROM manifest_layers WHERE manifest_id = ? "
                "ORDER BY position", (manifest_id,)))

    def remove_manifest(self, manifest_id) -> None:
        """Unregister a manifest together with its tags and layers.

        Args:
            manifest_id: SHA-256 of the manifest.
        """
        with self._connect() as db:
            db.execute("DELETE FROM manifests WHERE id = ?", (manifest_id,))

    def list_manifests(self) -> list[ManifestRecord]:
        """List every manifest with its tags.

        Returns:
            The records, newest first.
        """
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, size, created_at FROM manifests "
                "ORDER BY created_at DESC, id").fetchall()
        return [
            ManifestRecord(i, datetime.fromisoformat(c), s, tuple(self.tags_of(i)))
            for i, s, c in rows
        ]

    def set_tag(self, reference, manifest_id) -> None:
        """Point a reference to a manifest, overwriting it if it exists.

        Args:
            reference: Complete reference.
            manifest_id: SHA-256 of the manifest.
        """
        with self._connect() as db:
            db.execute(f"DELETE FROM tags WHERE {_REFERENCE}", _key(reference))
            db.execute("INSERT INTO tags VALUES (?, ?, ?, ?, ?, ?)",
                       (*_key(reference), manifest_id))

    def get_tag(self, reference) -> str | None:
        """Find the manifest a reference points to.

        Args:
            reference: Complete reference.

        Returns:
            The manifest ID, or None.
        """
        with self._connect() as db:
            row = db.execute(
                f"SELECT manifest_id FROM tags WHERE {_REFERENCE}", _key(reference)
            ).fetchone()
        return row[0] if row else None

    def remove_tag(self, reference) -> None:
        """Delete a reference; the manifest is kept.

        Args:
            reference: Complete reference.
        """
        with self._connect() as db:
            db.execute(f"DELETE FROM tags WHERE {_REFERENCE}", _key(reference))

    def tags_of(self, manifest_id) -> list[Reference]:
        """List the references that point to a manifest.

        Args:
            manifest_id: SHA-256 of the manifest.

        Returns:
            The references, in creation order.
        """
        with self._connect() as db:
            rows = db.execute(
                "SELECT host, port, organization, repository, tag FROM tags "
                "WHERE manifest_id = ? ORDER BY rowid", (manifest_id,)).fetchall()
        return [Reference(*row) for row in rows]

    def layer_in_use(self, layer_id) -> bool:
        """Check whether any registered manifest needs a layer.

        Args:
            layer_id: SHA-256 of the layer.

        Returns:
            True if at least one manifest uses it.
        """
        with self._connect() as db:
            return db.execute(
                "SELECT 1 FROM manifest_layers WHERE layer_id = ? LIMIT 1",
                (layer_id,)).fetchone() is not None

    def clear_templates(self) -> None:
        """Unregister every manifest and tag; dry runs are kept."""
        with self._connect() as db:
            db.execute("DELETE FROM manifests")

    def record_dry_run(self, key, stage, at) -> None:
        """Remember that a stage of a template had a dry run.

        Args:
            key: Manifest ID or SHA-256 of an old config.template.
            stage: ``build`` or ``deploy``.
            at: Moment of the dry run.
        """
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO dry_runs VALUES (?, ?, ?)",
                       (key, stage, at.isoformat()))

    def has_dry_run(self, key, stage) -> bool:
        """Check whether a stage of a template already had a dry run.

        Args:
            key: Manifest ID or SHA-256 of an old config.template.
            stage: ``build`` or ``deploy``.

        Returns:
            True if it had one on this machine.
        """
        with self._connect() as db:
            return db.execute(
                "SELECT 1 FROM dry_runs WHERE key = ? AND stage = ?",
                (key, stage)).fetchone() is not None
