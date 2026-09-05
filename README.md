# SecureEWS v0.7.3

SecureEWS evaluates educational early-warning systems as tools for educator decision support. Its central question is practical: can an institution collect and use less student-background information while preserving the usefulness of the review lists that teachers, advisers, or support teams can realistically act on?

This aggregate-only public release accompanies the manuscript **“Evaluating Data-Minimized Early-Warning Systems for Educator Decision Support: Evidence Across Review Capacities and Educational Stages.”** Version 0.7.2 incorporates the authors' final revised conceptual diagrams without changing the frozen analyses, numerical results, or provenance record.

## Why review capacity matters

A risk score does not support a student by itself. An educator or support team must interpret the alert, understand the student's circumstances, and decide whether and how to respond. SecureEWS therefore evaluates models at four review capacities—5%, 10%, 20%, and 30% of a cohort—and at several points in the educational process.

In the manuscript, *precision at a given capacity* means the proportion of students in the review list who later experience the defined adverse outcome. *Recall at that capacity* means the proportion of all later adverse outcomes represented in the list. These measures describe prioritization under limited staff capacity; they do not measure the causal effect of an intervention.

## Main findings

- Targeted removal of sex/gender information produced no family-wise difference in review-list yield in the three datasets under the evaluated conditions.
- Removing socioeconomic and family-related information reduced overall predictive performance throughout OULAD and UCI 697 and weakened selected review lists.
- The practical effect changed with educational stage and the number of students that staff could review.
- Results from the smaller UCI 320 samples were inconclusive for data-removal effects.
- Excluded attributes remained partly predictable from other retained records. Direct deletion is therefore one governance measure, not evidence that all related information has disappeared.
- Clickstream-free fallback models improved when assessment-process information was added, but they remained less useful than the standard comparator at the evaluated operating point.

The analyses do not establish equivalence, fairness, privacy, causal educational benefit, or actual proxy use by the outcome models. Prospective evaluation with educators and students remains necessary.

## Repository structure

| Path | Contents |
| --- | --- |
| `protocol/` | Frozen final-stage protocol, analysis plan, input anchors, and comparable information groups |
| `src/` | Analysis, verification, table, and figure code |
| `tests/` | Deterministic unit tests |
| `results/` | Aggregate capacity, residual-predictability, comparable-group, and paired-statistical results |
| `paper/mdpi_submission/` | Education Sciences/MDPI article and Supplementary Materials sources, PDFs, logs, and QA record |
| `paper/figures/`, `paper/tables/` | Reproducible data figures, conceptual synthesis diagrams, and manuscript tables |
| `provenance/` | Canonical phase registry and private-clean-room verification receipt; no restricted payload |
| `scripts/` | Release, submission-package, GitHub, and Zenodo verification tools |

Internal phase identifiers are retained in paths and machine-readable files for traceability. The article itself uses educational and institutional language, with a practical interpretation guide in Appendix A.

## Verification

Python 3.12 is recommended. Poppler is required for PDF verification.

```bash
python -m pip install -r requirements.txt
python scripts/make_public_manifest.py
python scripts/verify_public_release.py
python scripts/build_release_zip.py
python scripts/verify_release_zip.py
```

Every verifier must report `PASS`. The checks cover the public manifest, restricted-artifact exclusions, numerical replay from aggregate artifacts, figure provenance, author and funding metadata, PDF identity, LaTeX diagnostics, and the final article/Supplementary Materials package.

## Manuscript files

Submission-ready files are in `paper/mdpi_submission/`:

- `outputs/SecureEWS_MDPI_article_v6.pdf` — main article;
- `outputs/SecureEWS_MDPI_supplement_v6.pdf` — Supplementary Materials;
- `article_source/article_mdpi.tex` — `education,article,submit` profile;
- `supplement_source/supplement_mdpi.tex` — `education,supfile,submit` profile.

Both PDFs were compiled from the included sources and visually inspected on every page. See `paper/mdpi_submission/README.md` and `MDPI_SUBMISSION_QA.json`.

## Reproduction and redistribution boundary

The public release reproduces the reported paired intervals from supplied aggregate artifacts and hashed bootstrap draws and regenerates manuscript tables and figures from locked aggregate results. It deliberately excludes raw or processed student-level data, individual predictions, trained model bundles, private clean-room archives, and XuetangX-derived files. See [DATA_AVAILABILITY.md](DATA_AVAILABILITY.md).

## License and citation

Source code is licensed under the MIT License. Documentation, manuscript materials, figures, tables, and aggregate result files are licensed under CC BY 4.0. Third-party datasets are not redistributed. See [LICENSES.md](LICENSES.md), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and `CITATION.cff`.

After Zenodo publication, add the version DOI to `CITATION.cff` and this README in a metadata-only follow-up commit. Do not alter the tagged `v0.7.2` archive.
