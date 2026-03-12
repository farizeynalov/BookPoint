param(
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $projectRoot

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutputPath = "backups/bookpoint_$timestamp.sql"
}

$dbUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "bookpoint" }
$dbName = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "bookpoint" }
$resolvedOutput = [System.IO.Path]::GetFullPath((Join-Path $projectRoot $OutputPath))
$outputDirectory = Split-Path -Parent $resolvedOutput
if (-not (Test-Path $outputDirectory)) {
    New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
}

Write-Host "[backup] creating database backup at $resolvedOutput"
$composeArgs = @("compose", "exec", "-T", "db", "pg_dump", "-U", $dbUser, "-d", $dbName)
& docker @composeArgs > $resolvedOutput
if ($LASTEXITCODE -ne 0) {
    throw "Backup failed."
}
Write-Host "[backup] backup completed: $resolvedOutput"
