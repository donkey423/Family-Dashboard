param(
    [Parameter(Mandatory=$true)][string]$Pdf,
    [string]$IrOut,
    [string]$Rule,
    [string]$Config
)

$ErrorActionPreference = "Stop"
$argsList = @("-m", "secure_documents.cli", "extract", $Pdf)
if ($IrOut) { $argsList += @("--ir-out", $IrOut) }
if ($Rule) { $argsList += @("--rule", $Rule) }
if ($Config) { $argsList += @("--config", $Config) }
python @argsList
