param(
    [string]$MobileHostname = "",
    [ValidateRange(3001, 65535)][int]$FrontendPort = 3001,
    [ValidateRange(8030, 65535)][int]$BackendPort = 8030,
    [ValidatePattern('^category-preview[-a-zA-Z0-9_]*$')][string]$DataName = "category-preview"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$logRoot = Join-Path $root "data/$DataName"
if ($FrontendPort -eq $BackendPort) { throw "Frontend and backend ports must differ." }
$listeners = Get-NetTCPConnection -State Listen -ErrorAction Stop
foreach ($port in @($FrontendPort, $BackendPort)) {
    if ($listeners | Where-Object LocalPort -eq $port) {
        throw "Preview port $port is occupied. No existing service was stopped."
    }
}
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$python = Join-Path $root ".venv/Scripts/python.exe"
$node = (Get-Command node -ErrorAction Stop).Source
$backend = Start-Process -FilePath $python -ArgumentList "scripts/category_preview.py --data-directory data/$DataName --port $BackendPort" -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot "backend.stdout.log") -RedirectStandardError (Join-Path $logRoot "backend.stderr.log")
$env:FAMILY_FINANCE_HUB_API_URL = "http://127.0.0.1:$BackendPort"
$env:FAMILY_FINANCE_HUB_PREVIEW_HOST = $MobileHostname
$frontend = Start-Process -FilePath $node -ArgumentList "node_modules/vite/bin/vite.js --host 127.0.0.1 --port $FrontendPort --strictPort" -WorkingDirectory (Join-Path $root "frontend") -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot "frontend.stdout.log") -RedirectStandardError (Join-Path $logRoot "frontend.stderr.log")
[pscustomobject]@{ BackendPid = $backend.Id; FrontendPid = $frontend.Id; LocalUrl = "http://127.0.0.1:$FrontendPort/?month=2026-09"; Database = "data/$DataName/synthetic.db" } | Format-List
