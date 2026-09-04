#!/usr/bin/env python3
"""Verify the aggregate-only SecureEWS public release."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PARTS = {"models", "inputs", "canonical_c13e", "phase_archives"}
FORBIDDEN_NAMES = {
    "proxy_predictions.csv.gz",
    "harmonized_predictions.csv.gz",
    "new_model_predictions.csv.gz",
    "oof_predictions.csv.gz",
    "SecureEWS_C14G_CLEANROOM_PROJECT.zip",
    "SecureEWS_v0.3.1_C05_COMPLETE_STAGE.zip",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], *, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
    if completed.returncode:
        raise RuntimeError(f"command failed: {' '.join(command)}\n{completed.stdout}\n{completed.stderr}")
    return completed.stdout


def add(checks: list[dict[str, object]], name: str, passed: bool, detail: object) -> None:
    checks.append({"check": name, "status": "PASS" if passed else "FAIL", "detail": detail})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "PUBLIC_RELEASE_VERIFICATION.json")
    args = parser.parse_args()
    checks: list[dict[str, object]] = []

    manifest = json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
    csv_rows = list(csv.DictReader((ROOT / "MANIFEST.csv").open(encoding="utf-8", newline="")))
    manifest_errors = []
    for row in manifest["files"]:
        path = ROOT / row["path"]
        if not path.is_file():
            manifest_errors.append(f"missing: {row['path']}")
        elif path.stat().st_size != int(row["size_bytes"]) or sha256(path) != row["sha256"]:
            manifest_errors.append(f"mismatch: {row['path']}")
    add(checks, "public_manifest", not manifest_errors and len(csv_rows) == len(manifest["files"]), {
        "entries": len(manifest["files"]), "csv_entries": len(csv_rows), "errors": manifest_errors,
    })

    files = [path for path in ROOT.rglob("*") if path.is_file() and ".git" not in path.parts]
    forbidden = []
    for path in files:
        relative = path.relative_to(ROOT)
        if FORBIDDEN_PARTS.intersection(relative.parts) or path.name in FORBIDDEN_NAMES or path.suffix in {".joblib", ".pkl", ".pickle"}:
            forbidden.append(relative.as_posix())
    add(checks, "no_raw_row_level_or_model_artifacts", not forbidden, forbidden)

    large = {path.relative_to(ROOT).as_posix(): path.stat().st_size for path in files if path.stat().st_size >= 100 * 1024 * 1024}
    add(checks, "github_100_mib_file_limit", not large, large)

    try:
        json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))
        json.loads((ROOT / "zenodo_metadata.json").read_text(encoding="utf-8"))
        metadata_ok = (ROOT / "LICENSE").is_file() and (ROOT / "LICENSES.md").is_file() and (ROOT / "CITATION.cff").is_file()
        add(checks, "publication_metadata_and_licenses", metadata_ok, "JSON parsed; required files present")
    except Exception as exc:
        add(checks, "publication_metadata_and_licenses", False, str(exc))

    python_paths = [ROOT / "src/c14b", ROOT / "src/c14c", ROOT / "src/c14d", ROOT / "src/c14e", ROOT / "src/c14f"]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(str(path) for path in python_paths)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        unit_outputs = []
        for test_path in sorted((ROOT / "tests").glob("test_*.py")):
            output = run([sys.executable, str(test_path)], env=env)
            unit_outputs.append(output.strip().splitlines()[-1])
        add(checks, "unit_tests", len(unit_outputs) == 4, unit_outputs)
    except Exception as exc:
        add(checks, "unit_tests", False, str(exc))

    verifier_commands = {
        "c14a_protocol": [sys.executable, "protocol/verify_c14a.py"],
        "c14b_aggregates": [sys.executable, "src/c14b/verify_c14b.py", "results/C14B"],
        "c14e_draws_and_statistics": [sys.executable, "src/c14e/verify_c14e.py", "--result-dir", "results/C14E"],
    }
    for name, command in verifier_commands.items():
        try:
            report = json.loads(run(command, env=env))
            add(checks, name, report.get("status") == "PASS", report)
        except Exception as exc:
            add(checks, name, False, str(exc))

    c14c = json.loads((ROOT / "results/C14C/C14C_VERIFICATION.json").read_text(encoding="utf-8"))
    add(checks, "c14c_aggregate_gate", c14c.get("status") == "PASS" and c14c.get("configurations") == 44 and c14c.get("prediction_rows") == 250044, c14c)
    c14d = json.loads((ROOT / "results/C14D/C14D_INDEPENDENT_VERIFICATION.json").read_text(encoding="utf-8"))
    add(checks, "c14d_aggregate_gate", c14d.get("status") == "PASS" and c14d.get("new_models_replayed") == 28 and c14d.get("xuetangx_c05_retrained") is False, c14d)

    try:
        with tempfile.TemporaryDirectory(prefix="secureews_public_verify_") as temporary:
            report_path = Path(temporary) / "C14F.json"
            c14f = json.loads(run([
                sys.executable, "src/c14f/verify_c14f.py", "--release", "paper",
                "--c14c", "results/C14C", "--c14e", "results/C14E", "--output", str(report_path),
            ], env=env))
        add(checks, "c14f_article_and_supplement", c14f.get("status") == "PASS", c14f)
    except Exception as exc:
        add(checks, "c14f_article_and_supplement", False, str(exc))

    private = json.loads((ROOT / "provenance/C14G_VERIFY_EXISTING.json").read_text(encoding="utf-8"))
    private_ok = (
        private.get("status") == "PASS"
        and private.get("xuetangx_c05_retrained") is False
        and private.get("checks", {}).get("project_manifest", {}).get("status") == "PASS"
    )
    add(checks, "private_cleanroom_anchor", private_ok, {
        "status": private.get("status"),
        "xuetangx_c05_retrained": private.get("xuetangx_c05_retrained"),
        "project_manifest": private.get("checks", {}).get("project_manifest", {}).get("status"),
    })

    failures = [item["check"] for item in checks if item["status"] != "PASS"]
    report = {
        "release": "SecureEWS-v0.6.0",
        "status": "PASS" if not failures else "FAIL",
        "checks_passed": len(checks) - len(failures),
        "checks_total": len(checks),
        "failures": failures,
        "public_files": len(files),
        "largest_file_bytes": max(path.stat().st_size for path in files),
        "checks": checks,
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
