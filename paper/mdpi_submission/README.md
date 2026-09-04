# MDPI submission package

Target journal: **Education Sciences** (`education` / `Educ. Sci.`).

Target Special Issue: **Advancing AI Education: Virtual Learning, Technology Integration, and Instructional Design**.

## Files

| Path | Use |
| --- | --- |
| `article_source/` | Upload as the main LaTeX source package |
| `supplement_source/` | Upload as supplementary source if requested by the submission system |
| `outputs/SecureEWS_MDPI_article_v3.pdf` | Main article PDF, 19 pages |
| `outputs/SecureEWS_MDPI_supplement_v3.pdf` | Supplementary Materials PDF, 9 pages |
| `build/` | Final LaTeX logs used for technical QA |
| `MDPI_SUBMISSION_QA.json` | Machine-readable QA receipt |

The article uses `\documentclass[education,article,submit,moreauthors]{Definitions/mdpi}`. The supplement uses `\documentclass[education,supfile,submit,moreauthors]{Definitions/mdpi}`.

## Local compilation

A complete TeX Live installation with the MDPI template dependencies is required.

```bash
cd article_source
latexmk -pdf -interaction=nonstopmode -halt-on-error article_mdpi.tex

cd ../supplement_source
latexmk -pdf -interaction=nonstopmode -halt-on-error supplement_mdpi.tex
```

Do not replace the bundled `Definitions/mdpi.cls` with a generic journal class. Do not upload local `.aux`, `.fls`, `.fdb_latexmk`, or `.out` files.

## Submission note

The source package intentionally leaves volume, issue, article number, DOI, and received/revised/accepted/published dates under publisher control. Production staff populate these fields after acceptance.
