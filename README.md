# Dad Project Scripts

Standalone utilities and operational notes for the SellMyCar dealership project. This is separate from the website repository in [`../qatar-drive-deal`](../qatar-drive-deal).

Qatar Drive Deal contains the website code, built and published through Lovable, and its Supabase cloud database migrations. Its current photos and advertisements are demo data for testing the website and workflow.

This folder contains one-time or PC-side tools, their tests, and setup/research notes. Website application features belong in Qatar Drive Deal. See [project instructions](AGENTS.md).

## Contents

```text
dad-project-scripts/
  AGENTS.md
  CONTEXT.md                        # Inventory terminology
  docs/
    inventory-system.md             # Integration and remote-access plan
    research/
      dealer-platform-integrations.md
  scripts/
    inventory/
      README.md                     # Setup, inputs, outputs and limitations
      config.example.json           # Replace sample roots in config.local.json
      scan.py                       # Read-only multi-drive discovery
      tests/
        test_scan.py
  inventory-sync/
    README.md                       # Picasa manifest baseline and change-scan runbook
    picasa_sync.py                  # Read-only exported-copy verification and reports
    manifest.py                     # Strict five-column manifest validation
    sync_state.py                   # Private local SQLite baseline
    tests/
  inventory-local/                  # Private generated reports; ignored
```

## Start here

Follow the [inventory scanner setup](scripts/inventory/README.md), then review the [inventory integration plan](docs/inventory-system.md). Real folder paths and sample layouts are still needed before scanning Dad's inventory.

For the completed Picasa export, follow the [Picasa inventory sync preview](inventory-sync/README.md). It verifies the exported copies and produces private local change reports; it does not upload or publish inventory.

From this folder, validate the scanner with:

```powershell
python -m unittest discover -s scripts/inventory/tests -v
```

The discovery scanner and local Picasa baseline/change reporter are implemented. OCR, authenticated database uploads, review screens, recurring cloud sync and marketplace publication are planned, not implemented. No real inventory has been imported or published by these utilities.

Private reports and machine-specific configuration are excluded by `.gitignore` if version control is added. This folder does not need to be a Git repository to run the utilities.
