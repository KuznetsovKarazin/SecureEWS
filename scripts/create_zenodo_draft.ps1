param(
    [string]$ArchivePath = "..\SecureEWS-v0.6.1.zip",
    [string]$ChecksumPath = "..\SecureEWS-v0.6.1.zip.sha256",
    [string]$MetadataPath = ".\zenodo_metadata.json",
    [switch]$Sandbox
)

$ErrorActionPreference = "Stop"
if (-not $env:ZENODO_TOKEN) { throw "Set ZENODO_TOKEN in this PowerShell session first." }

$Base = if ($Sandbox) { "https://sandbox.zenodo.org" } else { "https://zenodo.org" }
$Headers = @{ Authorization = "Bearer $env:ZENODO_TOKEN" }
$Archive = (Resolve-Path $ArchivePath).Path
$Checksum = (Resolve-Path $ChecksumPath).Path
$Metadata = (Resolve-Path $MetadataPath).Path

$Draft = Invoke-RestMethod -Method Post -Uri "$Base/api/deposit/depositions" -Headers $Headers -ContentType "application/json" -Body "{}"
$Bucket = $Draft.links.bucket

foreach ($File in @($Archive, $Checksum)) {
    $Name = [System.IO.Path]::GetFileName($File)
    Invoke-RestMethod -Method Put -Uri "$Bucket/$Name" -Headers $Headers -InFile $File -ContentType "application/octet-stream" | Out-Null
}

$Body = Get-Content $Metadata -Raw
$Updated = Invoke-RestMethod -Method Put -Uri "$Base/api/deposit/depositions/$($Draft.id)" -Headers $Headers -ContentType "application/json" -Body $Body

$Receipt = [ordered]@{
    environment = if ($Sandbox) { "sandbox" } else { "production" }
    deposition_id = $Updated.id
    reserved_doi = $Updated.metadata.prereserve_doi.doi
    draft_url = $Updated.links.html
    published = $false
}
$Receipt | ConvertTo-Json | Set-Content -Encoding UTF8 "zenodo_draft_receipt.json"
$Receipt | Format-List
Write-Host "DRAFT CREATED. Inspect it in the browser. This script did not publish the record."
