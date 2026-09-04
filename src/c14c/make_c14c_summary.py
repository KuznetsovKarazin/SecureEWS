#!/usr/bin/env python3
"""Create compact primary tables from C14C proxy metrics."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_dir", type=Path)
    args = parser.parse_args()
    metrics = pd.read_csv(args.result_dir / "proxy_metrics.csv")
    primary = metrics[
        (metrics["model"] == "logistic")
        & metrics["evaluation_cohort"].isin(["all_2014J", "all_oof"])
    ].copy()
    primary = primary.sort_values(["dataset", "subject", "target_field", "stage"])
    primary.to_csv(args.result_dir / "proxy_primary_metrics.csv", index=False)
    ranges = (
        primary.groupby(["dataset", "subject", "target_field"], dropna=False)
        .agg(
            stages=("stage", "nunique"),
            minimum_auroc=("auroc", "min"),
            maximum_auroc=("auroc", "max"),
            minimum_ap_lift=("ap_lift_over_prevalence", "min"),
            maximum_ap_lift=("ap_lift_over_prevalence", "max"),
            minimum_balanced_accuracy=("balanced_accuracy", "min"),
            maximum_balanced_accuracy=("balanced_accuracy", "max"),
        )
        .reset_index()
    )
    ranges.to_csv(args.result_dir / "proxy_primary_ranges.csv", index=False)
    print({"primary_rows": len(primary), "range_rows": len(ranges)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

