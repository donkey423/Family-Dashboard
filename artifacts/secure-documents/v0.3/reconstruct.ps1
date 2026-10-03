$ErrorActionPreference = "Stop"

$parts = @(
    "secure-documents-codex-skill-v0.3.zip.b64.part00",
    "secure-documents-codex-skill-v0.3.zip.b64.part01",
    "secure-documents-codex-skill-v0.3.zip.b64.part02",
    "secure-documents-codex-skill-v0.3.zip.b64.part03a",
    "secure-documents-codex-skill-v0.3.zip.b64.part03b",
    "secure-documents-codex-skill-v0.3.zip.b64.part04",
    "secure-documents-codex-skill-v0.3.zip.b64.part05"
)

$base64 = ""
foreach ($part in $parts) {
    $path = Join-Path $PSScriptRoot $part
    if (-not (Test-Path $path)) { throw "Missing artifact part: $part" }
    $base64 += (Get-Content -Raw -Path $path).Trim()
}

$bytes = [Convert]::FromBase64String($base64)
if ($bytes.Length -ne 21644) {
    throw "Decoded ZIP size mismatch: $($bytes.Length)"
}

$out = Join-Path $PSScriptRoot "secure-documents-codex-skill-v0.3.zip"
[IO.File]::WriteAllBytes($out, $bytes)

$actual = (Get-FileHash -Algorithm SHA256 -Path $out).Hash.ToLowerInvariant()
$expected = "2edd94420bd960438e412d858781d0144d8f23dd6e78820e9dacfbc2106bc0f1"
if ($actual -ne $expected) {
    Remove-Item -Force $out
    throw "SHA-256 mismatch. Reconstructed ZIP was removed."
}

Write-Host "Artifact reconstruction PASS"
Write-Host "ZIP: $out"
Write-Host "SHA-256: $actual"
