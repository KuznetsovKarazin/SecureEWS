# Обновление SecureEWS v0.6.1 в GitHub и Zenodo

Команды рассчитаны на Windows PowerShell. Публикуется только `SecureEWS-v0.6.1.zip`; private C14G, datasets, row-level predictions, models и XuetangX загружать нельзя.

## 0. Переменные

Расположите `SecureEWS-v0.6.1.zip` и `SecureEWS-v0.6.1.zip.sha256` в одной папке, затем задайте:

```powershell
$Owner = "KuznetsovKarazin"
$Repo = "SecureEWS"
$PackageDir = (Resolve-Path ".").Path
```

## 1. Проверить и распаковать релиз

```powershell
Get-FileHash "$PackageDir\SecureEWS-v0.6.1.zip" -Algorithm SHA256
Get-Content "$PackageDir\SecureEWS-v0.6.1.zip.sha256"

Expand-Archive `
  "$PackageDir\SecureEWS-v0.6.1.zip" `
  -DestinationPath "$PackageDir\unpacked" `
  -Force

$ReleaseRoot = "$PackageDir\unpacked\SecureEWS-v0.6.1"
Set-Location $ReleaseRoot
py -3.12 -m pip install -r requirements.txt
py -3.12 .\scripts\verify_public_release.py
py -3.12 .\scripts\verify_release_zip.py `
  --archive "$PackageDir\SecureEWS-v0.6.1.zip" `
  --checksum "$PackageDir\SecureEWS-v0.6.1.zip.sha256"
```

Обе проверки должны вернуть `PASS`, а два SHA-256 должны совпасть.

## 2A. Обновить существующий GitHub repository

Работайте в новом clone: это исключает смешивание релиза с локальными незакоммиченными файлами.

```powershell
Set-Location $PackageDir
git clone "https://github.com/$Owner/$Repo.git" SecureEWS-publish
Set-Location .\SecureEWS-publish
git switch main

if (git status --porcelain) {
  throw "Clone is not clean; stop and inspect git status."
}

git branch "backup/pre-v0.6.1"
git rm -r --ignore-unmatch -- .
Get-ChildItem -Force $ReleaseRoot | Copy-Item -Destination . -Recurse -Force

git add -A
git status --short
git diff --cached --stat
git diff --cached --check
git commit -m "Release SecureEWS v0.6.1 and finalize MDPI submission package"
git push origin main
```

`git rm` здесь выполняется только в свежем чистом clone; резервная ветка сохраняет прежнее состояние. Перед `commit` обязательно просмотрите `git status` и `git diff --cached --stat`.

## 2B. Если repository ещё не существует

```powershell
Set-Location $ReleaseRoot
git init -b main
git config user.name "Oleksandr Kuznetsov"
git config user.email "YOUR_VERIFIED_GITHUB_EMAIL"
git add -A
git diff --cached --check
git commit -m "Release SecureEWS v0.6.1 and finalize MDPI submission package"

gh auth login --web --git-protocol https
gh repo create "$Owner/$Repo" --private --source . --remote origin --push
```

Не подставляйте фиктивный email. Используйте email, подтверждённый в GitHub, или GitHub noreply address.

## 3. Финальная проверка перед публичностью

All-author sign-off подтверждён 4 сентября 2026 года. Выполните финальную техническую проверку:

```powershell
Set-Location "$PackageDir\SecureEWS-publish"
py -3.12 .\scripts\make_public_manifest.py
py -3.12 .\scripts\verify_public_release.py
git status --short
```

После публикации manifest не должен неожиданно меняться. Если verifier изменил `PUBLIC_RELEASE_VERIFICATION.json`, зафиксируйте только ожидаемое обновление:

```powershell
git add MANIFEST.csv MANIFEST.json PUBLIC_RELEASE_VERIFICATION.json
git commit -m "Refresh v0.6.1 verification receipts"
git push origin main
```

После статуса `PASS` сделайте repository публичным:

```powershell
gh repo edit "$Owner/$Repo" `
  --visibility public `
  --accept-visibility-change-consequences
```

## 4. Tag и GitHub Release

```powershell
git tag -a v0.6.1 -m "SecureEWS v0.6.1"
git push origin v0.6.1

gh release create v0.6.1 `
  "$PackageDir\SecureEWS-v0.6.1.zip" `
  "$PackageDir\SecureEWS-v0.6.1.zip.sha256" `
  --repo "$Owner/$Repo" `
  --title "SecureEWS v0.6.1" `
  --notes-file RELEASE_NOTES.md `
  --verify-tag

gh release view v0.6.1 --repo "$Owner/$Repo" --web
```

GitHub Release должен содержать оба assets. Не перетагируйте `v0.6.1` после публикации; исправления payload выпускайте новой версией.

## 5. Zenodo: создать draft через API

Выберите только один маршрут: ручной API **или** Zenodo–GitHub integration. Не используйте оба для одного релиза, иначе появятся два DOI.

Для ручного API создайте Zenodo token со scopes `deposit:write` и `deposit:actions`. Не вставляйте токен в командную историю или файл:

```powershell
$SecureToken = Read-Host "Zenodo token" -AsSecureString
$env:ZENODO_TOKEN = [Net.NetworkCredential]::new("", $SecureToken).Password

Set-Location "$PackageDir\SecureEWS-publish"
.\scripts\create_zenodo_draft.ps1 `
  -ArchivePath "$PackageDir\SecureEWS-v0.6.1.zip" `
  -ChecksumPath "$PackageDir\SecureEWS-v0.6.1.zip.sha256" `
  -MetadataPath ".\zenodo_metadata.json"
```

Скрипт создаёт draft, загружает оба файла и сохраняет `zenodo_draft_receipt.json`; он ничего не публикует.

В draft вручную проверьте:

1. авторов, порядок, affiliations и ORCID;
2. title, version `0.6.1`, дату и keywords;
3. Related work: `https://github.com/KuznetsovKarazin/SecureEWS/releases/tag/v0.6.1`;
4. MIT как основную software license и примечание о CC BY 4.0 для documentation/results/manuscript materials;
5. funding `AP23489228`;
6. точный состав files и SHA-256.

Для пробного запуска используйте отдельный sandbox-token и параметр `-Sandbox`. Sandbox выдаёт тестовый DOI и может очищаться.

## 6. Опубликовать Zenodo — необратимый шаг

После ручной проверки Zenodo draft:

```powershell
$Receipt = Get-Content .\zenodo_draft_receipt.json -Raw | ConvertFrom-Json
.\scripts\publish_zenodo_draft.ps1 `
  -DepositionId $Receipt.deposition_id `
  -IConfirmAuthorFundingEthicsAndConflictsApproval
```

После публикации сохраните DOI. Добавьте его в `CITATION.cff` и README отдельным metadata-only commit на `main`; tagged payload и уже опубликованный Zenodo archive не заменяйте.

## 7. Альтернатива: Zenodo–GitHub integration

До создания GitHub Release подключите GitHub в Zenodo, выполните `Sync now` и включите repository. После публикации GitHub Release Zenodo автоматически создаст запись. В этом случае не запускайте `create_zenodo_draft.ps1`.
