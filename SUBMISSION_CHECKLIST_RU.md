# Финальный checklist подачи в Education Sciences (MDPI)

Целевая Special Issue: **Advancing AI Education: Virtual Learning, Technology Integration, and Instructional Design**. Заявленный срок приёма: **30 сентября 2026 года**.

## 1. Подтверждения авторов — выполнено 4 сентября 2026 года

- [x] Все шесть авторов утвердили порядок и написание имён.
- [x] Авторы подтвердили affiliations и данные двух corresponding authors.
- [x] Подтверждены `oleksandr.kuznetsov@uniecampus.it` / ORCID `0000-0003-2331-6326` и `gshangytbayeva@zhubanov.edu.kz` / ORCID `0000-0003-4615-5756`.
- [x] Согласован CRediT statement в формулировке статьи.
- [x] Подтверждены funder и grant `AP23489228`, включая отсутствие роли funder в дизайне, анализе и решении публиковать.
- [x] Согласованы формулировки ethics и informed consent (`Not applicable`).
- [x] Подтверждена декларация об отсутствии conflicts of interest.
- [x] Согласован AI-use disclosure и ответственность авторов за текст, код и результаты.
- [x] Согласованы MIT для кода и CC BY 4.0 для документации, manuscript materials и aggregate results.

## 2. GitHub/Zenodo — до нажатия Submit

- [ ] Публичный GitHub repository существует по адресу `https://github.com/KuznetsovKarazin/SecureEWS`.
- [ ] В repository загружен только aggregate-only релиз; C14G, raw/processed data, individual predictions, trained models и XuetangX отсутствуют.
- [ ] `python scripts/verify_public_release.py` и `python scripts/verify_release_zip.py` вернули `PASS`.
- [ ] Создан GitHub Release `v0.6.1` с ZIP и `.sha256`.
- [ ] Zenodo draft содержит тот же ZIP и `.sha256`; авторы, version, date, licenses и related GitHub URL проверены вручную.
- [ ] Если Zenodo DOI публикуется до подачи, DOI внесён в metadata формы MDPI. Tagged payload не изменяется после публикации DOI.

Если GitHub ещё не публичен к моменту подачи, нельзя оставлять в статье утверждение, что release “is available”. В таком случае сначала опубликуйте repository либо измените Data Availability Statement до фактического состояния.

## 3. Файлы для MDPI

- [ ] Main source: `SecureEWS_MDPI_article_SOURCE_v3.zip`.
- [ ] Main PDF: `SecureEWS_MDPI_article_v3.pdf`.
- [ ] Supplementary Materials PDF: `SecureEWS_MDPI_supplement_v3.pdf`.
- [ ] Supplement source: `SecureEWS_MDPI_supplement_SOURCE_v3.zip`, если SuSy предлагает отдельное поле source/LaTeX supplementary file.
- [ ] Cover letter: `COVER_LETTER_MDPI.txt`, после проверки имени handling editor и всех авторских утверждений.

Не загружайте общий public-release ZIP как manuscript source и не загружайте private C14G clean-room в MDPI.

## 4. Поля в SuSy

- [ ] Journal: `Education Sciences`; article type: `Article`.
- [ ] Выбрана нужная Special Issue, а не regular issue.
- [ ] Title, abstract и keywords скопированы из финального `.tex` без сокращений.
- [ ] Все авторы, emails, affiliations и ORCID внесены в том же порядке, что в PDF.
- [ ] Funding agency и grant number внесены в structured fields.
- [ ] Data Availability, Institutional Review Board, Informed Consent, Conflicts of Interest и AI-use disclosure совпадают с рукописью.
- [ ] Supplement обозначен как Supplementary Materials, а не как дополнительный main manuscript.
- [ ] Suggested/opposed reviewers заполнены только при наличии обоснованных и независимых кандидатов без conflict of interest.

## 5. Последняя проверка

- [ ] PDF в preview SuSy показывает `Submitted to Educ. Sci.`, а не `Journal Not Specified`.
- [ ] В preview 19 страниц статьи и 9 страниц supplement; таблицы и рисунки не обрезаны.
- [ ] Ссылки, DOI, номера таблиц/рисунков и supplement citations корректно отображаются.
- [ ] MDPI-generated merged PDF скачан и просмотрен полностью перед подтверждением.
- [ ] Все авторы получили final submitted PDF и manuscript ID после подачи.

Техническая проверка существенно снижает риск возврата на форматирование, но не может гарантировать отсутствие научных или production queries со стороны редакции.
