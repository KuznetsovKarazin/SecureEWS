# SecureEWS C14A — зафиксированный протокол

Версия: 1.0.0. Дата фиксации: 2026-09-02 (UTC). Статус: `FROZEN_BEFORE_C14B_C14C_C14D_RESULTS`.

## 1. Исходная точка и границы

C14 является продолжением проверенного C13E, а не новым исследованием. Уже известны результаты C12 OULAD и C13 UCI, поэтому C14 остаётся post-development исследованием и не обозначается как preregistered confirmation. До фиксации данного документа не вычислялись многобюджетные таблицы C14B, proxy-persistence показатели C14C и новые harmonized block-exclusion модели C14D.

Канонический XuetangX C05/v0.3.1 сохраняется физически внутри C12E и не переобучается. Он не включается в демографические выводы, поскольку официальная KDD Cup 2015 схема не содержит необходимых полей, а происхождение ранее использованной производной нельзя независимо подтвердить.

## 2. Исследовательские вопросы

1. Сохраняется ли знак и практический масштаб restricted-minus-full различий при бюджетах проверки 5%, 10%, 20% и 30%?
2. Остаются ли исключённые поля `gender/sex` и `disability/special needs` предсказуемыми по разрешённым данным после прямого удаления этих полей?
3. Согласуются ли результаты для двух заранее определённых межнаборных блоков — `sex_gender` и `socioeconomic_family` — при сопоставимых стадиях и только с same-run full controls?
4. Какие выводы выдерживают заранее определённую family-wise поправку по бюджетам и стадиям?

## 3. C14B — чувствительность к бюджету без переобучения

Используются только сохранённые вероятности C12/C13. Модели, калибраторы, признаки и split assignments не изменяются.

- Бюджеты: 0.05, 0.10, 0.20 и 0.30.
- Число предупреждений: `ceil(budget * n_group)` отдельно внутри исходной operational group.
- OULAD: группа `code_module`, порядок — убывание сохранённой калиброванной вероятности и затем сохранённый `tie_key_sha256`.
- UCI 697: группа `Course`; UCI 320: группа `school`; tie-break в точности наследуется из C13 (`SecureEWS-C13A`, dataset, row_id, исходный seed).
- Основные показатели очереди: alerts, true alerts, false alerts, precision, recall, lift, restricted/full alert-set Jaccard и доля retained full alerts.
- Вероятностные AP, AUROC и Brier не зависят от бюджета и не дублируются как четыре разных результата.

Основные OULAD-контрасты: minimized-minus-full и partial-gender-disability-minus-full на шести горизонтах. Strict day-42 и leave-one-field-out сохраняются как отдельные sensitivity families. Основные UCI-контрасты используют HGB; logistic и UCI 697 LOO являются sensitivity results.

## 4. C14C — proxy-persistence audit

Proxy audit отвечает только на вопрос, можно ли предсказывать непосредственно исключённое поле по оставшимся разрешённым признакам в held-out данных. Он не доказывает, что EWS фактически использует конкретный proxy, не измеряет справедливость, не устанавливает причинность и не является privacy attack.

Целевые поля:

- OULAD: `gender`, `disability`;
- UCI 697: `Gender`, `Educational special needs`;
- UCI 320: `sex`.

Для каждого целевого поля оно удаляется из predictors. Также исключаются outcome, row/student identifiers, split fields и любые будущие признаки. Predictor view совпадает с полями соответствующей targeted-exclusion политики на каждой стадии.

- OULAD: фиксированные probe-модели обучаются на 2013B/2013J; 2014B используется только для выбора decision threshold для balanced accuracy; окончательная оценка выполняется на 2014J без использования его меток при обучении или выборе порога. Дополнительно отдельно оцениваются студенты 2014J, отсутствовавшие в обучающих презентациях.
- UCI: 10 сохранённых outer folds C13; preprocessing строго внутри train fold.
- Primary probe: фиксированная logistic regression (`C=1`, `max_iter=2000`, без подбора).
- Nonlinear sensitivity: фиксированный HGB (`max_leaf_nodes=15`, остальные параметры как C13, без grid selection).
- Метрики: AUROC, average precision, balanced accuracy, Brier и prevalence baseline; для редких бинарных полей всегда публикуются prevalence и число положительных случаев.

Не допускается отбор стадий, targets или probe family после результатов. Нулевые, отрицательные и нестабильные показатели сохраняются.

## 5. C14D — минимально необходимые harmonized block-exclusion модели

Новые outcome-модели обучаются только там, где в C12/C13 отсутствует точный заранее заданный блок. Primary family — HGB; новые logistic-модели не строятся.

### Блок H1: `sex_gender`

- OULAD: `gender`;
- UCI 697: `Gender`;
- UCI 320: `sex`.

Повторно используются существующие same-run пары OULAD day 14/day 42, UCI 697 и UCI 320. Для OULAD day 28/56/70/90 строятся только missing no-gender модели и новые full controls в том же запуске.

### Блок H2: `socioeconomic_family`

- OULAD: `highest_education`, `imd_band`;
- UCI 697: parental qualification/occupation, debtor, tuition-fee status и scholarship-holder — существующая policy `no_family_financial`;
- UCI 320: `Medu`, `Fedu`, `Mjob`, `Fjob`.

Для OULAD на шести горизонтах и UCI 320 на двух subjects × трёх стадиях строятся restricted модели и full controls в одном запуске. Для UCI 697 используются существующие same-run C13 HGB pairs. Название блока обозначает operational harmonization, а не идентичность измеряемых конструктов.

Каждый новый full control обязан воспроизвести соответствующую сохранённую full prediction с максимальным абсолютным расхождением не более `1e-12`; иначе вся соответствующая новая пара отклоняется. Сравнение с full из другого запуска запрещено.

## 6. C14E — парная неопределённость и множественность

- OULAD: paired cluster bootstrap по `id_student` с общими multiplicities для full/restricted и всех четырёх бюджетов; 5000 повторов для primary HGB families.
- UCI: paired row bootstrap с общими multiplicities; 5000 повторов для primary HGB families.
- Sensitivity families: 2000 повторов.
- Интервалы: pointwise 95% paired percentile и family-wise Bonferroni-percentile.
- Семья множественности фиксируется отдельно для каждого dataset × subject/outcome × named policy/block × metric и включает все заранее определённые стадии × четыре бюджета. Для OULAD это 24 клетки, UCI 697 — 8, UCI 320 — 12 на subject.
- Для probability metrics семья включает только стадии, поскольку бюджет на них не влияет.
- Cross-dataset sign summaries и forest plots являются описательными; pooled meta-effect не вычисляется из семантически неодинаковых наборов.

Primary workload estimand — `precision_restricted - precision_full`. Recall, overlap, AP, AUROC, Brier и proxy metrics являются заранее указанными secondary estimands. Отсутствие статистически различимого эффекта не интерпретируется как эквивалентность.

## 7. Правила отчётности

1. Все отрицательные, нулевые и противоречивые результаты публикуются.
2. Ни один бюджет или блок не удаляется после просмотра результатов.
3. OULAD, UCI 697 и UCI 320 остаются отдельно идентифицированными; различия дизайна не маскируются термином replication.
4. Proxy predictability не называется доказательством фактического proxy use.
5. Harmonized block не называется единым латентным социально-экономическим конструктом.
6. Результаты не являются formal non-inferiority, fairness certification, privacy guarantee или доказательством причинного улучшения педагогической деятельности.
7. Статья связывает результаты с governance teacher-facing decision support и необходимостью prospective implementation study без экспертных опросов в текущем C14.
