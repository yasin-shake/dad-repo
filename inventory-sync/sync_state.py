"""SQLite baseline storage for the local Picasa inventory sync utility."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class FileState:
    export_key: str
    relative_path: str
    size_bytes: int
    modified_ns: int
    sha256: str


@dataclass(frozen=True)
class BaselineState:
    manifest_digest: str
    created_at: str
    albums: dict[str, str]
    files: dict[str, FileState]
    memberships: set[tuple[str, str]]


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def write_baseline(
    path: Path,
    manifest_digest: str,
    albums: dict[str, str],
    files: dict[str, FileState],
    memberships: set[tuple[str, str]],
    *,
    replace: bool = False,
) -> None:
    if path.exists() and not replace:
        raise FileExistsError(f"State already exists: {path}. Use --replace-state to replace it deliberately.")
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = _connect(path)
    try:
        with connection:
            connection.executescript(
                """
                DROP TABLE IF EXISTS memberships;
                DROP TABLE IF EXISTS files;
                DROP TABLE IF EXISTS albums;
                DROP TABLE IF EXISTS metadata;
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE albums (
                    album_id TEXT PRIMARY KEY,
                    album_name TEXT NOT NULL
                );
                CREATE TABLE files (
                    export_key TEXT PRIMARY KEY,
                    relative_path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    modified_ns INTEGER NOT NULL,
                    sha256 TEXT NOT NULL
                );
                CREATE TABLE memberships (
                    album_id TEXT NOT NULL REFERENCES albums(album_id),
                    export_key TEXT NOT NULL REFERENCES files(export_key),
                    PRIMARY KEY (album_id, export_key)
                );
                """
            )
            created_at = datetime.now(timezone.utc).isoformat()
            connection.executemany(
                "INSERT INTO metadata(key, value) VALUES (?, ?)",
                (
                    ("schema_version", SCHEMA_VERSION),
                    ("manifest_digest", manifest_digest),
                    ("created_at", created_at),
                ),
            )
            connection.executemany(
                "INSERT INTO albums(album_id, album_name) VALUES (?, ?)",
                sorted(albums.items()),
            )
            connection.executemany(
                """INSERT INTO files(export_key, relative_path, size_bytes, modified_ns, sha256)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    (item.export_key, item.relative_path, item.size_bytes, item.modified_ns, item.sha256)
                    for item in sorted(files.values(), key=lambda value: value.export_key)
                ),
            )
            connection.executemany(
                "INSERT INTO memberships(album_id, export_key) VALUES (?, ?)",
                sorted(memberships),
            )
    finally:
        connection.close()


def read_baseline(path: Path) -> BaselineState:
    if not path.is_file():
        raise FileNotFoundError(f"State database not found: {path}")
    connection = _connect(path)
    try:
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        if metadata.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported state schema {metadata.get('schema_version')!r}; expected {SCHEMA_VERSION}."
            )
        albums = dict(connection.execute("SELECT album_id, album_name FROM albums"))
        files = {
            row["export_key"]: FileState(
                export_key=row["export_key"],
                relative_path=row["relative_path"],
                size_bytes=row["size_bytes"],
                modified_ns=row["modified_ns"],
                sha256=row["sha256"],
            )
            for row in connection.execute(
                "SELECT export_key, relative_path, size_bytes, modified_ns, sha256 FROM files"
            )
        }
        memberships = {
            (row["album_id"], row["export_key"])
            for row in connection.execute("SELECT album_id, export_key FROM memberships")
        }
        return BaselineState(
            manifest_digest=metadata["manifest_digest"],
            created_at=metadata["created_at"],
            albums=albums,
            files=files,
            memberships=memberships,
        )
    except sqlite3.DatabaseError as error:
        raise ValueError(f"Invalid state database: {path}") from error
    finally:
        connection.close()
