"""Read-only Picasa export verification and local change reporting.

The utility reads exported copies and a CSV manifest. It never writes to the
export tree, original paths, a cloud service, or the Qatar Drive Deal website.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from manifest import Manifest, ManifestError, load_manifest, local_export_path
from sync_state import BaselineState, FileState, read_baseline, write_baseline


CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class ScanResult:
    albums: dict[str, str]
    files: dict[str, FileState]
    declared_paths: dict[str, str]
    memberships: set[tuple[str, str]]
    issues: tuple[dict, ...]
    hashed_files: int
    reused_hashes: int


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    resolved = path.resolve(strict=False)
    root_resolved = root.resolve(strict=False)
    return resolved == root_resolved or root_resolved in resolved.parents


def ensure_output_outside_export(path: Path, export_root: Path, label: str) -> None:
    if _is_within(path, export_root):
        raise ValueError(f"{label} must be outside --export-root so the export remains untouched.")


def scan_exports(
    manifest: Manifest,
    export_root: Path,
    baseline: BaselineState | None = None,
) -> ScanResult:
    albums = {entry.album_id: entry.album_name for entry in manifest.entries}
    declared_paths = {entry.export_key: entry.relative_path for entry in manifest.entries}
    memberships = {(entry.album_id, entry.export_key) for entry in manifest.entries}
    files: dict[str, FileState] = {}
    issues: list[dict] = []
    hashed_files = 0
    reused_hashes = 0

    for entry in manifest.entries:
        if entry.status.casefold() != "copied":
            issues.append(
                {
                    "kind": "manifest_status_not_copied",
                    "album_id": entry.album_id,
                    "relative_path": entry.relative_path,
                    "status": entry.status,
                }
            )
            continue
        path = local_export_path(export_root, entry.relative_path)
        try:
            before = path.stat()
            if not path.is_file():
                issues.append(
                    {"kind": "missing_export", "album_id": entry.album_id, "relative_path": entry.relative_path}
                )
                continue
            cached = baseline.files.get(entry.export_key) if baseline else None
            if cached and (cached.size_bytes, cached.modified_ns) == (before.st_size, before.st_mtime_ns):
                digest = cached.sha256
                reused_hashes += 1
            else:
                digest = hash_file(path)
                hashed_files += 1
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                issues.append(
                    {
                        "kind": "changed_during_scan",
                        "album_id": entry.album_id,
                        "relative_path": entry.relative_path,
                    }
                )
                continue
            files[entry.export_key] = FileState(
                export_key=entry.export_key,
                relative_path=entry.relative_path,
                size_bytes=after.st_size,
                modified_ns=after.st_mtime_ns,
                sha256=digest,
            )
        except FileNotFoundError:
            issues.append(
                {"kind": "missing_export", "album_id": entry.album_id, "relative_path": entry.relative_path}
            )
        except OSError as error:
            issues.append(
                {
                    "kind": "unreadable_export",
                    "album_id": entry.album_id,
                    "relative_path": entry.relative_path,
                    "error": f"{type(error).__name__}: {error}",
                }
            )

    return ScanResult(
        albums=albums,
        files=files,
        declared_paths=declared_paths,
        memberships=memberships,
        issues=tuple(issues),
        hashed_files=hashed_files,
        reused_hashes=reused_hashes,
    )


def duplicate_groups(files: dict[str, FileState]) -> list[dict]:
    by_hash: dict[str, list[str]] = defaultdict(list)
    for item in files.values():
        by_hash[item.sha256].append(item.relative_path)
    return [
        {"sha256": digest, "paths": sorted(paths, key=str.casefold)}
        for digest, paths in sorted(by_hash.items())
        if len(paths) > 1
    ]


def membership_details(
    memberships: set[tuple[str, str]],
    albums: dict[str, str],
    paths: dict[str, str],
    fallback_files: dict[str, FileState],
) -> list[dict]:
    return [
        {
            "album_id": album_id,
            "album_name": albums.get(album_id),
            "relative_path": paths.get(export_key)
            or fallback_files[export_key].relative_path,
        }
        for album_id, export_key in sorted(memberships)
    ]


def build_change_report(manifest: Manifest, baseline: BaselineState, current: ScanResult) -> dict:
    old_album_ids = set(baseline.albums)
    new_album_ids = set(current.albums)
    added_album_ids = new_album_ids - old_album_ids
    removed_album_ids = old_album_ids - new_album_ids
    renamed_album_ids = {
        album_id
        for album_id in old_album_ids & new_album_ids
        if baseline.albums[album_id] != current.albums[album_id]
    }
    added_memberships = current.memberships - baseline.memberships
    removed_memberships = baseline.memberships - current.memberships
    common_files = set(baseline.files) & set(current.files)
    modified_keys = {
        key for key in common_files if baseline.files[key].sha256 != current.files[key].sha256
    }
    duplicates = duplicate_groups(current.files)

    return {
        "report_version": 1,
        "generated_at": utc_now(),
        "baseline": {
            "created_at": baseline.created_at,
            "manifest_sha256": baseline.manifest_digest,
        },
        "current_manifest_sha256": manifest.digest,
        "summary": {
            "manifest_rows": len(manifest.entries),
            "verified_files": len(current.files),
            "issues": len(current.issues),
            "hashed_files": current.hashed_files,
            "reused_hashes": current.reused_hashes,
            "albums_added": len(added_album_ids),
            "albums_removed": len(removed_album_ids),
            "albums_renamed": len(renamed_album_ids),
            "memberships_added": len(added_memberships),
            "memberships_removed": len(removed_memberships),
            "files_modified": len(modified_keys),
            "duplicate_content_groups": len(duplicates),
        },
        "albums": {
            "added": [
                {"album_id": album_id, "album_name": current.albums[album_id]}
                for album_id in sorted(added_album_ids)
            ],
            "removed": [
                {
                    "album_id": album_id,
                    "album_name": baseline.albums[album_id],
                    "interpretation": "missing_from_manifest_not_proof_of_sale",
                }
                for album_id in sorted(removed_album_ids)
            ],
            "renamed": [
                {
                    "album_id": album_id,
                    "previous_name": baseline.albums[album_id],
                    "current_name": current.albums[album_id],
                }
                for album_id in sorted(renamed_album_ids)
            ],
        },
        "memberships": {
            "added": membership_details(
                added_memberships, current.albums, current.declared_paths, baseline.files
            ),
            "removed": membership_details(
                removed_memberships,
                baseline.albums,
                {key: value.relative_path for key, value in baseline.files.items()},
                current.files,
            ),
        },
        "modified_files": [
            {
                "relative_path": current.files[key].relative_path,
                "previous_sha256": baseline.files[key].sha256,
                "current_sha256": current.files[key].sha256,
            }
            for key in sorted(modified_keys)
        ],
        "issues": list(current.issues),
        "duplicate_content": duplicates,
        "safety": {
            "source_files_modified": False,
            "cloud_upload_attempted": False,
            "inventory_published": False,
            "removed_items_mean_sold": False,
        },
    }


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def run_baseline(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    export_root = args.export_root.resolve()
    if not export_root.is_dir():
        raise ValueError(f"Export root is not an accessible directory: {export_root}")
    ensure_output_outside_export(args.state, export_root, "--state")
    result = scan_exports(manifest, export_root)
    if result.issues:
        kinds: dict[str, int] = defaultdict(int)
        for issue in result.issues:
            kinds[issue["kind"]] += 1
        print(
            f"Baseline not saved: {len(result.issues)} issue(s): "
            + ", ".join(f"{kind}={count}" for kind, count in sorted(kinds.items())),
            file=sys.stderr,
        )
        return 2
    write_baseline(
        args.state,
        manifest.digest,
        result.albums,
        result.files,
        result.memberships,
        replace=args.replace_state,
    )
    print(
        f"Baseline saved: {len(result.albums)} albums, {len(result.files)} verified files, "
        f"{len(duplicate_groups(result.files))} duplicate-content group(s)."
    )
    print(f"State: {args.state.resolve()}")
    return 0


def run_scan(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    baseline = read_baseline(args.state)
    export_root = args.export_root.resolve()
    if not export_root.is_dir():
        raise ValueError(f"Export root is not an accessible directory: {export_root}")
    ensure_output_outside_export(args.state, export_root, "--state")
    ensure_output_outside_export(args.report, export_root, "--report")
    result = scan_exports(manifest, export_root, baseline)
    report = build_change_report(manifest, baseline, result)
    write_json(args.report, report)
    summary = report["summary"]
    print(
        "Scan complete: "
        f"added albums={summary['albums_added']}, renamed albums={summary['albums_renamed']}, "
        f"removed albums={summary['albums_removed']}, modified files={summary['files_modified']}, "
        f"issues={summary['issues']}."
    )
    print(f"Report: {args.report.resolve()}")
    return 2 if result.issues else 0


def path_argument(value: str) -> Path:
    return Path(value).expanduser()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify Picasa exports and report local changes without modifying originals or uploading data."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--manifest", required=True, type=path_argument, help="Picasa export CSV manifest")
    common.add_argument("--export-root", required=True, type=path_argument, help="Folder containing exported albums")
    common.add_argument("--state", required=True, type=path_argument, help="Local SQLite baseline path")

    baseline = subparsers.add_parser("baseline", parents=[common], help="Verify every exported copy and create state")
    baseline.add_argument(
        "--replace-state",
        action="store_true",
        help="Deliberately replace an existing baseline after a complete successful verification",
    )
    baseline.set_defaults(handler=run_baseline)

    scan = subparsers.add_parser("scan", parents=[common], help="Compare a manifest/export snapshot with the baseline")
    scan.add_argument("--report", required=True, type=path_argument, help="Private JSON change-report path")
    scan.set_defaults(handler=run_scan)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (ManifestError, FileNotFoundError, FileExistsError, ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
