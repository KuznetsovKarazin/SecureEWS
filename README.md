# SecureEWS v0.6.0

SecureEWS is an auditable, post-development stress test of data-minimization claims in educational early-warning systems. The release evaluates whether conclusions change across review budgets, prediction stages, excluded feature blocks, and metrics in OULAD and two separately reported UCI datasets.

This public package contains source code, frozen protocols, aggregate results, paired-bootstrap draws, verification reports, manuscript sources, and rendered PDFs. It deliberately excludes raw or processed row-level educational data, individual predictions, trained model bundles, and the preserved XuetangX C05 archive.

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
| `paper/` | Academic article, supplement, LaTeX source, tables, figures, and PDF QA records |
| `provenance/` | Canonical phase registry and full private-clean-room verification report |
| `scripts/` | Public-release verification, packaging, and Zenodo draft scripts |

## Verification

Python 3.12 is recommended. Poppler is required for PDF verification.

```bash
python -m pip install -r requirements.txt
python scripts/verify_public_release.py
```

The public verifier checks the manifest, forbidden-artifact exclusions, GitHub file-size limits, unit tests, C14A/C14B/C14E numerical verification, C14C/C14D aggregate gates, and the complete C14F PDF/provenance checks. After packaging, `scripts/verify_release_zip.py` additionally checks ZIP integrity, the checksum sidecar, the exact member set, and every internal-manifest hash.

## Reproduction boundary

The public release can independently reproduce the reported C14E intervals from the supplied hashed bootstrap draws and can regenerate C14F tables and figures from aggregate C14C/C14E results. Full model refitting and row-level prediction replay require the official datasets and the separately retained private clean-room checkpoint. See [DATA_AVAILABILITY.md](DATA_AVAILABILITY.md).

## Article

- `paper/outputs/SecureEWS_C14F_article.pdf`
- `paper/outputs/SecureEWS_C14F_supplement.pdf`

The manuscript is a working revision. Author order, CRediT roles, funding wording, ethics determination, competing-interest declarations, and final author approval must be confirmed before journal submission or permanent public publication.

## License

Source code is licensed under the MIT License. Documentation, manuscript materials, figures, tables, and aggregate result files are licensed under CC BY 4.0. Third-party datasets are not redistributed. See [LICENSES.md](LICENSES.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Citation

Please use the metadata in `CITATION.cff`. A Zenodo DOI can be added after a draft record has been created or when the release is published.
