# Загрузка SecureEWS v0.6.0 в GitHub и Zenodo

Команды ниже рассчитаны на Windows PowerShell. Используйте один и тот же `SecureEWS-v0.6.0.zip` и его SHA-256 для GitHub Release и ручного Zenodo deposit.

## 0. Что нельзя публиковать

Не загружайте полный 302-MB C14G, C13E, фазовые ZIP, raw/processed datasets, individual predictions, `.joblib`-модели или XuetangX C05. Они специально отсутствуют в публичном архиве.

Статья всё ещё содержит обязательные отметки `confirmation required`. До подтверждения author order/CRediT, funding, ethics, competing interests и финального согласия всех авторов GitHub держите private, Zenodo — draft.

## 1. Проверка архива

```powershell
Get-FileHash .\SecureEWS-v0.6.0.zip -Algorithm SHA256
Get-Content .\SecureEWS-v0.6.0.zip.sha256
Expand-Archive .\SecureEWS-v0.6.0.zip -DestinationPath .\SecureEWS-release
Set-Location .\SecureEWS-release\SecureEWS-v0.6.0
py -3.12 -m pip install -r requirements.txt
py -3.12 .\scripts\verify_public_release.py
py -3.12 .\scripts\build_release_zip.py
py -3.12 .\scripts\verify_release_zip.py
```

Оба verifier должны завершиться статусом `PASS`; SHA-256 в ZIP-verifier должен совпасть с `.zip.sha256`.

## 2. GitHub: сначала private repository

Установите Git и GitHub CLI, если их ещё нет:

```powershell
winget install --id Git.Git -e
winget install --id GitHub.cli -e
```

Закройте и снова откройте PowerShell, затем из каталога `SecureEWS-v0.6.0`:

```powershell
git init -b main
git config user.name "Oleksandr Kuznetsov"
git config user.email "YOUR_VERIFIED_GITHUB_EMAIL"
git add .
git status --short
git commit -m "Prepare SecureEWS v0.6.0 public release"

gh auth login --web --git-protocol https
gh repo create SecureEWS --private --source . --remote origin --push
gh repo view --web
```

Если репозиторий должен принадлежать организации, замените последнюю команду создания на:

```powershell
gh repo create OWNER_OR_ORGANIZATION/SecureEWS --private --source . --remote origin --push
```

Не используйте прежнюю фиктивную identity `release-prep@example.invalid`.

## 3. Финальная проверка перед публичностью

В GitHub проверьте отображение `README.md`, `CITATION.cff`, лицензий и PDF. Получите письменное согласование авторов и заполните в статье funding, ethics, CRediT и competing interests. После любых изменений пересоберите package:

```powershell
py -3.12 .\scripts\make_public_manifest.py
py -3.12 .\scripts\verify_public_release.py
py -3.12 .\scripts\build_release_zip.py
git add .
git commit -m "Finalize SecureEWS v0.6.0 metadata"
git push origin main
```

## 4. Сделать GitHub публичным, поставить tag и создать Release

В командах ниже `OWNER` замените на точный GitHub login или организацию:

```powershell
gh repo edit OWNER/SecureEWS --visibility public --accept-visibility-change-consequences
git tag -a v0.6.0 -m "SecureEWS v0.6.0"
git push origin v0.6.0

gh release create v0.6.0 `
  ..\SecureEWS-v0.6.0.zip `
  ..\SecureEWS-v0.6.0.zip.sha256 `
  --repo OWNER/SecureEWS `
  --title "SecureEWS v0.6.0" `
  --notes-file RELEASE_NOTES.md `
  --verify-tag
```

Проверьте:

```powershell
gh release view v0.6.0 --repo OWNER/SecureEWS --web
```

## 5. Zenodo: безопасный draft через API

Создайте токен в Zenodo Applications со scopes `deposit:write` и `deposit:actions`. Токен никому не отправляйте и не записывайте в файл.

```powershell
$SecureToken = Read-Host "Zenodo token" -AsSecureString
$env:ZENODO_TOKEN = [Net.NetworkCredential]::new("", $SecureToken).Password

.\scripts\create_zenodo_draft.ps1 `
  -ArchivePath "..\SecureEWS-v0.6.0.zip" `
  -ChecksumPath "..\SecureEWS-v0.6.0.zip.sha256" `
  -MetadataPath ".\zenodo_metadata.json"
```

Сценарий создаёт draft, загружает ZIP и SHA-256, записывает локальный `zenodo_draft_receipt.json` и выводит reserved DOI. Он **не публикует** запись.

Откройте draft URL и вручную проверьте:

1. порядок и написание всех авторов;
2. title, version `0.6.0`, publication date и keywords;
3. GitHub Release URL в Related works;
4. обе лицензии: MIT для кода и CC BY 4.0 для остальных материалов;
5. funding — только после официального подтверждения;
6. состав файлов и совпадение SHA-256.

Для теста можно использовать отдельный sandbox-token и ключ `-Sandbox`. Sandbox может очищаться и выдаёт тестовые DOI.

## 6. Публикация Zenodo — только после всех согласований

Подставьте deposition ID из `zenodo_draft_receipt.json`:

```powershell
.\scripts\publish_zenodo_draft.ps1 `
  -DepositionId 12345678 `
  -IConfirmAuthorFundingEthicsAndConflictsApproval
```

После публикации добавьте DOI в `CITATION.cff` и README, создайте отдельный metadata-only commit и не меняйте уже опубликованный ZIP. Для исправления научного payload создавайте новую версию Zenodo и новый Git tag, а не заменяйте историю `v0.6.0`.

## Альтернатива: Zenodo–GitHub integration

Можно связать GitHub в профиле Zenodo, нажать `Sync now` и включить репозиторий до выпуска GitHub Release. Тогда новый GitHub release будет автоматически архивирован. Не используйте одновременно integration и ручной API deposit: это создаст два Zenodo records/DOI для одного релиза.
