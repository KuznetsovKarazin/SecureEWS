# Финальная публикация SecureEWS v0.6.1

## 1. Распаковать новый релиз отдельно

Сохраните `SecureEWS-v0.6.1.zip` и `.sha256` в `E:\SecureEWS_release`, затем:

```powershell
New-Item -ItemType Directory -Force E:\SecureEWS_release | Out-Null
Set-Location E:\SecureEWS_release
Get-FileHash .\SecureEWS-v0.6.1.zip -Algorithm SHA256
Get-Content .\SecureEWS-v0.6.1.zip.sha256
Expand-Archive .\SecureEWS-v0.6.1.zip -DestinationPath . -Force
$ReleaseRoot = "E:\SecureEWS_release\SecureEWS-v0.6.1"
```

Ожидаемый SHA-256 указан в приложенном `.sha256`; обе строки должны совпасть.

## 2. Обновить существующий private repository

```powershell
Set-Location E:\SecureEWS-v0.6.0
git fetch origin
git switch main
git pull --ff-only origin main

if (git status --porcelain) {
  throw "Есть локальные изменения. Сначала сохраните их и повторите."
}

git branch backup/pre-v0.6.1
git rm -r --ignore-unmatch -- .
Get-ChildItem -Force $ReleaseRoot | Copy-Item -Destination . -Recurse -Force

py -3.12 -m pip install -r requirements.txt
py -3.12 .\scripts\make_public_manifest.py
py -3.12 .\scripts\verify_public_release.py

git add -A
git diff --cached --check
git status --short
git commit -m "Release SecureEWS v0.6.1 and finalize MDPI submission"
git push origin main
```

Verifier должен вернуть `PASS`. Папку `E:\SecureEWS-v0.6.0` переименовывать не обязательно: имя локальной папки не влияет на repository или tag.

## 3. Сделать GitHub публичным и выпустить release

```powershell
gh auth login --web --git-protocol https
gh repo edit KuznetsovKarazin/SecureEWS --visibility public --accept-visibility-change-consequences

git tag -a v0.6.1 -m "SecureEWS v0.6.1"
git push origin v0.6.1

gh release create v0.6.1 `
  E:\SecureEWS_release\SecureEWS-v0.6.1.zip `
  E:\SecureEWS_release\SecureEWS-v0.6.1.zip.sha256 `
  --repo KuznetsovKarazin/SecureEWS `
  --title "SecureEWS v0.6.1" `
  --notes-file RELEASE_NOTES.md `
  --verify-tag
```

## 4. Zenodo

```powershell
$SecureToken = Read-Host "Zenodo token" -AsSecureString
$env:ZENODO_TOKEN = [Net.NetworkCredential]::new("", $SecureToken).Password

.\scripts\create_zenodo_draft.ps1 `
  -ArchivePath E:\SecureEWS_release\SecureEWS-v0.6.1.zip `
  -ChecksumPath E:\SecureEWS_release\SecureEWS-v0.6.1.zip.sha256 `
  -MetadataPath .\zenodo_metadata.json
```

Проверьте draft в браузере и только затем опубликуйте:

```powershell
$Receipt = Get-Content .\zenodo_draft_receipt.json -Raw | ConvertFrom-Json
.\scripts\publish_zenodo_draft.ps1 `
  -DepositionId $Receipt.deposition_id `
  -IConfirmAuthorFundingEthicsAndConflictsApproval
```

Не включайте одновременно Zenodo–GitHub integration и ручной API deposit.

## 5. MDPI

Распакуйте `SecureEWS_MDPI_SUBMISSION_PACKAGE_v3.zip` отдельно. В SuSy загрузите:

1. `SecureEWS_MDPI_article_SOURCE_v3.zip` — main LaTeX source;
2. `SecureEWS_MDPI_article_v3.pdf` — main manuscript PDF;
3. `SecureEWS_MDPI_supplement_v3.pdf` — Supplementary Materials;
4. `SecureEWS_MDPI_supplement_SOURCE_v3.zip` — supplementary source, если система запросит;
5. `COVER_LETTER_MDPI.txt` — cover letter.

Сам общий `SecureEWS_MDPI_SUBMISSION_PACKAGE_v3.zip` в поле manuscript не загружайте.
