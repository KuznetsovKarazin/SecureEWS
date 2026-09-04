#!/usr/bin/env python3
"""Structural verification for the frozen SecureEWS C14A protocol."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main() -> int:
    errors: list[str] = []
    plan = json.loads((ROOT / "C14_ANALYSIS_PLAN.json").read_text(encoding="utf-8"))
    anchors = json.loads((ROOT / "INPUT_ANCHORS.json").read_text(encoding="utf-8"))
    with (ROOT / "HARMONIZED_BLOCKS.csv").open(encoding="utf-8", newline="") as handle:
        blocks = list(csv.DictReader(handle))

    if plan.get("status") != "FROZEN_BEFORE_C14B_C14C_C14D_RESULTS":
        errors.append("protocol status is not frozen")
    if plan["c14b"].get("budgets") != [0.05, 0.1, 0.2, 0.3]:
        errors.append("budget grid changed")
    if plan["c14b"].get("models_refit") is not False:
        errors.append("C14B must not refit models")
    if plan["c14d"].get("same_run_full_control_required") is not True:
        errors.append("same-run control guard missing")
    if plan["c14d"].get("full_replay_tolerance_max_abs_probability") != 1e-12:
        errors.append("control replay tolerance changed")
    if plan["c14e"].get("primary_bootstrap_replicates") != 5000:
        errors.append("primary bootstrap count changed")
    if plan["canonical_parent"].get("archive_sha256") != anchors["c13e_archive"].get("sha256"):
        errors.append("C13E anchor mismatch")
    if {row["block_id"] for row in blocks} != {"sex_gender", "socioeconomic_family"}:
        errors.append("harmonized block registry mismatch")
    if len(blocks) != 6:
        errors.append("expected six dataset-block mappings")

    result = {"status": "PASS" if not errors else "FAIL", "checks": 8, "errors": errors}
    print(json.dumps(result, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
