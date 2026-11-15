"""Read-only inventory discovery. Python 3.11+, standard library only.

Never uploads files, runs OCR, changes source folders, or publishes listings.
Each configured root contains vehicle folders as its immediate children.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


MEDIA_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff", ".bmp", ".pdf"}
DOCUMENT_WORDS = re.compile(r"mul[ qk]*[iy]+a|mulkiya|mulqiya|registration|istimara|استمارة|ملكية", re.I)
MAKE_ALIASES = {
    "mercedes benz": "Mercedes-Benz", "mercedes": "Mercedes-Benz",
    "land rover": "Land Rover", "range rover": "Land Rover",
    "rolls royce": "Rolls-Royce", "alfa romeo": "Alfa Romeo",
    **{name.lower(): name for name in (
        "Toyota", "Lexus", "Nissan", "Infiniti", "Honda", "Acura", "Mazda", "Mitsubishi",
        "Suzuki", "Subaru", "Isuzu", "Hyundai", "Kia", "Genesis", "BMW", "Audi", "Volkswagen",
        "Porsche", "Bentley", "Ferrari", "Lamborghini", "Maserati", "McLaren", "Aston Martin",
        "Ford", "Lincoln", "Chevrolet", "GMC", "Cadillac", "Dodge", "Chrysler", "Jeep", "Ram",
        "Tesla", "Volvo", "Peugeot", "Renault", "Geely", "Changan", "Chery", "Haval", "BYD",
        "MG", "Jetour", "GAC", "Tank", "BAIC", "JAC", "Great Wall",
    )},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def folder_hints(name: str) -> dict:
    """Suggestions only: residual text may include trim, price, or stock number."""
    text = re.sub(r"[_\-.]+", " ", name).strip()
    years = sorted({int(y) for y in re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", text)
                    if 1950 <= int(y) <= datetime.now().year + 1})
    make, model_hint = None, None
    for alias in sorted(MAKE_ALIASES, key=len, reverse=True):
        match = re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", text, re.I)
        if match:
            make = MAKE_ALIASES[alias]
            # Keep 'Range Rover' in the model hint, as it is also a model family.
            remaining = text if alias == "range rover" else text[:match.start()] + " " + text[match.end():]
            remaining = re.sub(r"(?<!\d)(?:19|20)\d{2}(?!\d)", " ", remaining)
            model_hint = " ".join(remaining.split()) or None
            break
    return {"make": make, "model_text": model_hint,
            "year": years[0] if len(years) == 1 else None,
            "year_candidates": years, "source": "folder_name", "verified": False}


def is_link(path: Path) -> bool:
    # Windows junctions must also be skipped: they can escape the configured root.
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def load_config(path: Path) -> list[dict]:
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict):
        raise ValueError("Config must be a JSON object containing roots.")
    roots = config.get("roots")
    if not isinstance(roots, list) or not roots:
        raise ValueError("Config must contain a nonempty roots array.")
    seen_ids: set[str] = set()
    resolved: list[dict] = []
    for item in roots:
        if not isinstance(item, dict):
            raise ValueError("Each root must be an object.")
        root_id = item.get("id", "")
        if not isinstance(root_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", root_id) or root_id in seen_ids:
            raise ValueError("Root IDs must be unique and contain only letters, numbers, _ or -.")
        raw = item.get("path")
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"Root {root_id} needs a path.")
        root = Path(os.path.expandvars(raw)).expanduser()
        if not root.is_absolute():
            root = path.parent / root
        if is_link(root):
            raise ValueError(f"Root {root_id} cannot be a symbolic link or junction.")
        root = root.resolve()
        if any(root == old["path"] or root in old["path"].parents or old["path"] in root.parents for old in resolved):
            raise ValueError("Roots must not overlap. Configure each physical location once.")
        hint = item.get("availability_hint", "unknown")
        if hint not in {"unknown", "in_stock", "reserved", "sold", "archived"}:
            raise ValueError(f"Invalid availability_hint for {root_id}.")
        seen_ids.add(root_id)
        resolved.append({"id": root_id, "path": root, "availability_hint": hint})
    return resolved


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_folder(root: dict, folder: Path, settle_seconds: int) -> dict:
    relative = folder.relative_to(root["path"]).as_posix()
    source_key = hashlib.sha256(f"{root['id']}\0{relative.casefold()}".encode("utf-8")).hexdigest()
    record = {
        "source_key": source_key, "root_id": root["id"], "relative_folder": relative,
        "folder_name": folder.name, "hints": folder_hints(folder.name),
        "availability": "unknown", "availability_hint": root["availability_hint"],
        "review_status": "needs_review", "assets": [], "issues": [], "content_fingerprint": None,
    }

    def walk_error(error: OSError) -> None:
        record["issues"].append({"kind": "unreadable_directory", "path": str(error.filename), "message": str(error)})

    for directory, dirs, names in os.walk(folder, onerror=walk_error, followlinks=False):
        safe_dirs = []
        for name in sorted(dirs):
            child = Path(directory) / name
            if is_link(child):
                record["issues"].append({"kind": "link_skipped", "path": child.relative_to(folder).as_posix()})
            else:
                safe_dirs.append(name)
        dirs[:] = safe_dirs
        for name in sorted(names):
            path = Path(directory) / name
            if path.suffix.lower() not in MEDIA_EXTENSIONS:
                continue
            asset = {"relative_path": path.relative_to(folder).as_posix(),
                     "classification": "possible_registration_document" if DOCUMENT_WORDS.search(name) or path.suffix.lower() == ".pdf" else "unreviewed_media",
                     "public_approved": False, "sha256": None}
            if is_link(path):
                record["issues"].append({"kind": "link_skipped", "path": asset["relative_path"]})
                continue
            try:
                before = path.stat()
                asset.update({"bytes": before.st_size, "modified_ns": before.st_mtime_ns})
                if before.st_size == 0 or time.time() - before.st_mtime < settle_seconds:
                    record["issues"].append({"kind": "unsettled_file", "path": asset["relative_path"]})
                else:
                    digest = hash_file(path)
                    after = path.stat()
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        record["issues"].append({"kind": "changed_during_scan", "path": asset["relative_path"]})
                    else:
                        asset["sha256"] = digest
            except OSError as error:
                record["issues"].append({"kind": "unreadable_file", "path": asset["relative_path"], "message": str(error)})
            record["assets"].append(asset)

    if not record["assets"]:
        record["issues"].append({"kind": "no_media"})
    if record["assets"] and not record["issues"]:
        # Set comparison intentionally tolerates renamed/duplicated copies of an image.
        hashes = sorted({asset["sha256"] for asset in record["assets"]})
        record["content_fingerprint"] = hashlib.sha256("\n".join(hashes).encode("ascii")).hexdigest()
    return record


def scan(roots: list[dict], settle_seconds: int = 60) -> dict:
    records, root_results = [], []
    for root in roots:
        result = {"id": root["id"], "path": str(root["path"]), "status": "complete", "issues": []}
        try:
            children = sorted(root["path"].iterdir(), key=lambda child: child.name.casefold())
            for child in children:
                if is_link(child):
                    result["issues"].append({"kind": "link_skipped", "name": child.name})
                elif child.is_dir():
                    record = scan_folder(root, child, settle_seconds)
                    records.append(record)
                    if record["issues"]:
                        result["status"] = "incomplete"
                elif child.suffix.lower() in MEDIA_EXTENSIONS:
                    result["issues"].append({"kind": "media_outside_vehicle_folder", "name": child.name})
        except OSError as error:
            result["status"] = "unavailable"
            result["issues"].append({"kind": "root_unavailable", "message": str(error)})
        if result["issues"] and result["status"] == "complete":
            result["status"] = "incomplete"
        root_results.append(result)
    fingerprints = defaultdict(list)
    for record in records:
        if record["content_fingerprint"]:
            fingerprints[record["content_fingerprint"]].append(record["source_key"])
    return {
        "schema_version": 1, "scanned_at": utc_now(), "mode": "discovery_only",
        "complete": all(root["status"] == "complete" for root in root_results),
        "roots": root_results, "folders": records,
        "duplicate_candidates": [{"content_fingerprint": key, "source_keys": keys}
                                 for key, keys in fingerprints.items() if len(keys) > 1],
    }


def csv_safe(value: object) -> object:
    # Folder names are arbitrary; avoid spreadsheet formula execution on open.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def write_report(manifest: dict, output: Path) -> None:
    # A fresh run directory preserves earlier evidence and avoids partial overwrite.
    output.mkdir(parents=True, exist_ok=False)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    fields = ["source_key", "root_id", "folder", "make_hint", "model_text_hint", "year_hint",
              "availability", "availability_hint", "media_count", "possible_documents", "issues"]
    with (output / "inventory-review.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in manifest["folders"]:
            writer.writerow({key: csv_safe(value) for key, value in dict(
                source_key=record["source_key"], root_id=record["root_id"], folder=record["relative_folder"],
                make_hint=record["hints"]["make"], model_text_hint=record["hints"]["model_text"],
                year_hint=record["hints"]["year"], availability=record["availability"],
                availability_hint=record["availability_hint"], media_count=len(record["assets"]),
                possible_documents=sum(a["classification"] == "possible_registration_document" for a in record["assets"]),
                issues="; ".join(i["kind"] for i in record["issues"]),
            ).items()})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New report directory outside all source roots")
    parser.add_argument("--settle-seconds", type=int, default=60, help="Skip recent or empty files (default: 60)")
    args = parser.parse_args()
    try:
        if args.settle_seconds < 0:
            raise ValueError("settle-seconds must be nonnegative.")
        roots = load_config(args.config.resolve())
        output = args.output.resolve()
        if any(output == root["path"] or root["path"] in output.parents for root in roots):
            raise ValueError("Report output must be outside every source root.")
        if output.exists():
            raise ValueError("Output already exists; choose a new run directory.")
        manifest = scan(roots, args.settle_seconds)
        write_report(manifest, output)
    except (OSError, ValueError, TypeError) as error:
        print(f"Scan failed: {error}", file=sys.stderr)
        return 1
    print(f"Found {len(manifest['folders'])} folders; {len(manifest['duplicate_candidates'])} duplicate candidate groups.")
    print(f"Report: {output}")
    if not manifest["complete"]:
        print("Incomplete scan: check root and file issues. Missing files or drives never imply a sale.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
