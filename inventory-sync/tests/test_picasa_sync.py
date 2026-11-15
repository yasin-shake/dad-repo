from __future__ import annotations

import csv
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


SYNC_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SYNC_DIR))

import picasa_sync  # noqa: E402
from manifest import ManifestError, load_manifest  # noqa: E402
from sync_state import read_baseline  # noqa: E402


HEADERS = ["Album", "Album ID", "Original", "Exported", "Status"]
DECLARED_ROOT = r"C:\Picasa Exported Albums"


class PicasaSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.exports = self.root / "exports"
        self.local = self.root / "local"
        self.exports.mkdir()
        self.local.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_file(self, album: str, name: str, content: bytes) -> Path:
        path = self.exports / album / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def row(
        self,
        album: str,
        album_id: str,
        name: str,
        *,
        status: str = "Copied",
        original: str | None = None,
    ) -> dict[str, str]:
        return {
            "Album": album,
            "Album ID": album_id,
            "Original": original or rf"G:\private-source\{name}",
            "Exported": rf"{DECLARED_ROOT}\{album}\{name}",
            "Status": status,
        }

    def manifest(self, name: str, rows: list[dict[str, str]]) -> Path:
        path = self.local / name
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=HEADERS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        return path

    def run_baseline(self, manifest: Path, state: Path | None = None) -> tuple[int, Path]:
        state = state or self.local / "state.sqlite"
        result = picasa_sync.main(
            [
                "baseline",
                "--manifest",
                str(manifest),
                "--export-root",
                str(self.exports),
                "--state",
                str(state),
            ]
        )
        return result, state

    def test_baseline_verifies_exported_copies_without_reading_originals(self) -> None:
        self.make_file("Toyota Prado", "front.jpg", b"front")
        self.make_file("Toyota Prado", "rear.jpg", b"rear")
        manifest = self.manifest(
            "baseline.csv",
            [
                self.row("Toyota Prado", "album-1", "front.jpg", original=r"Z:\offline\front.jpg"),
                self.row("Toyota Prado", "album-1", "rear.jpg", original=r"Z:\offline\rear.jpg"),
            ],
        )

        exit_code, state_path = self.run_baseline(manifest)

        self.assertEqual(0, exit_code)
        state = read_baseline(state_path)
        self.assertEqual({"album-1": "Toyota Prado"}, state.albums)
        self.assertEqual(2, len(state.files))
        self.assertEqual(2, len(state.memberships))
        with closing(sqlite3.connect(state_path)) as connection:
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(files)")
            }
        self.assertNotIn("original_path", columns)

    def test_single_album_manifest_infers_export_root(self) -> None:
        path = self.manifest("one.csv", [self.row("Leisure", "a", "one.jpg")])
        loaded = load_manifest(path)
        self.assertEqual(DECLARED_ROOT, loaded.declared_export_root)
        self.assertEqual("Leisure/one.jpg", loaded.entries[0].relative_path)

    def test_scan_reports_rename_add_remove_modify_and_reuses_hashes(self) -> None:
        unchanged = self.make_file("Alpha", "same.jpg", b"same")
        changed = self.make_file("Alpha", "changed.jpg", b"before")
        self.make_file("Old", "removed.jpg", b"removed")
        baseline_manifest = self.manifest(
            "baseline.csv",
            [
                self.row("Alpha", "album-a", "same.jpg"),
                self.row("Alpha", "album-a", "changed.jpg"),
                self.row("Old", "album-old", "removed.jpg"),
            ],
        )
        exit_code, state = self.run_baseline(baseline_manifest)
        self.assertEqual(0, exit_code)

        old_mtime = changed.stat().st_mtime_ns
        changed.write_bytes(b"after!")
        os.utime(changed, ns=(old_mtime + 2_000_000_000, old_mtime + 2_000_000_000))
        self.make_file("New Car", "new.jpg", b"new")
        latest = self.manifest(
            "latest.csv",
            [
                self.row("Alpha Renamed", "album-a", "same.jpg") | {
                    "Exported": rf"{DECLARED_ROOT}\Alpha\same.jpg"
                },
                self.row("Alpha Renamed", "album-a", "changed.jpg") | {
                    "Exported": rf"{DECLARED_ROOT}\Alpha\changed.jpg"
                },
                self.row("New Car", "album-new", "new.jpg"),
            ],
        )
        report = self.local / "report.json"

        scan_exit = picasa_sync.main(
            [
                "scan",
                "--manifest",
                str(latest),
                "--export-root",
                str(self.exports),
                "--state",
                str(state),
                "--report",
                str(report),
            ]
        )

        self.assertEqual(0, scan_exit)
        data = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(1, data["summary"]["albums_added"])
        self.assertEqual(1, data["summary"]["albums_removed"])
        self.assertEqual(1, data["summary"]["albums_renamed"])
        self.assertEqual(1, data["summary"]["files_modified"])
        self.assertEqual(1, data["summary"]["reused_hashes"])
        self.assertEqual("missing_from_manifest_not_proof_of_sale", data["albums"]["removed"][0]["interpretation"])
        self.assertTrue(unchanged.is_file())

    def test_scan_writes_partial_report_for_missing_new_export(self) -> None:
        self.make_file("Alpha", "one.jpg", b"one")
        baseline_manifest = self.manifest("baseline.csv", [self.row("Alpha", "a", "one.jpg")])
        exit_code, state = self.run_baseline(baseline_manifest)
        self.assertEqual(0, exit_code)
        latest = self.manifest(
            "latest.csv",
            [self.row("Alpha", "a", "one.jpg"), self.row("Beta", "b", "missing.jpg")],
        )
        report = self.local / "partial.json"

        scan_exit = picasa_sync.main(
            [
                "scan",
                "--manifest",
                str(latest),
                "--export-root",
                str(self.exports),
                "--state",
                str(state),
                "--report",
                str(report),
            ]
        )

        self.assertEqual(2, scan_exit)
        data = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual("missing_export", data["issues"][0]["kind"])
        self.assertEqual("Beta/missing.jpg", data["memberships"]["added"][0]["relative_path"])

    def test_baseline_is_not_saved_when_manifest_status_failed(self) -> None:
        self.make_file("Alpha", "one.jpg", b"one")
        manifest = self.manifest(
            "failed.csv", [self.row("Alpha", "a", "one.jpg", status="Failed")]
        )
        exit_code, state = self.run_baseline(manifest)
        self.assertEqual(2, exit_code)
        self.assertFalse(state.exists())

    def test_baseline_refuses_to_replace_existing_state_without_flag(self) -> None:
        self.make_file("Alpha", "one.jpg", b"one")
        manifest = self.manifest("baseline.csv", [self.row("Alpha", "a", "one.jpg")])
        first, state = self.run_baseline(manifest)
        second, _ = self.run_baseline(manifest, state)
        self.assertEqual(0, first)
        self.assertEqual(1, second)

    def test_duplicate_content_is_reported_without_merging(self) -> None:
        self.make_file("Alpha", "one.jpg", b"duplicate")
        self.make_file("Beta", "two.jpg", b"duplicate")
        manifest = self.manifest(
            "baseline.csv",
            [self.row("Alpha", "a", "one.jpg"), self.row("Beta", "b", "two.jpg")],
        )
        loaded = load_manifest(manifest)
        result = picasa_sync.scan_exports(loaded, self.exports)
        groups = picasa_sync.duplicate_groups(result.files)
        self.assertEqual(1, len(groups))
        self.assertEqual(2, len(groups[0]["paths"]))
        self.assertEqual(2, len(result.memberships))

    def test_rejects_bad_columns_and_outputs_inside_export_tree(self) -> None:
        bad = self.local / "bad.csv"
        bad.write_text("Album,Exported\nAlpha,C:\\\\x.jpg\n", encoding="utf-8")
        with self.assertRaises(ManifestError):
            load_manifest(bad)

        self.make_file("Alpha", "one.jpg", b"one")
        manifest = self.manifest("baseline.csv", [self.row("Alpha", "a", "one.jpg")])
        exit_code, _ = self.run_baseline(manifest, self.exports / "state.sqlite")
        self.assertEqual(1, exit_code)
        self.assertFalse((self.exports / "state.sqlite").exists())


if __name__ == "__main__":
    unittest.main()
