[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('initialize', 'baseline', 'scan', 'status', 'test')]
    [string]$Action = 'status',

    [string]$ExportRoot,
    [string]$Manifest,
    [switch]$ReplaceState
)

$ErrorActionPreference = 'Stop'
$SyncDirectory = $PSScriptRoot
$RepositoryRoot = Split-Path -Parent $SyncDirectory
if ([string]::IsNullOrWhiteSpace($env:INVENTORY_SYNC_LOCAL_DIR)) {
    $LocalDirectory = Join-Path $SyncDirectory 'local'
}
else {
    $LocalDirectory = [System.IO.Path]::GetFullPath($env:INVENTORY_SYNC_LOCAL_DIR)
}
$ManifestDirectory = Join-Path $LocalDirectory 'manifests'
$ReportDirectory = Join-Path $LocalDirectory 'reports'
$ConfigPath = Join-Path $LocalDirectory 'config.json'
$StatePath = Join-Path $LocalDirectory 'sync_state.sqlite'
$PythonScript = Join-Path $SyncDirectory 'picasa_sync.py'


function New-LocalDirectories {
    New-Item -ItemType Directory -Force -Path $ManifestDirectory | Out-Null
    New-Item -ItemType Directory -Force -Path $ReportDirectory | Out-Null
}


function Get-PythonCommand {
    $Candidates = @(
        @{ Name = 'py'; Prefix = @('-3') },
        @{ Name = 'python'; Prefix = @() }
    )
    foreach ($Candidate in $Candidates) {
        $Command = Get-Command $Candidate.Name -ErrorAction SilentlyContinue
        if ($null -eq $Command) {
            continue
        }
        $CheckArguments = @($Candidate.Prefix) + @(
            '-c',
            'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'
        )
        $PreviousPreference = $ErrorActionPreference
        $ErrorActionPreference = 'SilentlyContinue'
        try {
            & $Command.Source @CheckArguments *> $null
            $CheckExitCode = $LASTEXITCODE
        }
        catch {
            $CheckExitCode = 1
        }
        finally {
            $ErrorActionPreference = $PreviousPreference
        }
        if ($CheckExitCode -eq 0) {
            return @{
                Executable = $Command.Source
                Prefix = @($Candidate.Prefix)
            }
        }
    }
    throw 'Python 3.11 or newer was not found. Install Python, then reopen PowerShell.'
}


function Resolve-ExportDirectory([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw 'Provide -ExportRoot when initializing.'
    }
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "Export folder is not accessible: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}


function Save-Configuration([string]$ResolvedExportRoot) {
    New-LocalDirectories
    [ordered]@{
        export_root = $ResolvedExportRoot
    } | ConvertTo-Json | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
    Write-Host "Saved private local configuration: $ConfigPath"
}


function Get-Configuration {
    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
        throw "Local configuration is missing. Run the initialize action with the PC's current -ExportRoot path."
    }
    $Config = Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
    if ([string]::IsNullOrWhiteSpace($Config.export_root)) {
        throw "Local configuration is invalid: $ConfigPath"
    }
    if (-not (Test-Path -LiteralPath $Config.export_root -PathType Container)) {
        throw "Configured export folder is offline or unavailable: $($Config.export_root)"
    }
    return $Config
}


function Find-Manifest([string]$RequestedPath, [string]$ResolvedExportRoot) {
    if (-not [string]::IsNullOrWhiteSpace($RequestedPath)) {
        if (-not (Test-Path -LiteralPath $RequestedPath -PathType Leaf)) {
            throw "Manifest is not accessible: $RequestedPath"
        }
        return (Resolve-Path -LiteralPath $RequestedPath).Path
    }

    $SearchFolders = @($ResolvedExportRoot, (Split-Path -Parent $ResolvedExportRoot)) |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        Select-Object -Unique
    $Candidates = @(
        foreach ($Folder in $SearchFolders) {
            Get-ChildItem -LiteralPath $Folder -File -Filter 'picasa_export_manifest*.csv' -ErrorAction SilentlyContinue
        }
    ) | Sort-Object FullName -Unique

    if ($Candidates.Count -eq 1) {
        Write-Host "Using discovered manifest: $($Candidates[0].FullName)"
        return $Candidates[0].FullName
    }
    if ($Candidates.Count -gt 1) {
        $List = ($Candidates.FullName | ForEach-Object { "  $_" }) -join [Environment]::NewLine
        throw "More than one manifest was found. Rerun with -Manifest and the correct path:$([Environment]::NewLine)$List"
    }
    throw 'No Picasa manifest was found beside the export folder. Rerun with -Manifest and its full path.'
}


function Copy-PrivateManifest([string]$SourcePath, [string]$DestinationName) {
    New-LocalDirectories
    $Destination = Join-Path $ManifestDirectory $DestinationName
    if (-not [string]::Equals(
        (Resolve-Path -LiteralPath $SourcePath).Path,
        [System.IO.Path]::GetFullPath($Destination),
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        Copy-Item -LiteralPath $SourcePath -Destination $Destination -Force
    }
    return $Destination
}


function Invoke-SyncPython([string[]]$Arguments) {
    $Python = Get-PythonCommand
    $AllArguments = @($Python.Prefix) + @($PythonScript) + $Arguments
    & $Python.Executable @AllArguments
    $ExitCode = $LASTEXITCODE
    if ($ExitCode -ne 0) {
        exit $ExitCode
    }
}


function Invoke-Baseline([string]$ResolvedExportRoot, [string]$ManifestPath) {
    $PrivateManifest = Copy-PrivateManifest $ManifestPath 'baseline.csv'
    $Arguments = @(
        'baseline',
        '--manifest', $PrivateManifest,
        '--export-root', $ResolvedExportRoot,
        '--state', $StatePath
    )
    if ($ReplaceState) {
        $Arguments += '--replace-state'
    }
    Invoke-SyncPython $Arguments
}


switch ($Action) {
    'initialize' {
        $ResolvedExportRoot = Resolve-ExportDirectory $ExportRoot
        Save-Configuration $ResolvedExportRoot
        $ManifestPath = Find-Manifest $Manifest $ResolvedExportRoot
        Invoke-Baseline $ResolvedExportRoot $ManifestPath
        Write-Host ''
        Write-Host 'Initialization complete. For later exports, run:'
        Write-Host ".\inventory-sync\run.ps1 scan -Manifest 'FULL_PATH_TO_NEW_MANIFEST.csv'"
    }
    'baseline' {
        $Config = Get-Configuration
        $ManifestPath = Find-Manifest $Manifest $Config.export_root
        Invoke-Baseline $Config.export_root $ManifestPath
    }
    'scan' {
        $Config = Get-Configuration
        if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
            throw 'The baseline state is missing. Run the initialize action first.'
        }
        $ManifestPath = Find-Manifest $Manifest $Config.export_root
        $Timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $PrivateManifest = Copy-PrivateManifest $ManifestPath "latest-$Timestamp.csv"
        $ReportPath = Join-Path $ReportDirectory "latest-$Timestamp.json"
        Invoke-SyncPython @(
            'scan',
            '--manifest', $PrivateManifest,
            '--export-root', $Config.export_root,
            '--state', $StatePath,
            '--report', $ReportPath
        )
        Write-Host "Private report: $ReportPath"
    }
    'status' {
        Write-Host "Repository: $RepositoryRoot"
        Write-Host "Local config present: $(Test-Path -LiteralPath $ConfigPath -PathType Leaf)"
        Write-Host "Baseline state present: $(Test-Path -LiteralPath $StatePath -PathType Leaf)"
        if (Test-Path -LiteralPath $ConfigPath -PathType Leaf) {
            $Config = Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
            Write-Host "Export folder: $($Config.export_root)"
            Write-Host "Export folder accessible: $(Test-Path -LiteralPath $Config.export_root -PathType Container)"
        }
        Write-Host "Private reports: $ReportDirectory"
    }
    'test' {
        $Python = Get-PythonCommand
        $Arguments = @($Python.Prefix) + @(
            '-m', 'unittest', 'discover',
            '-s', (Join-Path $SyncDirectory 'tests'),
            '-v'
        )
        & $Python.Executable @Arguments
        exit $LASTEXITCODE
    }
}
