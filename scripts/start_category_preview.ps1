param([string]$MobileHostname = "")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$logRoot = Join-Path $root "data/category-preview"
foreach ($port in @(3001, 8030)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        throw "Preview port $port is occupied. No existing service was stopped."
    }
}
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$python = Join-Path $root ".venv/Scripts/python.exe"
$node = (Get-Command node -ErrorAction Stop).Source
$backend = Start-Process -FilePath $python -ArgumentList "scripts/category_preview.py" -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot "backend.stdout.log") -RedirectStandardError (Join-Path $logRoot "backend.stderr.log")
$env:FAMILY_FINANCE_HUB_API_URL = "http://127.0.0.1:8030"
$env:FAMILY_FINANCE_HUB_PREVIEW_HOST = $MobileHostname
$frontend = Start-Process -FilePath $node -ArgumentList "node_modules/vite/bin/vite.js --host 127.0.0.1 --port 3001 --strictPort" -WorkingDirectory (Join-Path $root "frontend") -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot "frontend.stdout.log") -RedirectStandardError (Join-Path $logRoot "frontend.stderr.log")
[pscustomobject]@{ BackendPid = $backend.Id; FrontendPid = $frontend.Id; LocalUrl = "http://127.0.0.1:3001/?month=2026-09"; Database = "data/category-preview/synthetic.db" } | Format-List
