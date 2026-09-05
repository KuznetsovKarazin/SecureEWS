#!/usr/bin/env python3
"""Build deterministic MDPI article, supplement, and combined submission ZIPs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MDPI = ROOT / "paper/mdpi_submission"
FIXED_TIME = (2026, 9, 4, 0, 0, 0)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def zip_entry(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o100644 & 0xFFFF) << 16
    archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def build_source_zip(source: Path, pdf: Path, pdf_name: str, output: Path) -> None:
    with zipfile.ZipFile(output, "w") as archive:
        for path in sorted(source.rglob("*")):
            if (
                path.is_file()
                and path.name != pdf_name
                and path.suffix not in {".aux", ".blg", ".fdb_latexmk", ".fls", ".log", ".out"}
            ):
                zip_entry(archive, path.relative_to(source).as_posix(), path.read_bytes())
        zip_entry(archive, pdf_name, pdf.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT.parent / "SecureEWS_MDPI_v6")
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise SystemExit(f"Refusing to overwrite existing directory: {output_dir}")

    staging = Path(tempfile.mkdtemp(prefix="secureews_mdpi_build_", dir=output_dir.parent))
    try:
        article_pdf = MDPI / "outputs/SecureEWS_MDPI_article_v6.pdf"
        supplement_pdf = MDPI / "outputs/SecureEWS_MDPI_supplement_v6.pdf"
        article_zip = staging / "SecureEWS_MDPI_article_SOURCE_v6.zip"
        supplement_zip = staging / "SecureEWS_MDPI_supplement_SOURCE_v6.zip"
        build_source_zip(MDPI / "article_source", article_pdf, "article_mdpi.pdf", article_zip)
        build_source_zip(MDPI / "supplement_source", supplement_pdf, "supplement_mdpi.pdf", supplement_zip)

        copies = {
            article_pdf: staging / article_pdf.name,
            supplement_pdf: staging / supplement_pdf.name,
            ROOT / "COVER_LETTER_MDPI.txt": staging / "COVER_LETTER_MDPI.txt",
            ROOT / "SUBMISSION_CHECKLIST_RU.md": staging / "SUBMISSION_CHECKLIST_RU.md",
            ROOT / "FINAL_PUBLISH_STEPS_RU.md": staging / "FINAL_PUBLISH_STEPS_RU.md",
            MDPI / "MDPI_SUBMISSION_QA.json": staging / "MDPI_SUBMISSION_QA.json",
            MDPI / "MDPI_SUBMISSION_VERIFICATION.json": staging / "MDPI_SUBMISSION_VERIFICATION.json",
        }
        for source, destination in copies.items():
            shutil.copy2(source, destination)

        payload_names = sorted(path.name for path in staging.iterdir() if path.is_file())
        rows = [{"path": name, "size_bytes": (staging / name).stat().st_size, "sha256": sha256(staging / name)} for name in payload_names]
        csv_stream = io.StringIO(newline="")
        writer = csv.DictWriter(csv_stream, fieldnames=["path", "size_bytes", "sha256"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        (staging / "MDPI_FILE_MANIFEST.csv").write_text(csv_stream.getvalue(), encoding="utf-8")
        (staging / "MDPI_FILE_MANIFEST.json").write_text(json.dumps({
            "package": "SecureEWS_MDPI_SUBMISSION_PACKAGE_v6",
            "status": "PASS",
            "scope": "submission payload; manifest and checksum files excluded from self-hashing",
            "files": rows,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        checksum_targets = payload_names + ["MDPI_FILE_MANIFEST.csv", "MDPI_FILE_MANIFEST.json"]
        (staging / "SHA256SUMS.txt").write_text(
            "".join(f"{sha256(staging / name)}  {name}\n" for name in checksum_targets),
            encoding="utf-8",
        )

        combined = staging / "SecureEWS_MDPI_SUBMISSION_PACKAGE_v6.zip"
        prefix = "SecureEWS_MDPI_SUBMISSION_PACKAGE_v6/"
        combined_members = sorted(path for path in staging.iterdir() if path.is_file() and path != combined)
        with zipfile.ZipFile(combined, "w") as archive:
            for path in combined_members:
                zip_entry(archive, prefix + path.name, path.read_bytes())
        bad_member = zipfile.ZipFile(combined).testzip()
        if bad_member is not None:
            raise RuntimeError(f"ZIP integrity failure: {bad_member}")
        (staging / "SecureEWS_MDPI_SUBMISSION_PACKAGE_v6.zip.sha256").write_text(
            f"{sha256(combined)}  {combined.name}\n", encoding="utf-8"
        )

        staging.replace(output_dir)
        report = {
            "status": "PASS",
            "output_dir": str(output_dir),
            "article_source_zip_sha256": sha256(output_dir / article_zip.name),
            "supplement_source_zip_sha256": sha256(output_dir / supplement_zip.name),
            "combined_zip_sha256": sha256(output_dir / combined.name),
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
