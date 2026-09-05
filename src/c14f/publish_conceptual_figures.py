#!/usr/bin/env python3
"""Publish the authors' final conceptual figures and record their provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


FIGURE_STEMS = ("fig0_capacity_aware_framework", "fig5_results_to_practice")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command(*parts: str) -> str:
    completed = subprocess.run(parts, check=True, text=True, capture_output=True)
    return (completed.stdout or completed.stderr).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--article-figures-dir", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    args = parser.parse_args()

    source_dir = args.source_dir.resolve()
    article_dir = args.article_figures_dir.resolve()
    article_dir.mkdir(parents=True, exist_ok=True)

    source_hashes: dict[str, str] = {}
    derived_hashes: dict[str, str] = {}
    article_hashes: dict[str, str] = {}
    page_sizes: dict[str, str] = {}

    with tempfile.TemporaryDirectory(prefix="secureews_conceptual_figures_") as temporary:
        temporary_dir = Path(temporary)
        for stem in FIGURE_STEMS:
            pdf = source_dir / f"{stem}.pdf"
            if not pdf.is_file():
                raise FileNotFoundError(pdf)
            info = command("pdfinfo", str(pdf))
            if "Pages:           1" not in info:
                raise RuntimeError(f"Expected a one-page figure: {pdf}")
            page_size = next(line.split(":", 1)[1].strip() for line in info.splitlines() if line.startswith("Page size:"))
            page_sizes[pdf.name] = page_size
            source_hashes[pdf.name] = sha256(pdf)

            temporary_prefix = temporary_dir / stem
            command("pdftoppm", "-png", "-r", "300", "-singlefile", str(pdf), str(temporary_prefix))
            rendered = temporary_prefix.with_suffix(".png")
            png = source_dir / f"{stem}.png"
            shutil.copy2(rendered, png)
            derived_hashes[png.name] = sha256(png)

            for path in (pdf, png):
                destination = article_dir / path.name
                shutil.copy2(path, destination)
                article_hashes[path.name] = sha256(destination)

    script_path = Path(__file__).resolve()
    record = {
        "status": "PASS",
        "release": "SecureEWS-v0.7.2",
        "purpose": "Reader-facing conceptual synthesis; no new data or statistical result",
        "source_kind": "author-revised final vector artwork",
        "source_files": source_hashes,
        "derived_png_files": derived_hashes,
        "article_copies": article_hashes,
        "page_sizes": page_sizes,
        "png_renderer": command("pdftoppm", "-v").splitlines()[0],
        "publisher_script": "src/c14f/publish_conceptual_figures.py",
        "publisher_script_sha256": sha256(script_path),
    }
    args.provenance.parent.mkdir(parents=True, exist_ok=True)
    args.provenance.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
