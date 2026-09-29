param(
    [string]$DatabasePath = "data/family-finance-hub.db"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath ".venv/Scripts/python.exe")) {
    throw "Python virtual environment is missing. See README.md."
}
if (-not (Test-Path -LiteralPath "frontend/dist/index.html")) {
    throw "Built frontend is missing. Run npm --prefix frontend run build."
}
if (-not (Test-Path -LiteralPath $DatabasePath)) {
    throw "Database is missing: $DatabasePath"
}

$env:FAMILY_FINANCE_HUB_DATABASE_URL = "sqlite:///./$($DatabasePath.Replace('\', '/'))"
& ".venv/Scripts/python.exe" -m uvicorn family_finance_hub.main:app --app-dir backend/src --host 127.0.0.1 --port 3000 --no-access-log
exit $LASTEXITCODE
