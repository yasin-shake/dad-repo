# Picasa inventory sync preview

This Windows utility verifies the exported copies described by a Picasa CSV manifest, creates a private local SQLite baseline, and compares later exports with that baseline. It is the safe first stage of inventory synchronization: it does **not** modify original or exported photos, upload to Supabase, change Qatar Drive Deal, publish listings, or infer that a missing album means a vehicle was sold.

The uploaded reference manifest was validated with 19,509 `Copied` rows, 507 stable album IDs and these exact columns:

```text
Album,Album ID,Original,Exported,Status
```

Only the manifest format is reflected in this repository. The real manifest, local paths, reports and SQLite state are private and are not committed.

## Requirements

- Windows 10/11 with Python 3.11 or newer. `py -3` is used below; substitute `python` if needed.
- A fresh Picasa export and its CSV manifest.
- Read permission for the export folder and write permission for `inventory-sync\local`.
- No Python packages, cloud credentials or Supabase secrets are required.

## Quick start on Dad's PC through VNC

SSH is not required when operating the Qatar PC directly through VNC. The current export folder is `F:\Picasa Exported Albums`. The helper below records that machine-specific path in `inventory-sync\local\config.json`, which Git ignores, rather than hard-coding it into the program.

Open PowerShell and get the code:

```powershell
Set-Location C:\
git clone https://github.com/yasin-shake/dad-repo.git C:\dad-project-scripts
Set-Location C:\dad-project-scripts
```

If the repository is already there, update it instead:

```powershell
Set-Location C:\dad-project-scripts
git switch main
git pull --ff-only origin main
```

Then initialize the private local configuration and baseline with one command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\inventory-sync\run.ps1 initialize `
  -ExportRoot 'F:\Picasa Exported Albums'
```

The runner automatically uses the manifest when exactly one `picasa_export_manifest*.csv` file is in the export folder or its parent. If it reports that none or several were found, provide the correct file explicitly:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\inventory-sync\run.ps1 initialize `
  -ExportRoot 'F:\Picasa Exported Albums' `
  -Manifest 'F:\full\path\to\picasa_export_manifest.csv'
```

The baseline is saved only when every manifest row has status `Copied` and every exported file can be read without changing during hashing. Exit code `0` means it was saved; `2` means the export is incomplete or unreadable; `1` means the manifest, arguments or state are invalid. An existing state file is not replaced unless `-ReplaceState` is explicitly supplied to the runner.

The utility reads the exported copies, not the `Original` paths. It records relative export paths, sizes, timestamps and SHA-256 hashes. It does not store original source paths in SQLite.

## Compare a later Picasa export

After exporting Picasa again, run one command with the new manifest. The runner keeps a private timestamped copy and report:

```powershell
Set-Location C:\dad-project-scripts
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\inventory-sync\run.ps1 scan `
  -Manifest 'F:\full\path\to\new_picasa_export_manifest.csv'
```

The report contains added, renamed and missing albums; added/removed album-photo associations; modified content; missing/unreadable exports; and exact-content duplicate candidates. Unchanged files reuse baseline hashes when size and modification time match. Duplicate hashes are evidence for review and are never automatically merged. Removed albums are explicitly labelled as not proving a sale.

Exit code `2` still writes a partial report so offline drives, missing exports and incomplete scans stay visible. Reports can expose private album and file names, so keep `inventory-sync\local` private and do not copy it into website assets.

Check the saved path and baseline at any time:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\inventory-sync\run.ps1 status
```

Run the sync utility's tests with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\inventory-sync\run.ps1 test
```

## Optional SSH over Tailscale

This section is optional now that you are operating directly through VNC. Tailscale provides the private network path; Windows OpenSSH Server provides SSH. On Dad's PC, use an elevated PowerShell window for installation and firewall setup:

```powershell
Get-WindowsCapability -Online -Name OpenSSH.Server*
# Run the next line only if OpenSSH.Server is NotPresent.
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic

# Replace this with the UAE computer's actual Tailscale IPv4 address.
Set-NetFirewallRule -Name OpenSSH-Server-In-TCP -RemoteAddress '<UAE-PC-Tailscale-IPv4>'

whoami
tailscale ip -4
```

From the UAE computer:

```powershell
tailscale ping <QATAR-PC-TAILSCALE-IPV4>
ssh <WINDOWS-USERNAME>@<QATAR-PC-TAILSCALE-IPV4>
```

Use the Windows account password, not a Windows Hello PIN, until key authentication is configured. Verify the SSH host fingerprint with the Qatar PC and keep a recovery/remote-desktop path while testing firewall changes. No router port forwarding is needed. The PC must remain powered on and awake, and the SSH account must be able to read `F:\Picasa Exported Albums`.

After connecting, verify the location and run the baseline commands above:

```powershell
hostname
whoami
Test-Path 'F:\Picasa Exported Albums'
Set-Location C:\dad-project-scripts
```

## Tests

From the repository root:

```powershell
py -3 -m unittest discover -s inventory-sync\tests -v
```

The tests use temporary fake exports. They do not use or copy the uploaded real manifest, registration cards, or inventory photographs.
