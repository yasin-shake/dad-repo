# SellMyCar project instructions

## Source folders

This project uses two sibling source folders:

- **Dad Project Scripts** (this folder, `dad-project-scripts`) holds standalone utilities, one-time scripts, Windows folder scanning/import tools, OCR experiments, reconciliation tools, PC/SSH setup instructions, and their tests and documentation.
- **Qatar Drive Deal** (`../qatar-drive-deal`) is the website repository. Lovable is used for website design, planning, building and publishing; Supabase hosts the cloud database. Website application code, website integrations and database migrations belong there.

Choose the correct folder before creating files. Read the destination's local instructions before editing. Keep miscellaneous PC utilities here; do not duplicate them into the website repository. Promote shared behavior into the website only when it becomes an intentional application feature. Keep cross-folder references accurate.

## Current state

The website currently contains fake/sample photos and advertisements to test its design and workflow. Treat them as demo data, not evidence of real inventory, availability, sales, or production readiness. Real stock comes from Dad's reviewed source folders and verified dealership records.

Dad's PC is in Qatar and runs Windows; the user is in the UAE. Inventory photos are spread across multiple PC paths and external drives, usually one folder per car with make/model/year in the name. Registration cards may provide additional candidate details. Exact paths are machine-specific configuration, not hard-coded defaults.

## Working rules

- Organize utilities by purpose under `scripts/`, keep their tests with the utility, and maintain setup/usage notes. Put integration plans and sourced research under `docs/`.
- Preserve original inventory files. Start discovery with read-only reports; make incomplete scans, offline drives and ambiguous identity visible.
- Distinguish confirmed vehicle availability from a channel's listing status. A missing advert or disconnected drive never proves a sale. Identical make/model/year does not identify a physical vehicle.
- Treat folder parsing, OCR and marketplace observations as reviewable evidence. Keep registration cards, personal information, local configuration and reports private; never put them into public website assets.
- Keep generated descriptions and photos subject to review and publication approval. Verify platform-supported access before adding marketplace automation.
- Store credentials outside source files. Do not place a Supabase service-role secret on the PC or in reports.
- Run relevant checks from this folder. For inventory discovery: `python -m unittest discover -s scripts/inventory/tests -v`.
- When editing Qatar Drive Deal, preserve its Lovable history: do not force-push or rewrite already-published commits. Keep the connected branch working.
