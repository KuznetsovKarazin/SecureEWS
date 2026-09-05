#!/usr/bin/env python3
"""Create deterministic CSV/JSON manifests for the public release."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {
    "COVER_LETTER_MDPI.txt",
    "FINAL_PUBLISH_STEPS_RU.md",
    "GITHUB_ZENODO_UPLOAD_RU.md",
    "MANIFEST.csv",
    "MANIFEST.json",
    "PUBLICATION_READINESS.json",
    "PUBLIC_RELEASE_VERIFICATION.json",
    "SUBMISSION_CHECKLIST_RU.md",
    "MDPI_SUBMISSION_VERIFICATION.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def main() -> int:
    rows = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.name in EXCLUDED or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        rows.append({
            "path": path.relative_to(ROOT).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=["path", "size_bytes", "sha256"], lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    atomic_text(ROOT / "MANIFEST.csv", stream.getvalue())
    atomic_text(ROOT / "MANIFEST.json", json.dumps({
        "release": "SecureEWS-v0.7.3",
        "status": "PASS",
        "scope": "public payload; manifest files and runtime verification report excluded to avoid self-reference",
        "files": rows,
    }, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "PASS", "entries": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
