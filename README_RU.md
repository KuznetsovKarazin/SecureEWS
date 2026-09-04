# SecureEWS v0.6.1 — публичный релиз

Это очищенный aggregate-only пакет для GitHub Release и Zenodo, собранный из канонического C14G. Версия 0.6.1 добавляет финальные исходники и PDF, оформленные под **Education Sciences (MDPI)**, без изменения научных результатов C14.

## Что входит

- код, frozen protocol и unit tests;
- агрегированные C14B–C14E результаты и bootstrap draws;
- проверяемые C14F figures/tables и clean-room provenance без устаревшей working manuscript;
- финальные MDPI article/supplement sources и PDF в `paper/mdpi_submission/`;
- manifest, проверки, metadata для GitHub/Zenodo и пошаговые инструкции.

Публично исключены raw/processed student-level data, индивидуальные predictions, обученные модели, полный C13E/C14G clean-room, XuetangX C05 и legacy/DP-эксперименты.

## Проверка

```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 scripts\make_public_manifest.py
py -3.12 scripts\verify_public_release.py
py -3.12 scripts\build_release_zip.py
py -3.12 scripts\verify_release_zip.py
```

Все проверки должны вернуть `PASS`.

## Статья и supplement

- `paper/mdpi_submission/outputs/SecureEWS_MDPI_article_v3.pdf` — 19 страниц;
- `paper/mdpi_submission/outputs/SecureEWS_MDPI_supplement_v3.pdf` — 9 страниц;
- отдельные LaTeX source trees для загрузки в MDPI.

Использован профиль `education`, поэтому PDF корректно обозначен `Educ. Sci.`, а не `Journal Not Specified`. Все 28 страниц отрендерены и визуально проверены.

## Статус публикации

Технический пакет готов. 4 сентября 2026 года corresponding author подтвердил согласование с соавторами финальной рукописи, CRediT, funding AP23489228, ethics wording, conflicts, AI-use disclosure и лицензий. Репозиторий можно сделать публичным, поставить tag `v0.6.1`, архивировать в Zenodo и подавать в Education Sciences.

Краткая последовательность для текущей папки `E:\SecureEWS-v0.6.0` находится в `FINAL_PUBLISH_STEPS_RU.md`; расширенные команды GitHub/Zenodo — в `GITHUB_ZENODO_UPLOAD_RU.md`; checklist подачи — в `SUBMISSION_CHECKLIST_RU.md`.
