from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SYNC_DIR = Path(__file__).resolve().parents[1]
RUNNER = SYNC_DIR / "run.ps1"


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell.exe"), "Windows PowerShell required")
class PowerShellRunnerTests(unittest.TestCase):
    def test_initialize_status_and_scan_use_private_local_working_area(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            export_root = root / "Picasa Exported Albums"
            photo = export_root / "Alpha" / "one.jpg"
            photo.parent.mkdir(parents=True)
            photo.write_bytes(b"unchanged exported copy")
            manifest = root / "picasa_export_manifest.csv"
            with manifest.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=["Album", "Album ID", "Original", "Exported", "Status"],
                    lineterminator="\n",
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "Album": "Alpha",
                        "Album ID": "album-a",
                        "Original": r"G:\offline\one.jpg",
                        "Exported": r"C:\Picasa Exported Albums\Alpha\one.jpg",
                        "Status": "Copied",
                    }
                )

            local = root / "private-local"
            environment = os.environ.copy()
            environment["INVENTORY_SYNC_LOCAL_DIR"] = str(local)

            initialized = self.run_runner(
                "initialize",
                "-ExportRoot",
                str(export_root),
                "-Manifest",
                str(manifest),
                environment=environment,
            )
            self.assertEqual(0, initialized.returncode, initialized.stdout + initialized.stderr)
            self.assertTrue((local / "sync_state.sqlite").is_file())
            config = json.loads((local / "config.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(str(export_root.resolve()), config["export_root"])

            status = self.run_runner("status", environment=environment)
            self.assertEqual(0, status.returncode, status.stdout + status.stderr)
            self.assertIn("Baseline state present: True", status.stdout)

            scanned = self.run_runner(
                "scan", "-Manifest", str(manifest), environment=environment
            )
            self.assertEqual(0, scanned.returncode, scanned.stdout + scanned.stderr)
            reports = list((local / "reports").glob("latest-*.json"))
            self.assertEqual(1, len(reports))
            self.assertEqual(b"unchanged exported copy", photo.read_bytes())
            self.assertEqual(["Alpha"], [item.name for item in export_root.iterdir()])

    @staticmethod
    def run_runner(*arguments: str, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(RUNNER),
                *arguments,
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            timeout=30,
        )
