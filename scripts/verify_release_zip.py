#!/usr/bin/env python3
"""Verify ZIP CRC, sidecar SHA-256, member set, and the internal manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = ROOT.parent / "SecureEWS-v0.7.2.zip"
DEFAULT_CHECKSUM = ROOT.parent / "SecureEWS-v0.7.2.zip.sha256"
DEFAULT_OUTPUT = ROOT.parent / "SecureEWS-v0.7.2_ZIP_VERIFICATION.json"
SELF_EXCLUDED = {
    "MANIFEST.csv",
    "MANIFEST.json",
    "PUBLIC_RELEASE_VERIFICATION.json",
    "paper/mdpi_submission/MDPI_SUBMISSION_VERIFICATION.json",
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--checksum", type=Path, default=DEFAULT_CHECKSUM)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    archive_sha = file_sha256(args.archive)
    checksum_tokens = args.checksum.read_text(encoding="utf-8").split()
    sidecar_ok = len(checksum_tokens) >= 2 and checksum_tokens[0] == archive_sha and checksum_tokens[-1] == args.archive.name
    prefix = ROOT.name + "/"

    with zipfile.ZipFile(args.archive) as zipped:
        bad_member = zipped.testzip()
        files = sorted(name for name in zipped.namelist() if not name.endswith("/"))
        manifest = json.loads(zipped.read(prefix + "MANIFEST.json"))
        public_verification = json.loads(zipped.read(prefix + "PUBLIC_RELEASE_VERIFICATION.json"))
        manifest_errors = []
        for row in manifest["files"]:
            member = prefix + row["path"]
            try:
                payload = zipped.read(member)
            except KeyError:
                manifest_errors.append(f"missing: {row['path']}")
                continue
            if len(payload) != int(row["size_bytes"]):
                manifest_errors.append(f"size mismatch: {row['path']}")
            if hashlib.sha256(payload).hexdigest() != row["sha256"]:
                manifest_errors.append(f"sha256 mismatch: {row['path']}")

    expected = {prefix + row["path"] for row in manifest["files"]}
    expected.update(prefix + name for name in SELF_EXCLUDED)
    actual = set(files)
    member_set_errors = {
        "missing": sorted(expected - actual),
        "unexpected": sorted(actual - expected),
    }
    failures = []
    if bad_member is not None:
        failures.append("zip_crc")
    if not sidecar_ok:
        failures.append("sha256_sidecar")
    if manifest_errors:
        failures.append("internal_manifest")
    if any(member_set_errors.values()):
        failures.append("member_set")
    if public_verification.get("status") != "PASS":
        failures.append("public_release_verification")

    report = {
        "release": ROOT.name,
        "status": "PASS" if not failures else "FAIL",
        "archive": args.archive.name,
        "archive_size_bytes": args.archive.stat().st_size,
        "archive_sha256": archive_sha,
        "sha256_sidecar": "PASS" if sidecar_ok else "FAIL",
        "zip_integrity": "PASS" if bad_member is None else "FAIL",
        "bad_zip_member": bad_member,
        "archive_files": len(files),
        "manifest_entries": len(manifest["files"]),
        "manifest_errors": manifest_errors,
        "member_set_errors": member_set_errors,
        "public_release_verification": public_verification.get("status"),
        "failures": failures,
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
