#!/usr/bin/env python3
"""Independent structural and algebraic verification of SecureEWS C14B."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


EXPECTED_BUDGETS = [0.05, 0.10, 0.20, 0.30]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_dir", type=Path)
    args = parser.parse_args()
    errors: list[str] = []

    verification = json.loads((args.result_dir / "C14B_VERIFICATION.json").read_text(encoding="utf-8"))
    probability = pd.read_csv(args.result_dir / "probability_metrics.csv")
    budget = pd.read_csv(args.result_dir / "budget_metrics.csv")
    prob_contrasts = pd.read_csv(args.result_dir / "probability_contrasts_vs_full.csv")
    contrasts = pd.read_csv(args.result_dir / "budget_contrasts_vs_full.csv")
    primary = pd.read_csv(args.result_dir / "primary_budget_contrasts.csv")
    stability = pd.read_csv(args.result_dir / "budget_sign_stability.csv")

    if verification.get("status") != "PASS" or verification.get("models_fitted") != 0:
        errors.append("verification status/models_fitted guard failed")
    if sorted(budget["budget_fraction"].unique().tolist()) != EXPECTED_BUDGETS:
        errors.append("budget grid mismatch")
    if len(probability) != 150 or len(budget) != 600:
        errors.append("absolute row count mismatch")
    if len(prob_contrasts) != 363 or len(contrasts) != 484:
        errors.append("contrast row count mismatch")
    if len(primary) != 176 or len(stability) != 44:
        errors.append("primary summary row count mismatch")
    if int(stability["strict_sign_reversal_across_budgets"].sum()) != 30:
        errors.append("sign-reversal count mismatch")
    if verification.get("max_abs_10pct_replay_error", 1.0) > 1e-12:
        errors.append("10% replay tolerance exceeded")

    config_budget_counts = budget.groupby("config_id")["budget_fraction"].nunique()
    if not (config_budget_counts == 4).all():
        errors.append("not every configuration has four budgets")
    if budget[["precision", "recall", "lift"]].isna().any().any():
        errors.append("non-finite queue metric")
    if not np.allclose(
        contrasts["precision_difference"],
        contrasts["restricted_precision"] - contrasts["full_precision"],
        atol=1e-15,
        rtol=0,
    ):
        errors.append("precision contrast algebra failed")
    if not np.allclose(
        contrasts["recall_difference"],
        contrasts["restricted_recall"] - contrasts["full_recall"],
        atol=1e-15,
        rtol=0,
    ):
        errors.append("recall contrast algebra failed")
    if not contrasts["alert_jaccard_vs_full"].between(0, 1).all():
        errors.append("Jaccard outside [0,1]")
    if not contrasts["retained_full_alert_fraction"].between(0, 1).all():
        errors.append("retained fraction outside [0,1]")

    report = {
        "phase": "C14B",
        "status": "PASS" if not errors else "FAIL",
        "checks": 13,
        "models_fitted": 0,
        "absolute_configurations": int(len(probability)),
        "budget_rows": int(len(budget)),
        "contrast_rows": int(len(contrasts)),
        "primary_stage_policy_families": int(len(stability)),
        "strict_sign_reversal_families": int(stability["strict_sign_reversal_across_budgets"].sum()),
        "errors": errors,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
