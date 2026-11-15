# Windows inventory discovery

This utility belongs to **Dad Project Scripts** (`dad-project-scripts`). The website is maintained separately in the sibling `qatar-drive-deal` folder. Its current photos and adverts are demo data, not a stock register.

This is the first, read-only step of the [inventory integration plan](../../docs/inventory-system.md). It works without cloud credentials or third-party Python packages. It is **not yet a database importer, OCR service, folder watcher, or marketplace publisher**.

## Prepare

1. Install Python 3.11 or newer on the dealership PC, if it is not already available. The Windows Python launcher must support `py -3` (or substitute the installed `python` executable).
2. Copy Dad Project Scripts or at least its `scripts/inventory` directory to that PC.
3. Copy `config.example.json` to `config.local.json` and replace the example paths with real paths. Keep the `id` for each physical collection stable if a drive letter changes. Relative paths resolve against the configuration file's directory; JSON Windows paths need doubled backslashes.
4. A configured root must contain **one immediate subfolder per vehicle**. Media in nested folders such as `edited` is included in that vehicle. For layouts like `E:\\Photos\\2023\\Toyota Camry`, configure `E:\\Photos\\2023` as a root. If the whole root is itself one car, configure its parent or reorganize the configuration before running. The scanner does not automatically discover layout boundaries.

Example layout:

```text
C:\DealerPhotos\Cars\
  Toyota Camry 2022\
    front.jpg
    edited\rear.jpg
    registration.jpg
  Lexus LX600 2023\
    IMG_0001.jpg
E:\CarArchive\
  Nissan Patrol 2019\
    side.jpg
```

## Run from the Dad Project Scripts directory in PowerShell

```powershell
Copy-Item scripts\inventory\config.example.json scripts\inventory\config.local.json
# Edit config.local.json with the real roots before the next command.
$scanRun = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
py -3 scripts\inventory\scan.py --config scripts\inventory\config.local.json --output "inventory-local\$scanRun"
```

The output directory must be new and outside every configured source root. The script reads source media and writes only the requested reports. It never modifies, deletes, or uploads source files. Photos may take a long time to hash on external drives; each run reads every supported file in full. There is no persistent change cache yet.

Output:

- `manifest.json`: folder identities, relative asset paths, SHA-256 content hashes, folder-name hints, root completeness, file issues, and exact-content duplicate candidate groups.
- `inventory-review.csv`: a spreadsheet for reviewing folder names, tentative vehicle details, media counts, and issues. **Do not upload it into the website's existing CSV importer.** It is a discovery report, without confirmed prices, mileage, identity or publication data.

Exit codes: `0` means discovery completed; `2` means a drive/folder/file was unavailable, skipped or still changing; `1` means configuration/output failure. A complete scan does not mean the proposed vehicle details are correct. Check partial reports and rerun after the drive is connected or copying finishes. Empty folders remain review items. Source media placed directly inside a root is reported as a layout issue.

## Interpretation

- Every vehicle starts with availability `unknown`. Optional per-root `availability_hint` values are unverified suggestions only; an archive drive does not prove a sale.
- Make/year suggestions use a small alias list and folder text. `model_text` may contain trim or other notes. Arabic-only names or abbreviated makes may remain unknown. Never treat these suggestions as confirmed specifications.
- Files less than 60 seconds old, empty files, unreadable files, and files changed during hashing are deferred. Symbolic links and Windows junctions are skipped. Pause editing/copying while scanning for the best snapshot; the time check cannot establish that a slow copy has finished.
- Media includes common photo formats and PDFs; other extensions are ignored. PDF/HEIC entries are inventoried, not converted. A known registration filename gets flagged, but an ordinary filename can still contain a registration card. **All assets start private and unapproved.** There is no reliable automatic document classifier here.
- Equal complete media-content sets across folders are **duplicate candidates**, never automatic merges. Shared content in otherwise different folders is visible in the individual asset hashes but not grouped. Generic shared photos can cause false matches. Identical make/model/year alone never deduplicates vehicles.
- A source key identifies a root plus relative folder path, not the physical vehicle. It survives drive relocation with the same root ID, but a folder rename creates a new key. The planned importer must reconcile renames and copies rather than assuming every new key is a new car.
- Reports include private paths and image fingerprints. Keep them private. This folder's `.gitignore` excludes `inventory-local/` and `config.local.json` if Git is used later; use that output location when running in Dad Project Scripts. A custom output location needs its own exclusion.

Run the scanner's checks from the Dad Project Scripts directory:

```powershell
py -3 -m unittest discover -s scripts/inventory/tests -v
```

The next step is to inspect a real report and sample folder layouts, then implement the authenticated staging upload and review screen described in the plan.
