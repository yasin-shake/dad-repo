"""Validation and path mapping for Picasa export manifests."""

from __future__ import annotations

import csv
import hashlib
import ntpath
from dataclasses import dataclass
from pathlib import Path


EXPECTED_COLUMNS = ("Album", "Album ID", "Original", "Exported", "Status")


class ManifestError(ValueError):
    """Raised when a manifest cannot be used safely."""


@dataclass(frozen=True)
class ManifestEntry:
    album_name: str
    album_id: str
    original_path: str
    exported_path: str
    status: str
    export_key: str
    relative_path: str


@dataclass(frozen=True)
class Manifest:
    path: Path
    digest: str
    declared_export_root: str
    entries: tuple[ManifestEntry, ...]


def _normalized_windows_path(value: str, row_number: int) -> str:
    path = ntpath.normpath(value)
    drive, tail = ntpath.splitdrive(path)
    if not drive or not tail.startswith(("\\", "/")):
        raise ManifestError(f"Row {row_number}: Exported must be an absolute Windows path.")
    return path


def _infer_export_root(rows: list[dict[str, str]]) -> str:
    directories = [ntpath.dirname(row["Exported"]) for row in rows]
    try:
        common = ntpath.commonpath(directories)
    except ValueError as error:
        raise ManifestError("Exported paths do not share one Windows export root.") from error

    album_ids = {row["Album ID"] for row in rows}
    if len(album_ids) == 1:
        common = ntpath.dirname(common)
    if not common or common == ntpath.splitdrive(common)[0] + "\\":
        raise ManifestError("Could not infer a safe export root from Exported paths.")
    return ntpath.normpath(common)


def load_manifest(path: Path) -> Manifest:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ManifestError("Manifest must be UTF-8 CSV (a UTF-8 BOM is accepted).") from error

    reader = csv.DictReader(text.splitlines())
    if tuple(reader.fieldnames or ()) != EXPECTED_COLUMNS:
        raise ManifestError(
            "Manifest columns must be exactly: " + ", ".join(EXPECTED_COLUMNS)
        )

    raw_rows: list[dict[str, str]] = []
    album_names: dict[str, str] = {}
    for row_number, row in enumerate(reader, start=2):
        clean = {column: (row[column] or "").strip() for column in EXPECTED_COLUMNS}
        if not any(clean.values()):
            continue
        for column in ("Album", "Album ID", "Exported", "Status"):
            if not clean[column]:
                raise ManifestError(f"Row {row_number}: {column} is required.")
        clean["Exported"] = _normalized_windows_path(clean["Exported"], row_number)
        previous = album_names.setdefault(clean["Album ID"], clean["Album"])
        if previous != clean["Album"]:
            raise ManifestError(
                f"Row {row_number}: album ID {clean['Album ID']!r} has multiple names in one manifest."
            )
        raw_rows.append(clean)

    if not raw_rows:
        raise ManifestError("Manifest has no data rows.")

    declared_root = _infer_export_root(raw_rows)
    entries: list[ManifestEntry] = []
    seen_exports: set[str] = set()
    seen_memberships: set[tuple[str, str]] = set()
    for row_number, row in enumerate(raw_rows, start=2):
        relative = ntpath.relpath(row["Exported"], declared_root)
        if relative == ntpath.pardir or relative.startswith(ntpath.pardir + ntpath.sep):
            raise ManifestError(f"Row {row_number}: Exported path escapes the inferred export root.")
        relative = relative.replace("\\", "/")
        export_key = relative.casefold()
        if export_key in seen_exports:
            raise ManifestError(f"Row {row_number}: duplicate Exported path {relative!r}.")
        membership = (row["Album ID"], export_key)
        if membership in seen_memberships:
            raise ManifestError(f"Row {row_number}: duplicate album-photo association.")
        seen_exports.add(export_key)
        seen_memberships.add(membership)
        entries.append(
            ManifestEntry(
                album_name=row["Album"],
                album_id=row["Album ID"],
                original_path=row["Original"],
                exported_path=row["Exported"],
                status=row["Status"],
                export_key=export_key,
                relative_path=relative,
            )
        )

    return Manifest(path=path, digest=digest, declared_export_root=declared_root, entries=tuple(entries))


def local_export_path(export_root: Path, relative_path: str) -> Path:
    parts = relative_path.split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ManifestError(f"Unsafe exported relative path: {relative_path!r}.")
    candidate = export_root.joinpath(*parts)
    root_resolved = export_root.resolve()
    candidate_resolved = candidate.resolve(strict=False)
    if candidate_resolved != root_resolved and root_resolved not in candidate_resolved.parents:
        raise ManifestError(f"Exported path escapes --export-root: {relative_path!r}.")
    return candidate
