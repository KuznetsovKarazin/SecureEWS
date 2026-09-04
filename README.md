# SecureEWS v0.6.1

SecureEWS is an auditable, post-development stress test of data-minimization claims in educational early-warning systems. It evaluates whether conclusions change across review budgets, prediction stages, excluded feature blocks, and metrics in OULAD and two separately reported UCI datasets.

This aggregate-only public release accompanies the manuscript **“Stress-Testing Data Minimization Across Review Budgets and Decision Stages in Educational Early Warning: Paired Evidence from OULAD and Two UCI Datasets.”** Version 0.6.1 adds submission-ready Education Sciences/MDPI LaTeX sources and rendered PDFs without changing the C14 scientific results.

## Main findings

- Saved predictions were re-evaluated at 5%, 10%, 20%, and 30% review budgets without refitting the frozen legacy outcome models.
- Directly excluded sex/gender and disability/special-needs fields remained predictable from retained inputs. This is residual predictability, not evidence that an outcome model used a particular proxy.
- Sex/gender exclusion produced no family-wise workload-precision difference in OULAD, UCI 697, or UCI 320.
- Socioeconomic/family exclusion reduced global predictive performance throughout OULAD and UCI 697; workload penalties were concentrated in selected OULAD 30% queues and at UCI 697 enrollment.
- UCI 320 workload results remained inconclusive.
- Of 296 primary precision cells, 30 had family-wise intervals below zero and none above zero. Planned duplicate views of exact pairs are included and are not independent confirmations.

The analyses do not establish equivalence, fairness, privacy, causal educational benefit, or actual proxy use by the outcome models.

## Repository structure

| Path | Contents |
| --- | --- |
| `protocol/` | Frozen C14 protocol, analysis plan, input anchors, and harmonized blocks |
| `src/` | C14B–C14F analysis and verification code |
| `tests/` | Deterministic unit tests |
| `results/C14B/` | Multi-budget aggregate metrics and contrasts |
| `results/C14C/` | Aggregate proxy-probe metrics and model inventory; no predictions or bundles |
| `results/C14D/` | Aggregate harmonized-block results and inventories; no predictions or bundles |
| `results/C14E/` | Paired statistics and hashed bootstrap draws |
| `paper/mdpi_submission/` | Final Education Sciences/MDPI article and supplement sources, PDFs, logs, and QA record |
| `paper/figures/`, `paper/tables/` | Reproducible C14F assets generated from locked aggregate results |
| `provenance/` | Canonical phase registry and private-clean-room verification report; no superseded manuscript payload |
| `scripts/` | Release, MDPI-package, GitHub, and Zenodo verification tools |

## Verification

Python 3.12 is recommended. Poppler is required for PDF verification.

```bash
python -m pip install -r requirements.txt
python scripts/make_public_manifest.py
python scripts/verify_public_release.py
python scripts/build_release_zip.py
python scripts/verify_release_zip.py
```

Every verifier must report `PASS`. The public verifier checks the manifest, forbidden-artifact exclusions, GitHub file-size limits, unit tests, C14A/C14B/C14E numerical verification, C14C/C14D aggregate gates, locked C14F figure provenance, and the final MDPI article/supplement package.

## Manuscript files

Submission-ready files are in `paper/mdpi_submission/`:

- `outputs/SecureEWS_MDPI_article_v3.pdf` — 19 pages;
- `outputs/SecureEWS_MDPI_supplement_v3.pdf` — 9 pages;
- `article_source/article_mdpi.tex` — `education,article,submit` profile;
- `supplement_source/supplement_mdpi.tex` — `education,supfile,submit` profile.

Both PDFs were compiled from the included sources and visually inspected on every page. See `paper/mdpi_submission/README.md`, `FINAL_PUBLISH_STEPS_RU.md`, and `SUBMISSION_CHECKLIST_RU.md`.

## Reproduction and redistribution boundary

The public release can independently reproduce the reported C14E intervals from the supplied hashed bootstrap draws and regenerate C14F tables and figures from aggregate C14C/C14E results. It deliberately excludes raw or processed student-level data, individual predictions, trained model bundles, the private clean-room, and XuetangX-derived files. See [DATA_AVAILABILITY.md](DATA_AVAILABILITY.md).

## Publication status

Technical QA is complete. On 4 September 2026, the corresponding author confirmed all-author approval of the final manuscript and publication declarations. The aggregate-only repository can now be made public, tagged, archived in Zenodo, and submitted to Education Sciences.

## License

Source code is licensed under the MIT License. Documentation, manuscript materials, figures, tables, and aggregate result files are licensed under CC BY 4.0. Third-party datasets are not redistributed. See [LICENSES.md](LICENSES.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Citation

Use `CITATION.cff`. After Zenodo publication, add the version DOI to `CITATION.cff` and this README in a metadata-only follow-up commit; do not mutate the tagged `v0.6.1` payload.
