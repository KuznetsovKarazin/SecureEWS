#!/usr/bin/env python3
"""Verify the final Education Sciences/MDPI article and supplement package."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "paper/mdpi_submission"
OUTPUT = PACKAGE / "MDPI_SUBMISSION_VERIFICATION.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command(*parts: str) -> str:
    completed = subprocess.run(parts, check=True, text=True, capture_output=True)
    return completed.stdout


def pdf_pages(path: Path) -> int:
    match = re.search(r"^Pages:\s+(\d+)\s*$", command("pdfinfo", str(path)), re.MULTILINE)
    if not match:
        raise RuntimeError(f"Could not read page count for {path}")
    return int(match.group(1))


def add(checks: list[dict[str, object]], name: str, passed: bool, detail: object) -> None:
    checks.append({"check": name, "status": "PASS" if passed else "FAIL", "detail": detail})


def main() -> int:
    article_tex = PACKAGE / "article_source/article_mdpi.tex"
    supplement_tex = PACKAGE / "supplement_source/supplement_mdpi.tex"
    article_pdf = PACKAGE / "outputs/SecureEWS_MDPI_article_v6.pdf"
    supplement_pdf = PACKAGE / "outputs/SecureEWS_MDPI_supplement_v6.pdf"
    qa_path = PACKAGE / "MDPI_SUBMISSION_QA.json"
    provenance_path = PACKAGE / "article_source/figures/C14F_FIGURE_PROVENANCE.json"
    conceptual_provenance_path = ROOT / "paper/figures/CONCEPTUAL_FIGURE_PROVENANCE.json"
    logs = [PACKAGE / "build/article_mdpi.log", PACKAGE / "build/supplement_mdpi.log"]
    required = [
        article_tex,
        supplement_tex,
        article_pdf,
        supplement_pdf,
        qa_path,
        provenance_path,
        conceptual_provenance_path,
        *logs,
    ]
    checks: list[dict[str, object]] = []

    missing = [path.relative_to(ROOT).as_posix() for path in required if not path.is_file()]
    add(checks, "required_files", not missing, missing)
    if missing:
        OUTPUT.write_text(json.dumps({"status": "FAIL", "failures": ["required_files"], "checks": checks}, indent=2) + "\n")
        return 1

    article_source = article_tex.read_text(encoding="utf-8")
    supplement_source = supplement_tex.read_text(encoding="utf-8")
    source_checks = {
        "article_profile": r"\\documentclass\[education,article,submit,moreauthors\]\{Definitions/mdpi\}",
        "supplement_profile": r"\\documentclass\[education,supfile,submit,moreauthors\]\{Definitions/mdpi\}",
    }
    source_errors = []
    if not re.search(source_checks["article_profile"], article_source):
        source_errors.append("article profile")
    if not re.search(source_checks["supplement_profile"], supplement_source):
        source_errors.append("supplement profile")
    if "apajournal" in article_source + supplement_source:
        source_errors.append("generic apajournal option")
    if "Journal Not Specified" in article_source + supplement_source:
        source_errors.append("incorrect journal identity")
    add(checks, "mdpi_source_profiles", not source_errors, source_errors)

    authors = [
        ("Aigul Shaikhanova", "0000-0001-6006-4813"),
        ("Oleksandr Kuznetsov", "0000-0003-2331-6326"),
        ("Gulmira Shangytbayeva", "0000-0003-4615-5756"),
        ("Kamila Bakenova", "0009-0004-2567-173X"),
        ("Kainizhamal Iklassova", "0000-0002-8330-4282"),
        ("Dana Tulemisova", "0009-0006-5319-7742"),
    ]
    author_errors = []
    for name, orcid in authors:
        if name not in article_source or name not in supplement_source:
            author_errors.append(f"missing author: {name}")
        if orcid not in article_source or orcid not in supplement_source:
            author_errors.append(f"missing ORCID: {orcid}")
    required_correspondence = [
        "Oleksandr Kuznetsov $^{3,4,*}$",
        "Gulmira Shangytbayeva $^{5,*}$",
        "oleksandr.kuznetsov@uniecampus.it",
        "gshangytbayeva@zhubanov.edu.kz",
    ]
    for item in required_correspondence:
        if item not in article_source or item not in supplement_source:
            author_errors.append(f"missing corresponding-author item: {item}")
    funding_terms = [
        "Science Committee of the Ministry of Science and Higher Education of the Republic of Kazakhstan",
        "AP23489228",
    ]
    for term in funding_terms:
        if term not in article_source:
            author_errors.append(f"missing funding item: {term}")
    add(checks, "authors_orcids_correspondence_and_funding", not author_errors, author_errors)

    statement_terms = [
        "Not applicable. This study used only publicly accessible, de-identified secondary datasets",
        "aggregate-only reproducibility release accompanying this submission",
        "OpenAI ChatGPT and Codex",
        "The authors declare no conflicts of interest",
    ]
    missing_statements = [term for term in statement_terms if term not in article_source]
    add(checks, "required_declarations_present", not missing_statements, missing_statements)

    editorial_markers = [
        "working revision",
        "confirmation required",
        "to be confirmed",
        "fill in before submission",
        "no final declaration",
        "repository is currently private",
    ]
    editorial_findings = [
        marker for marker in editorial_markers
        if marker in (article_source + "\n" + supplement_source).lower()
    ]
    add(checks, "no_editorial_working_markers", not editorial_findings, editorial_findings)

    markup_patterns = {
        "track_change_command": r"\\(?:todo|hl|added|deleted|replaced|comment)\b",
        "editorial_note": r"\b(?:editorial note|author query|query to author|aq:)\b",
    }
    markup_findings = [
        name for name, pattern in markup_patterns.items()
        if re.search(pattern, article_source + "\n" + supplement_source, re.IGNORECASE)
    ]
    add(checks, "no_editorial_markup_commands", not markup_findings, markup_findings)

    qa = json.loads(qa_path.read_text(encoding="utf-8"))
    expected_pages = {
        "article": qa.get("article", {}).get("pages"),
        "supplement": qa.get("supplement", {}).get("pages"),
    }
    pages = {"article": pdf_pages(article_pdf), "supplement": pdf_pages(supplement_pdf)}
    add(checks, "pdf_page_counts", pages == expected_pages, {"actual": pages, "expected": expected_pages})

    with tempfile.TemporaryDirectory(prefix="secureews_mdpi_verify_") as temporary:
        temporary_path = Path(temporary)
        pdf_text: dict[str, str] = {}
        render_counts: dict[str, int] = {}
        render_errors: list[str] = []
        for label, pdf in (("article", article_pdf), ("supplement", supplement_pdf)):
            text_path = temporary_path / f"{label}.txt"
            subprocess.run(["pdftotext", str(pdf), str(text_path)], check=True)
            pdf_text[label] = text_path.read_text(encoding="utf-8", errors="replace")
            prefix = temporary_path / label
            subprocess.run(["pdftoppm", "-png", "-r", "72", str(pdf), str(prefix)], check=True)
            images = sorted(temporary_path.glob(f"{label}-*.png"))
            render_counts[label] = len(images)
            render_errors.extend(f"{image.name}: {image.stat().st_size}" for image in images if image.stat().st_size < 10_000)

    pdf_errors = []
    metadata_errors = []
    pdf_paths = {"article": article_pdf, "supplement": supplement_pdf}
    for label, body in pdf_text.items():
        normalized = " ".join(body.split()).lower()
        if "journal not specified" in normalized:
            pdf_errors.append(f"{label}: Journal Not Specified")
        if "submitted to educ. sci." not in normalized:
            pdf_errors.append(f"{label}: missing Educ. Sci. identity")
        if "evaluating data-minimized early-warning systems for educator decision support" not in normalized or "evidence across review capacities and educational stages" not in normalized:
            pdf_errors.append(f"{label}: missing title")
        if "\ufffd" in body:
            pdf_errors.append(f"{label}: replacement glyph")
        metadata = command("pdfinfo", str(pdf_paths[label]))
        for field in ("Creator", "Producer"):
            match = re.search(rf"^{field}:\s*(.*)$", metadata, re.MULTILINE)
            value = match.group(1) if match else ""
            if re.search(r"openai|chatgpt|codex|language model|ai-generated", value, re.IGNORECASE):
                metadata_errors.append(f"{label}: {field}={value}")
    article_normalized = " ".join(pdf_text["article"].split()).lower()
    appendix_errors = []
    if "appendix a practical interpretation guide" not in article_normalized:
        appendix_errors.append("missing Appendix A heading")
    if "table a1. plain-language interpretation" not in article_normalized:
        appendix_errors.append("missing Table A1 caption")
    if "appendix f practical interpretation guide" in article_normalized:
        appendix_errors.append("stale Appendix F heading")
    add(checks, "pdf_identity_and_text", not pdf_errors, pdf_errors)
    add(checks, "appendix_numbering", not appendix_errors, appendix_errors)
    add(checks, "pdf_metadata_has_no_ai_tool_marker", not metadata_errors, metadata_errors)
    add(checks, "all_pages_render", render_counts == pages and not render_errors, {"rendered": render_counts, "errors": render_errors})

    critical_patterns = {
        "overfull": r"Overfull \\hbox|Overfull \\vbox",
        "undefined_reference": r"undefined references|Reference .* undefined",
        "undefined_citation": r"undefined citations|Citation .* undefined",
        "duplicate_label": r"multiply defined",
    }
    log_findings: dict[str, list[str]] = {}
    for log in logs:
        body = log.read_text(encoding="utf-8", errors="replace")
        log_findings[log.name] = [name for name, pattern in critical_patterns.items() if re.search(pattern, body, re.IGNORECASE)]
    add(checks, "latex_logs_no_critical_findings", not any(log_findings.values()), log_findings)

    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    input_paths = {
        "paired_statistics.csv.gz": ROOT / "results/C14E/paired_statistics.csv.gz",
        "primary_family_summary.csv": ROOT / "results/C14E/primary_family_summary.csv",
        "proxy_primary_metrics.csv": ROOT / "results/C14C/proxy_primary_metrics.csv",
    }
    input_mismatches = {
        name: {"expected": expected, "actual": sha256(input_paths[name]) if input_paths[name].is_file() else None}
        for name, expected in provenance["inputs"].items()
        if not input_paths[name].is_file() or sha256(input_paths[name]) != expected
    }
    add(checks, "locked_c14c_c14e_input_hashes", not input_mismatches, input_mismatches)

    output_mismatches = {}
    for relative, expected in provenance["outputs"].items():
        path = PACKAGE / "article_source" / relative
        actual = sha256(path) if path.is_file() else None
        if actual != expected:
            output_mismatches[relative] = {"expected": expected, "actual": actual}
    add(checks, "generated_c14f_figure_hashes", not output_mismatches, output_mismatches)

    conceptual = json.loads(conceptual_provenance_path.read_text(encoding="utf-8"))
    conceptual_mismatches = {}
    expected_assets = {
        **conceptual.get("source_files", {}),
        **conceptual.get("derived_png_files", {}),
    }
    for name, expected in expected_assets.items():
        paper_path = ROOT / "paper/figures" / name
        article_path = PACKAGE / "article_source/figures" / name
        for location, path in (("paper", paper_path), ("article_source", article_path)):
            actual = sha256(path) if path.is_file() else None
            if actual != expected:
                conceptual_mismatches[f"{location}/{name}"] = {"expected": expected, "actual": actual}
    publisher_source = ROOT / conceptual.get("publisher_script", "")
    expected_source = conceptual.get("publisher_script_sha256")
    actual_source = sha256(publisher_source) if publisher_source.is_file() else None
    if actual_source != expected_source:
        conceptual_mismatches[conceptual.get("publisher_script", "publisher_script")] = {
            "expected": expected_source,
            "actual": actual_source,
        }
    add(checks, "conceptual_figure_provenance", not conceptual_mismatches, conceptual_mismatches)

    hash_checks = {
        "article_source": (qa["article"]["source_sha256"], sha256(article_tex)),
        "article_pdf": (qa["article"]["pdf_sha256"], sha256(article_pdf)),
        "supplement_source": (qa["supplement"]["source_sha256"], sha256(supplement_tex)),
        "supplement_pdf": (qa["supplement"]["pdf_sha256"], sha256(supplement_pdf)),
    }
    mismatches = {name: {"expected": expected, "actual": actual} for name, (expected, actual) in hash_checks.items() if expected != actual}
    qa_ok = (
        qa.get("status") == "PASS"
        and qa.get("article", {}).get("pages_visually_inspected") == pages["article"]
        and qa.get("supplement", {}).get("pages_visually_inspected") == pages["supplement"]
        and qa.get("checks", {}).get("visual_defects") == []
    )
    add(checks, "qa_hashes_and_visual_record", qa_ok and not mismatches, {"hash_mismatches": mismatches, "qa_status": qa.get("status")})

    failures = [item["check"] for item in checks if item["status"] != "PASS"]
    report = {
        "release": "SecureEWS-v0.7.3",
        "status": "PASS" if not failures else "FAIL",
        "checks_passed": len(checks) - len(failures),
        "checks_total": len(checks),
        "failures": failures,
        "pdf_sha256": {"article": sha256(article_pdf), "supplement": sha256(supplement_pdf)},
        "checks": checks,
    }
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
