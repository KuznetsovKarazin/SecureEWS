# MDPI submission package

Target journal: **Education Sciences** (`education` / `Educ. Sci.`).

Target Special Issue: **Advancing AI Education: Virtual Learning, Technology Integration, and Instructional Design**.

Manuscript: **Evaluating Data-Minimized Early-Warning Systems for Educator Decision Support: Evidence Across Review Capacities and Educational Stages**.

## Files

| Path | Use |
| --- | --- |
| `article_source/` | Upload as the main LaTeX source package |
| `supplement_source/` | Upload as Supplementary Materials source |
| `outputs/SecureEWS_MDPI_article_v6.pdf` | Main article PDF, 19 pages |
| `outputs/SecureEWS_MDPI_supplement_v6.pdf` | Supplementary Materials PDF, 9 pages |
| `build/` | Final LaTeX logs used for technical QA |
| `MDPI_SUBMISSION_QA.json` | Machine-readable post-build and visual-QA receipt |
| `MDPI_SUBMISSION_VERIFICATION.json` | Independent package-verification report |

The article uses `\documentclass[education,article,submit,moreauthors]{Definitions/mdpi}`. The supplement uses `\documentclass[education,supfile,submit,moreauthors]{Definitions/mdpi}`.

## Local compilation

A complete TeX Live installation with the MDPI template dependencies is recommended.

```bash
cd article_source
latexmk -pdf -interaction=nonstopmode -halt-on-error article_mdpi.tex

cd ../supplement_source
latexmk -pdf -interaction=nonstopmode -halt-on-error supplement_mdpi.tex
```

The bundled MDPI class conditionally loads `bbm.sty`; the manuscript does not use `\mathbbm`, so this optional dependency does not affect content or typesetting when the package is unavailable. Do not replace the bundled `Definitions/mdpi.cls` with a generic journal class. Do not upload local `.aux`, `.fls`, `.fdb_latexmk`, `.log`, or `.out` files.

## QA status

- Article: 19/19 pages rendered and visually inspected.
- Supplementary Materials: 9/9 pages rendered and visually inspected.
- Appendix numbering is verified as `Appendix A` and `Table A1`.
- The two author-revised conceptual diagrams and their PNG derivatives are checked against the included provenance hashes.
- No overfull boxes, unresolved references/citations, duplicate labels, replacement glyphs, clipping, overlap, or blank pages.
- PDF metadata identify LaTeX/pdfTeX only and contain no AI-tool marker.
- Authors, ORCIDs, affiliations, corresponding-author details, and grant AP23489228 are verified against the submission sources.

## Submission note

The source package intentionally leaves volume, issue, article number, DOI, and received/revised/accepted/published dates under publisher control. Production staff populate these fields after acceptance. Detailed computational evidence remains in separate Supplementary Materials so that the main educational narrative stays readable; Appendix A and the two synthesis diagrams provide reader-facing interpretation in the article itself.
