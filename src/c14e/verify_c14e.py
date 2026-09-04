#!/usr/bin/env python3
"""Independent verification of C14E draws, intervals, and multiplicity."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd


DIFFERENCE_METRICS = {
    "precision_difference", "recall_difference", "average_precision_difference",
    "auroc_difference", "brier_difference",
}
PROBABILITY_METRICS = {"average_precision_difference", "auroc_difference", "brier_difference"}
TOLERANCE = 1e-12


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--write-json", type=Path)
    args = parser.parse_args()
    result = args.result_dir.resolve()
    errors: list[str] = []
    summary = pd.read_csv(result / "paired_statistics.csv.gz", low_memory=False)
    inventory = pd.read_csv(result / "bootstrap_draw_inventory.csv")
    primary = pd.read_csv(result / "primary_precision_familywise.csv")
    families = pd.read_csv(result / "primary_family_summary.csv")
    metadata = json.loads((result / "metadata.json").read_text(encoding="utf-8"))

    if list(result.rglob("*.tmp")):
        errors.append("temporary files remain")
    if len(summary) != 2869 or len(inventory) != 151 or inventory["contrast_id"].nunique() != 151:
        errors.append("summary or contrast inventory count mismatch")
    if inventory["draw_file"].nunique() != 42 or len(list((result / "draws").glob("*.npz"))) != 42:
        errors.append("bootstrap task/draw file count mismatch")
    if len(primary) != 296 or len(families) != 23:
        errors.append("primary precision or family count mismatch")
    if metadata.get("models_refitted") is not False or not metadata.get("paired_multiplicities"):
        errors.append("metadata violates frozen no-refit/paired contract")
    if metadata.get("primary_replicates") != 5000 or metadata.get("sensitivity_replicates") != 2000:
        errors.append("bootstrap replicate contract mismatch")
    if float(metadata.get("c14b_point_replay_max_abs_error", 1)) > TOLERANCE:
        errors.append("C14B point replay gate failed")

    hash_errors = 0
    for path_text, frame in inventory.groupby("draw_file", sort=True):
        path = result / path_text
        expected = set(frame["draw_file_sha256"])
        if len(expected) != 1 or sha256(path) not in expected:
            hash_errors += 1
    if hash_errors:
        errors.append(f"draw file hash errors: {hash_errors}")

    stream_errors = 0
    for _, frame in inventory.groupby("resampling_stream", sort=True):
        if frame["first_multiplicity_sha256"].nunique() != 1:
            stream_errors += 1
    if stream_errors:
        errors.append(f"shared resampling stream errors: {stream_errors}")

    family_errors = 0
    for (family_id, metric), frame in summary.groupby(["family_id", "metric"], sort=True):
        stages = frame["stage"].nunique()
        expected = stages if metric in PROBABILITY_METRICS else stages * 4
        if len(frame) != expected or frame["family_size"].nunique() != 1 or int(frame.iloc[0]["family_size"]) != expected:
            family_errors += 1
    if family_errors:
        errors.append(f"multiplicity family errors: {family_errors}")

    max_recalculation_error = 0.0
    recalculated_rows = 0
    for draw_file, rows in summary.groupby("draw_file", sort=True):
        with np.load(result / draw_file) as draws:
            for row in rows.itertuples(index=False):
                values = np.asarray(draws[row.draw_key], dtype=float)
                if len(values) != int(row.replicates) or not np.isfinite(values).all():
                    errors.append(f"invalid draw vector: {row.contrast_id}/{row.draw_key}")
                    continue
                family_size = int(row.family_size)
                q = np.quantile(values, [0.025, 0.975, 0.05 / (2 * family_size), 1 - 0.05 / (2 * family_size)])
                observed = np.asarray([
                    row.pointwise_ci95_low, row.pointwise_ci95_high,
                    row.familywise_bonferroni_low, row.familywise_bonferroni_high,
                ])
                max_recalculation_error = max(max_recalculation_error, float(np.max(np.abs(q - observed))))
                if row.metric in DIFFERENCE_METRICS:
                    p = min(1.0, 2 * min(
                        (float(np.sum(values <= 0)) + 1) / (len(values) + 1),
                        (float(np.sum(values >= 0)) + 1) / (len(values) + 1),
                    ))
                    adjusted = min(1.0, p * family_size)
                    max_recalculation_error = max(
                        max_recalculation_error,
                        abs(p - float(row.bootstrap_sign_p_two_sided)),
                        abs(adjusted - float(row.bonferroni_adjusted_sign_p)),
                    )
                    excludes = bool(q[2] > 0 or q[3] < 0)
                    if excludes != bool(row.familywise_excludes_zero):
                        errors.append(f"familywise decision mismatch: {row.contrast_id}/{row.draw_key}")
                recalculated_rows += 1
    if max_recalculation_error > TOLERANCE:
        errors.append(f"summary recalculation tolerance exceeded: {max_recalculation_error}")

    significant_negative = int((primary["familywise_bonferroni_high"] < 0).sum())
    significant_positive = int((primary["familywise_bonferroni_low"] > 0).sum())
    if significant_negative != 30 or significant_positive != 0:
        errors.append("primary family-wise decision count mismatch")

    duplicate_max_error = 0.0
    comparison_columns = [
        "estimate", "pointwise_ci95_low", "pointwise_ci95_high",
        "familywise_bonferroni_low", "familywise_bonferroni_high",
    ]
    duplicate_specs = [
        (
            (summary["analysis_source"] == "C14B_frozen") & (summary["dataset"] == "uci697")
            & (summary["outcome"] == "dropout_vs_graduate") & (summary["model"] == "histgb")
            & (summary["contrast_name"] == "no_family_financial"),
            (summary["analysis_source"] == "C14D_harmonized") & (summary["dataset"] == "uci697")
            & (summary["outcome"] == "dropout_vs_graduate") & (summary["contrast_name"] == "socioeconomic_family"),
        ),
        (
            (summary["analysis_source"] == "C14B_frozen") & (summary["dataset"] == "uci320")
            & (summary["model"] == "histgb") & (summary["contrast_name"] == "targeted_no_sex"),
            (summary["analysis_source"] == "C14D_harmonized") & (summary["dataset"] == "uci320")
            & (summary["contrast_name"] == "sex_gender"),
        ),
    ]
    sort_columns = ["dataset", "subject", "outcome", "stage", "metric", "budget_fraction"]
    for left_mask, right_mask in duplicate_specs:
        left = summary[left_mask].sort_values(sort_columns, na_position="first")
        right = summary[right_mask].sort_values(sort_columns, na_position="first")
        if len(left) != len(right):
            errors.append("exact duplicate analysis row count mismatch")
            continue
        duplicate_max_error = max(duplicate_max_error, float(np.max(np.abs(left[comparison_columns].to_numpy() - right[comparison_columns].to_numpy()))))
    if duplicate_max_error > TOLERANCE:
        errors.append("exact duplicate analyses do not share identical statistics")

    report = {
        "phase": "C14E",
        "status": "PASS" if not errors else "FAIL",
        "checks": 15,
        "contrasts": len(inventory),
        "bootstrap_tasks": inventory["draw_file"].nunique(),
        "summary_rows_recalculated": recalculated_rows,
        "primary_precision_rows": len(primary),
        "primary_familywise_negative_cells": significant_negative,
        "primary_familywise_positive_cells": significant_positive,
        "draw_hash_errors": hash_errors,
        "multiplicity_family_errors": family_errors,
        "shared_resampling_stream_errors": stream_errors,
        "max_abs_summary_recalculation_error": max_recalculation_error,
        "max_abs_exact_duplicate_statistic_error": duplicate_max_error,
        "tolerance": TOLERANCE,
        "models_refitted": False,
        "errors": errors,
    }
    if args.write_json:
        atomic_json(args.write_json, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
