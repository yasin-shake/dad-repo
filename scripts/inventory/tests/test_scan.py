import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.inventory.scan import folder_hints, load_config, scan, write_report


class InventoryScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "cars"
        self.root.mkdir()
        self.roots = [{"id": "pc", "path": self.root, "availability_hint": "sold"}]

    def photo(self, folder, content=b"photo", name="front.jpg"):
        path = self.root / folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_folder_information_is_unverified_and_multiple_years_are_ambiguous(self):
        hint = folder_hints("2022_Toyota_Land_Cruiser_GXR")
        self.assertEqual((hint["make"], hint["year"]), ("Toyota", 2022))
        self.assertEqual(hint["model_text"], "Land Cruiser GXR")
        self.assertFalse(hint["verified"])
        self.assertIsNone(folder_hints("Toyota 2022 registered 2023")["year"])

    def test_range_rover_model_is_not_discarded(self):
        self.assertEqual(folder_hints("Range Rover Sport 2021")["model_text"], "Range Rover Sport")

    def test_same_make_model_year_does_not_merge_different_cars(self):
        self.photo("Toyota Camry 2022", b"car-one")
        self.photo("Toyota Camry 2022 second", b"car-two")
        manifest = scan(self.roots, 0)
        self.assertEqual(len(manifest["folders"]), 2)
        self.assertEqual(manifest["duplicate_candidates"], [])
        self.assertNotEqual(*[folder["source_key"] for folder in manifest["folders"]])

    def test_copies_across_roots_are_candidates_and_never_auto_merged(self):
        self.photo("Toyota Camry 2022", b"same-photo")
        backup = self.base / "backup"
        (backup / "renamed").mkdir(parents=True)
        (backup / "renamed" / "copy.png").write_bytes(b"same-photo")
        roots = self.roots + [{"id": "backup", "path": backup, "availability_hint": "unknown"}]
        manifest = scan(roots, 0)
        self.assertEqual(len(manifest["folders"]), 2)
        self.assertEqual(len(manifest["duplicate_candidates"]), 1)
        self.assertTrue(all(f["availability"] == "unknown" for f in manifest["folders"]))

    def test_source_identity_survives_drive_relocation_with_same_root_id(self):
        self.photo("Camry")
        first = scan(self.roots, 0)["folders"][0]["source_key"]
        moved = self.base / "moved"
        self.root.rename(moved)
        self.roots[0]["path"] = moved
        self.assertEqual(scan(self.roots, 0)["folders"][0]["source_key"], first)

    def test_missing_drive_is_incomplete_without_status_inference(self):
        self.photo("car")
        roots = self.roots + [{"id": "offline", "path": self.base / "missing", "availability_hint": "unknown"}]
        manifest = scan(roots, 0)
        self.assertFalse(manifest["complete"])
        self.assertEqual(manifest["roots"][1]["status"], "unavailable")
        self.assertEqual(manifest["folders"][0]["availability"], "unknown")

    def test_recent_files_are_deferred_and_do_not_create_duplicate_candidates(self):
        self.photo("car")
        manifest = scan(self.roots, 3600)
        self.assertFalse(manifest["complete"])
        folder = manifest["folders"][0]
        self.assertIsNone(folder["assets"][0]["sha256"])
        self.assertIsNone(folder["content_fingerprint"])
        self.assertEqual(folder["issues"][0]["kind"], "unsettled_file")

    def test_changing_file_is_deferred(self):
        photo = self.photo("car")
        def changing_hash(path):
            photo.write_bytes(b"changed-during-read")
            return "a" * 64
        with patch("scripts.inventory.scan.hash_file", side_effect=changing_hash):
            manifest = scan(self.roots, 0)
        self.assertFalse(manifest["complete"])
        self.assertIsNone(manifest["folders"][0]["assets"][0]["sha256"])

    def test_all_media_private_even_if_document_name_is_unrecognized(self):
        self.photo("car", name="registration.jpg")
        self.photo("car", name="IMG_1923.jpg")
        self.photo("car", name="edits/front.png")
        assets = scan(self.roots, 0)["folders"][0]["assets"]
        self.assertEqual(len(assets), 3)
        self.assertTrue(all(not a["public_approved"] for a in assets))
        self.assertEqual(next(a for a in assets if a["relative_path"] == "registration.jpg")["classification"], "possible_registration_document")

    def test_unreadable_file_is_reported_without_stopping_other_folders(self):
        self.photo("car-one")
        self.photo("car-two")
        with patch("scripts.inventory.scan.hash_file", side_effect=PermissionError("locked")):
            manifest = scan(self.roots, 0)
        self.assertEqual(len(manifest["folders"]), 2)
        self.assertFalse(manifest["complete"])
        self.assertTrue(all(f["issues"][0]["kind"] == "unreadable_file" for f in manifest["folders"]))

    def test_overlapping_roots_are_rejected(self):
        config = self.base / "config.json"
        config.write_text(json.dumps({"roots": [{"id": "a", "path": str(self.root)}, {"id": "b", "path": str(self.root / "nested")}]}))
        with self.assertRaisesRegex(ValueError, "overlap"):
            load_config(config)

    def test_duplicate_root_ids_are_rejected(self):
        config = self.base / "config.json"
        config.write_text(json.dumps({"roots": [{"id": "a", "path": str(self.root)}, {"id": "a", "path": str(self.base / "backup")}]}))
        with self.assertRaisesRegex(ValueError, "unique"):
            load_config(config)

    def test_malformed_top_level_configuration_is_rejected(self):
        config = self.base / "config.json"
        config.write_text("[]")
        with self.assertRaisesRegex(ValueError, "JSON object"):
            load_config(config)

    def test_cli_creates_complete_report_and_partial_report_has_distinct_exit(self):
        self.photo("Toyota Camry 2022")
        config = self.base / "config.json"
        config.write_text(json.dumps({"roots": [{"id": "pc", "path": str(self.root)}]}))
        output = self.base / "cli-report"
        command = [sys.executable, "scripts/inventory/scan.py", "--config", str(config), "--settle-seconds", "0", "--output", str(output)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((output / "manifest.json").read_text())["folders"][0]["availability"], "unknown")
        config.write_text(json.dumps({"roots": [{"id": "pc", "path": str(self.base / "offline")}]}))
        command[-1] = str(self.base / "partial-report")
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(json.loads((self.base / "partial-report" / "manifest.json").read_text())["complete"])

    def test_report_preserves_previous_runs_and_neutralizes_csv_formulas(self):
        photo = self.photo("=SUM(1)")
        manifest = scan(self.roots, 0)
        output = self.base / "report"
        write_report(manifest, output)
        self.assertIn("'=SUM(1)", (output / "inventory-review.csv").read_text(encoding="utf-8-sig"))
        with self.assertRaises(FileExistsError):
            write_report(manifest, output)
        self.assertEqual(photo.read_bytes(), b"photo")

    def test_cli_rejects_output_inside_source_before_writing(self):
        config = self.base / "config.json"
        config.write_text(json.dumps({"roots": [{"id": "pc", "path": str(self.root)}]}))
        output = self.root / "report"
        result = subprocess.run([sys.executable, "scripts/inventory/scan.py", "--config", str(config), "--output", str(output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(output.exists())

    def test_links_are_skipped(self):
        self.photo("car")
        linked = self.root / "linked"
        try:
            linked.symlink_to(self.root / "car", target_is_directory=True)
        except OSError:
            self.skipTest("Creating symbolic links requires Windows privileges.")
        manifest = scan(self.roots, 0)
        self.assertEqual(len(manifest["folders"]), 1)
        self.assertFalse(manifest["complete"])


if __name__ == "__main__":
    unittest.main()
