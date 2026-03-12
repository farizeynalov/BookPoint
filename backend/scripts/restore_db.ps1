param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $projectRoot

$resolvedInput = [System.IO.Path]::GetFullPath((Join-Path $projectRoot $InputPath))
if (-not (Test-Path $resolvedInput)) {
    throw "[restore] backup file not found: $resolvedInput"
}

$dbUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "bookpoint" }
$dbName = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "bookpoint" }

Write-Host "[restore] restoring $resolvedInput into database $dbName"
$composeArgs = @("compose", "exec", "-T", "db", "psql", "-U", $dbUser, "-d", $dbName)
Get-Content -Raw -Path $resolvedInput | & docker @composeArgs
if ($LASTEXITCODE -ne 0) {
    throw "Restore failed."
}
Write-Host "[restore] restore completed"
