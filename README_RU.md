# SecureEWS v0.6.0 — публичный релиз

Это очищенный пакет для GitHub Release и Zenodo. Он построен из канонического C14G и содержит код, протокол, агрегированные результаты, bootstrap draws, статью, supplement и проверки.

Публично исключены:

- сырые и обработанные row-level образовательные данные;
- индивидуальные predictions;
- обученные `.joblib`-модели;
- полный C13E/C14G clean-room и фазовые ZIP;
- XuetangX C05;
- legacy/DP-эксперименты.

Проверка:

```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 scripts\verify_public_release.py
```

Пошаговая публикация приведена в `GITHUB_ZENODO_UPLOAD_RU.md`. До подтверждения всеми авторами author order/CRediT, funding, ethics и competing interests GitHub следует держать private, а Zenodo — в состоянии draft.
