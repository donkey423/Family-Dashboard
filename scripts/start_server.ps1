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

$vaultPreflight = @'
import sys
from family_finance_hub.security.secrets import KeyringSecretStore, SecretStoreUnavailable
try:
    KeyringSecretStore().verify_access()
except SecretStoreUnavailable:
    print("Windows Credential Manager is unavailable in this logon session.")
    sys.exit(1)
'@
& ".venv/Scripts/python.exe" -c $vaultPreflight
if ($LASTEXITCODE -ne 0) {
    throw "Start FamilyHub from your interactive Windows account. On this host, use the FamilyFinanceHub scheduled task. The server was not started because secure storage is unavailable."
}

$env:FAMILY_FINANCE_HUB_DATABASE_URL = "sqlite:///./$($DatabasePath.Replace('\', '/'))"
& ".venv/Scripts/python.exe" -m uvicorn family_finance_hub.main:app --app-dir backend/src --host 127.0.0.1 --port 3000 --no-access-log
exit $LASTEXITCODE
