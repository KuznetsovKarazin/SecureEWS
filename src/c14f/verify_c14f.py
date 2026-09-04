#!/usr/bin/env python3
"""Independent structural and provenance checks for the C14F manuscript release."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command(*parts: str) -> str:
    return subprocess.run(parts, check=True, text=True, capture_output=True).stdout


def pdf_pages(path: Path) -> int:
    match = re.search(r"^Pages:\s+(\d+)\s*$", command("pdfinfo", str(path)), re.MULTILINE)
    if not match:
        raise RuntimeError(f"Could not read page count for {path}")
    return int(match.group(1))


def add(checks: list[dict[str, object]], name: str, passed: bool, detail: object) -> None:
    checks.append({"check": name, "status": "PASS" if passed else "FAIL", "detail": detail})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--c14c", type=Path, required=True)
    parser.add_argument("--c14e", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    release = args.release.resolve()
    article = release / "outputs/SecureEWS_C14F_article.pdf"
    supplement = release / "outputs/SecureEWS_C14F_supplement.pdf"
    checks: list[dict[str, object]] = []

    required = [
        article,
        supplement,
        release / "manuscript/main.tex",
        release / "manuscript/supplement.tex",
        release / "manuscript/references.bib",
        release / "figures/C14F_FIGURE_PROVENANCE.json",
        release / "build/main.log",
        release / "build/supplement_wrapper.log",
        release / "C14F_VISUAL_QA.json",
    ]
    missing = [path.relative_to(release).as_posix() for path in required if not path.is_file()]
    add(checks, "required_release_files", not missing, {"missing": missing})

    pages = {"article": pdf_pages(article), "supplement": pdf_pages(supplement)}
    add(checks, "pdf_page_counts", pages == {"article": 21, "supplement": 10}, pages)

    with tempfile.TemporaryDirectory(prefix="c14f_verify_") as temporary:
        temporary_path = Path(temporary)
        article_text = temporary_path / "article.txt"
        supplement_text = temporary_path / "supplement.txt"
        subprocess.run(["pdftotext", str(article), str(article_text)], check=True)
        subprocess.run(["pdftotext", str(supplement), str(supplement_text)], check=True)
        article_body = article_text.read_text(encoding="utf-8", errors="replace")
        supplement_body = supplement_text.read_text(encoding="utf-8", errors="replace")

        article_terms = [
            "Stress-Testing Data Minimization Across Review Budgets",
            "Budget sensitivity changed which workload conclusions survived",
            "Excluded fields remained predictable from retained inputs",
            "Harmonized blocks separated sex/gender",
            "Multiplicity retained losses but did not create an equivalence claim",
            "XuetangX was formally disqualified",
            "It does not prove",
            "equivalence, fairness, privacy",
        ]
        missing_article_terms = [term for term in article_terms if term not in article_body]
        add(checks, "article_required_claims_and_guards", not missing_article_terms, missing_article_terms)

        supplement_terms = [
            "C14 Multi-Budget, Proxy, and Harmonized-Block Extension",
            "C14B budget audit",
            "C14C proxy audit",
            "C14D harmonized models",
            "C14E paired statistics",
            "residual predictability is not actual proxy use",
        ]
        missing_supplement_terms = [term for term in supplement_terms if term not in supplement_body]
        add(checks, "supplement_required_inventory_and_guards", not missing_supplement_terms, missing_supplement_terms)
        replacement_counts = {
            "article": article_body.count("\ufffd"),
            "supplement": supplement_body.count("\ufffd"),
        }
        add(checks, "pdf_text_has_no_replacement_glyph", not any(replacement_counts.values()), replacement_counts)

        rendered: dict[str, int] = {}
        render_errors: list[str] = []
        for label, pdf in (("article", article), ("supplement", supplement)):
            prefix = temporary_path / label
            subprocess.run(["pdftoppm", "-png", "-r", "72", str(pdf), str(prefix)], check=True)
            images = sorted(temporary_path.glob(f"{label}-*.png"))
            rendered[label] = len(images)
            for image in images:
                if image.stat().st_size < 10_000:
                    render_errors.append(f"{image.name}: {image.stat().st_size} bytes")
        add(
            checks,
            "all_pdf_pages_render_nontrivially",
            rendered == pages and not render_errors,
            {"rendered": rendered, "small_or_missing": render_errors},
        )

    log_patterns = {
        "overfull": r"Overfull \\hbox|Overfull \\vbox",
        "undefined_reference": r"undefined references|Reference .* undefined",
        "undefined_citation": r"undefined citations|Citation .* undefined",
        "multiply_defined_label": r"multiply defined",
    }
    log_findings: dict[str, list[str]] = {}
    for log_name in ("main.log", "supplement_wrapper.log"):
        body = (release / "build" / log_name).read_text(encoding="utf-8", errors="replace")
        log_findings[log_name] = [name for name, pattern in log_patterns.items() if re.search(pattern, body, re.IGNORECASE)]
    add(checks, "latex_logs_no_overflow_or_unresolved_crossrefs", not any(log_findings.values()), log_findings)

    provenance_path = release / "figures/C14F_FIGURE_PROVENANCE.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    input_paths = {
        "paired_statistics.csv.gz": args.c14e / "paired_statistics.csv.gz",
        "primary_family_summary.csv": args.c14e / "primary_family_summary.csv",
        "proxy_primary_metrics.csv": args.c14c / "proxy_primary_metrics.csv",
    }
    input_mismatches = {
        name: {"expected": expected, "actual": sha256(input_paths[name])}
        for name, expected in provenance["inputs"].items()
        if not input_paths[name].is_file() or sha256(input_paths[name]) != expected
    }
    add(checks, "locked_c14c_c14e_input_hashes", not input_mismatches, input_mismatches)

    output_mismatches = {}
    for relative, expected in provenance["outputs"].items():
        path = release / relative
        actual = sha256(path) if path.is_file() else None
        if actual != expected:
            output_mismatches[relative] = {"expected": expected, "actual": actual}
    add(checks, "generated_figure_hashes", not output_mismatches, output_mismatches)

    visual = json.loads((release / "C14F_VISUAL_QA.json").read_text(encoding="utf-8"))
    visual_ok = (
        visual.get("status") == "PASS"
        and visual.get("article_pages_inspected") == 21
        and visual.get("supplement_pages_inspected") == 10
        and visual.get("defects") == []
    )
    add(checks, "recorded_visual_inspection", visual_ok, visual)

    failures = [item["check"] for item in checks if item["status"] != "PASS"]
    report = {
        "phase": "C14F",
        "status": "PASS" if not failures else "FAIL",
        "checks_passed": len(checks) - len(failures),
        "checks_total": len(checks),
        "failures": failures,
        "pdf_sha256": {"article": sha256(article), "supplement": sha256(supplement)},
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
