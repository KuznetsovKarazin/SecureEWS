#!/usr/bin/env python3
"""Build a deterministic public ZIP beside the repository directory."""

from __future__ import annotations

import hashlib
import os
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT.parent / "SecureEWS-v0.6.0.zip"
SHA_FILE = ROOT.parent / "SecureEWS-v0.6.0.zip.sha256"
EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", ".venv", "verification_runs"}


def main() -> int:
    temporary = OUTPUT.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file() or EXCLUDED_PARTS.intersection(path.relative_to(ROOT).parts):
                continue
            relative = Path(ROOT.name) / path.relative_to(ROOT)
            info = zipfile.ZipInfo(relative.as_posix(), date_time=(2026, 9, 4, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100644 & 0xFFFF) << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    os.replace(temporary, OUTPUT)
    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    SHA_FILE.write_text(f"{digest}  {OUTPUT.name}\n", encoding="utf-8")
    print(f"{OUTPUT}\n{digest}\n{SHA_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
