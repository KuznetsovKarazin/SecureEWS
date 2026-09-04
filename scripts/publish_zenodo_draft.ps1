param(
    [Parameter(Mandatory = $true)][long]$DepositionId,
    [switch]$IConfirmAuthorFundingEthicsAndConflictsApproval,
    [switch]$Sandbox
)

$ErrorActionPreference = "Stop"
if (-not $IConfirmAuthorFundingEthicsAndConflictsApproval) {
    throw "Publication blocked: pass -IConfirmAuthorFundingEthicsAndConflictsApproval only after every listed confirmation is complete."
}
if (-not $env:ZENODO_TOKEN) { throw "Set ZENODO_TOKEN in this PowerShell session first." }

$Base = if ($Sandbox) { "https://sandbox.zenodo.org" } else { "https://zenodo.org" }
$Headers = @{ Authorization = "Bearer $env:ZENODO_TOKEN" }
$Published = Invoke-RestMethod -Method Post -Uri "$Base/api/deposit/depositions/$DepositionId/actions/publish" -Headers $Headers
$Published | ConvertTo-Json -Depth 8
