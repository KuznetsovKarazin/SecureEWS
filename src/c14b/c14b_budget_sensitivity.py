#!/usr/bin/env python3
"""SecureEWS C14B: multi-budget audit from frozen predictions only."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


BUDGETS = (0.05, 0.10, 0.20, 0.30)
UCI_SEEDS = {"uci697": 20260830, "uci320": 20260902}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def uci_tie_key(dataset: str, row_id: int, seed: int) -> str:
    raw = f"SecureEWS-C13A|{dataset}|{int(row_id)}|{seed}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def select_at_budget(
    probabilities: np.ndarray,
    groups: np.ndarray,
    tie_keys: np.ndarray,
    budget: float,
) -> np.ndarray:
    selected = np.zeros(len(probabilities), dtype=bool)
    group_text = np.asarray(groups).astype(str)
    for group in sorted(np.unique(group_text)):
        positions = np.flatnonzero(group_text == group)
        k = max(1, min(len(positions), int(math.ceil(budget * len(positions)))))
        order = positions[np.lexsort((tie_keys[positions], -probabilities[positions]))]
        selected[order[:k]] = True
    return selected


def probability_metrics(y: np.ndarray, p: np.ndarray) -> dict:
    return {
        "n": int(len(y)),
        "risk_cases": int(y.sum()),
        "prevalence": float(y.mean()),
        "average_precision": float(average_precision_score(y, p)),
        "auroc": float(roc_auc_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
    }


def queue_metrics(y: np.ndarray, selected: np.ndarray) -> dict:
    alerts = int(selected.sum())
    true_alerts = int(y[selected].sum())
    risk_cases = int(y.sum())
    prevalence = float(y.mean())
    precision = true_alerts / alerts if alerts else float("nan")
    recall = true_alerts / risk_cases if risk_cases else float("nan")
    return {
        "alerts": alerts,
        "true_alerts": true_alerts,
        "false_alerts": alerts - true_alerts,
        "precision": precision,
        "recall": recall,
        "lift": precision / prevalence if prevalence else float("nan"),
    }


def overlap_metrics(restricted: np.ndarray, full: np.ndarray) -> dict:
    intersection = int(np.logical_and(restricted, full).sum())
    union = int(np.logical_or(restricted, full).sum())
    full_alerts = int(full.sum())
    return {
        "alert_intersection": intersection,
        "alert_union": union,
        "alert_jaccard_vs_full": intersection / union if union else float("nan"),
        "retained_full_alert_fraction": intersection / full_alerts if full_alerts else float("nan"),
    }


def parse_oulad_name(path: Path) -> tuple[int, str, str]:
    name = path.name.removeprefix("test__").removesuffix(".csv.gz")
    day, policy, grid = name.split("__", 2)
    return int(day.removeprefix("day")), policy, grid


def load_oulad(prediction_dir: Path, point_metrics_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    point = pd.read_csv(point_metrics_path)
    point_index = point.set_index("name")
    probability_rows: list[dict] = []
    budget_rows: list[dict] = []
    selections: dict[tuple, tuple[pd.DataFrame, np.ndarray]] = {}
    replay_errors: list[dict] = []

    for path in sorted(prediction_dir.glob("test__*.csv.gz")):
        cutoff, policy, grid = parse_oulad_name(path)
        name = f"day{cutoff}__{policy}__{grid}"
        frame = pd.read_csv(path, dtype={"imd_band": str}, low_memory=False)
        frame = frame.sort_values(["code_module", "code_presentation", "id_student"]).reset_index(drop=True)
        y = frame["target_risk"].to_numpy(dtype=int)
        p = frame["probability_calibrated"].to_numpy(dtype=float)
        groups = frame["code_module"].astype(str).to_numpy()
        tie_keys = frame["tie_key_sha256"].astype(str).to_numpy()
        group = str(point_index.loc[name, "group"])
        base = {
            "dataset": "oulad",
            "subject": "all",
            "outcome": "future_fail_or_withdrawn",
            "stage": f"day{cutoff}",
            "policy": policy,
            "model": "histgb",
            "grid": grid,
            "analysis_group": group,
            "config_id": name,
            "source_prediction_sha256": sha256(path),
        }
        probability_rows.append({**base, **probability_metrics(y, p)})
        for budget in BUDGETS:
            selected = select_at_budget(p, groups, tie_keys, budget)
            selections[("oulad", "all", "future_fail_or_withdrawn", f"day{cutoff}", policy, "histgb", grid, budget)] = (frame, selected)
            budget_rows.append({**base, "budget_fraction": budget, **queue_metrics(y, selected)})

        reference = point_index.loc[name]
        observed = next(row for row in budget_rows if row["config_id"] == name and row["budget_fraction"] == 0.10)
        checks = {
            "alerts": int(reference["test_alerts"]),
            "true_alerts": int(reference["test_true_alerts"]),
            "false_alerts": int(reference["test_false_alerts"]),
            "precision": float(reference["test_precision_at_10"]),
            "recall": float(reference["test_recall_at_10"]),
        }
        max_error = max(abs(float(observed[key]) - value) for key, value in checks.items())
        replay_errors.append({"config_id": name, "max_abs_10pct_replay_error": max_error})

    return pd.DataFrame(probability_rows), pd.DataFrame(budget_rows), {"selections": selections, "replay": replay_errors}


def load_uci(predictions_path: Path, absolute_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    predictions = pd.read_csv(predictions_path, dtype={"budget_group": str}, low_memory=False)
    reference = pd.read_csv(absolute_path)
    reference = reference[reference["tie_rule"] == "canonical_hash"].copy()
    probability_rows: list[dict] = []
    budget_rows: list[dict] = []
    selections: dict[tuple, tuple[pd.DataFrame, np.ndarray]] = {}
    replay_errors: list[dict] = []

    keys = ["dataset", "subject", "outcome", "stage", "policy", "model", "exploratory", "config_id"]
    for key, raw in predictions.groupby(keys, sort=True, dropna=False):
        attrs = dict(zip(keys, key))
        frame = raw.sort_values("row_id").reset_index(drop=True)
        dataset = str(attrs["dataset"])
        seed = UCI_SEEDS[dataset]
        y = frame["target_risk"].to_numpy(dtype=int)
        p = frame["probability_calibrated"].to_numpy(dtype=float)
        groups = frame["budget_group"].astype(str).to_numpy()
        tie_keys = np.asarray([uci_tie_key(dataset, row_id, seed) for row_id in frame["row_id"]])
        base = {**attrs, "grid": "c13_selected", "analysis_group": "uci", "source_prediction_sha256": sha256(predictions_path)}
        probability_rows.append({**base, **probability_metrics(y, p)})
        for budget in BUDGETS:
            selected = select_at_budget(p, groups, tie_keys, budget)
            selection_key = (
                dataset,
                str(attrs["subject"]),
                str(attrs["outcome"]),
                str(attrs["stage"]),
                str(attrs["policy"]),
                str(attrs["model"]),
                "c13_selected",
                budget,
            )
            selections[selection_key] = (frame, selected)
            budget_rows.append({**base, "budget_fraction": budget, **queue_metrics(y, selected)})

        ref = reference[reference["config_id"] == attrs["config_id"]].set_index("metric")["value"]
        observed_probability = probability_rows[-1]
        observed_budget = budget_rows[-3]
        expected = {
            "average_precision": float(ref["average_precision"]),
            "auroc": float(ref["auroc"]),
            "brier": float(ref["brier"]),
            "precision": float(ref["precision_at_10pct_budget"]),
            "recall": float(ref["recall_at_10pct_budget"]),
        }
        observed = {**observed_probability, **observed_budget}
        max_error = max(abs(float(observed[name]) - value) for name, value in expected.items())
        replay_errors.append({"config_id": attrs["config_id"], "max_abs_10pct_replay_error": max_error})

    return pd.DataFrame(probability_rows), pd.DataFrame(budget_rows), {"selections": selections, "replay": replay_errors}


def build_contrasts(probability: pd.DataFrame, budget: pd.DataFrame, selections: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    prob_rows: list[dict] = []
    queue_rows: list[dict] = []
    family_keys = ["dataset", "subject", "outcome", "stage", "model", "grid"]

    for family, candidates in probability.groupby(family_keys, sort=True, dropna=False):
        full = candidates[candidates["policy"] == "full"]
        if full.empty:
            continue
        full_row = full.iloc[0]
        for _, restricted in candidates[candidates["policy"] != "full"].iterrows():
            base = dict(zip(family_keys, family))
            base.update({"policy": restricted["policy"], "comparator": "full", "config_id": restricted["config_id"], "full_config_id": full_row["config_id"]})
            for metric in ["average_precision", "auroc", "brier"]:
                prob_rows.append({**base, "metric": metric, "restricted": restricted[metric], "full": full_row[metric], "difference": restricted[metric] - full_row[metric]})

    queue_index = budget.set_index(family_keys + ["policy", "budget_fraction"])
    for family, candidates in probability.groupby(family_keys, sort=True, dropna=False):
        if not (candidates["policy"] == "full").any():
            continue
        full_config = candidates[candidates["policy"] == "full"].iloc[0]["config_id"]
        for policy in sorted(set(candidates["policy"]) - {"full"}):
            restricted_config = candidates[candidates["policy"] == policy].iloc[0]["config_id"]
            for budget_fraction in BUDGETS:
                base_key = tuple(family)
                restricted = queue_index.loc[base_key + (policy, budget_fraction)]
                full = queue_index.loc[base_key + ("full", budget_fraction)]
                family_map = dict(zip(family_keys, family))
                selection_key_r = (
                    family_map["dataset"],
                    family_map["subject"],
                    family_map["outcome"],
                    family_map["stage"],
                    policy,
                    family_map["model"],
                    family_map["grid"],
                    budget_fraction,
                )
                selection_key_f = (
                    family_map["dataset"],
                    family_map["subject"],
                    family_map["outcome"],
                    family_map["stage"],
                    "full",
                    family_map["model"],
                    family_map["grid"],
                    budget_fraction,
                )
                frame_r, selected_r = selections[selection_key_r]
                frame_f, selected_f = selections[selection_key_f]
                if not np.array_equal(frame_r["target_risk"].to_numpy(), frame_f["target_risk"].to_numpy()):
                    raise AssertionError(f"target mismatch for {restricted_config}")
                overlap = overlap_metrics(selected_r, selected_f)
                base = dict(zip(family_keys, family))
                queue_rows.append({
                    **base,
                    "policy": policy,
                    "comparator": "full",
                    "config_id": restricted_config,
                    "full_config_id": full_config,
                    "budget_fraction": budget_fraction,
                    "restricted_precision": restricted["precision"],
                    "full_precision": full["precision"],
                    "precision_difference": restricted["precision"] - full["precision"],
                    "restricted_recall": restricted["recall"],
                    "full_recall": full["recall"],
                    "recall_difference": restricted["recall"] - full["recall"],
                    "true_alert_difference": int(restricted["true_alerts"] - full["true_alerts"]),
                    "false_alert_difference": int(restricted["false_alerts"] - full["false_alerts"]),
                    **overlap,
                })

    return pd.DataFrame(prob_rows), pd.DataFrame(queue_rows)


def build_summary_tables(budget_contrasts: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    primary_mask = (
        (
            (budget_contrasts["dataset"] == "oulad")
            & (budget_contrasts["grid"] == "standard")
            & budget_contrasts["policy"].isin(["minimized", "partial_gender_disability"])
        )
        | (
            (budget_contrasts["dataset"] == "uci697")
            & (budget_contrasts["outcome"] == "dropout_vs_graduate")
            & (budget_contrasts["model"] == "histgb")
            & budget_contrasts["policy"].isin(
                ["legacy_operational", "no_direct_personal", "no_family_financial", "targeted_gender_special_needs"]
            )
        )
        | ((budget_contrasts["dataset"] == "uci320") & (budget_contrasts["model"] == "histgb"))
    )
    primary = budget_contrasts.loc[primary_mask].copy()
    primary = primary.sort_values(["dataset", "subject", "outcome", "stage", "policy", "budget_fraction"])

    family_keys = ["dataset", "subject", "outcome", "stage", "policy", "model", "grid"]
    rows = []
    for family, frame in primary.groupby(family_keys, sort=True, dropna=False):
        delta = frame["precision_difference"].to_numpy(dtype=float)
        at_10 = float(frame.loc[np.isclose(frame["budget_fraction"], 0.10), "precision_difference"].iloc[0])
        rows.append(
            {
                **dict(zip(family_keys, family)),
                "precision_difference_at_10pct": at_10,
                "minimum_precision_difference": float(delta.min()),
                "maximum_precision_difference": float(delta.max()),
                "negative_budget_count": int((delta < 0).sum()),
                "zero_budget_count": int((delta == 0).sum()),
                "positive_budget_count": int((delta > 0).sum()),
                "strict_sign_reversal_across_budgets": bool(delta.min() < 0 and delta.max() > 0),
                "contains_exact_zero": bool((delta == 0).any()),
            }
        )
    return primary, pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oulad-reference", type=Path, required=True)
    parser.add_argument("--uci-reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    oulad_prob, oulad_budget, oulad_meta = load_oulad(
        args.oulad_reference / "results/c12b/predictions",
        args.oulad_reference / "results/c12b/point_metrics.csv",
    )
    uci_prob, uci_budget, uci_meta = load_uci(
        args.uci_reference / "models_predictions/predictions/oof_predictions.csv.gz",
        args.uci_reference / "statistics/absolute_metrics_long.csv",
    )
    probability = pd.concat([oulad_prob, uci_prob], ignore_index=True, sort=False)
    budget = pd.concat([oulad_budget, uci_budget], ignore_index=True, sort=False)
    selections = {**oulad_meta["selections"], **uci_meta["selections"]}
    probability_contrasts, budget_contrasts = build_contrasts(probability, budget, selections)

    primary_budget, sign_stability = build_summary_tables(budget_contrasts)
    outputs = {
        "probability_metrics.csv": probability,
        "budget_metrics.csv": budget,
        "probability_contrasts_vs_full.csv": probability_contrasts,
        "budget_contrasts_vs_full.csv": budget_contrasts,
        "primary_budget_contrasts.csv": primary_budget,
        "budget_sign_stability.csv": sign_stability,
    }
    for name, frame in outputs.items():
        atomic_csv(frame, args.output / name)

    all_replay = oulad_meta["replay"] + uci_meta["replay"]
    max_replay_error = max(row["max_abs_10pct_replay_error"] for row in all_replay)
    verification = {
        "phase": "C14B",
        "status": "PASS" if max_replay_error <= 1e-12 else "FAIL",
        "models_fitted": 0,
        "budgets": list(BUDGETS),
        "oulad_configurations": int(len(oulad_prob)),
        "uci_configurations": int(len(uci_prob)),
        "probability_metric_rows": int(len(probability)),
        "budget_metric_rows": int(len(budget)),
        "probability_contrast_rows": int(len(probability_contrasts)),
        "budget_contrast_rows": int(len(budget_contrasts)),
        "primary_budget_contrast_rows": int(len(primary_budget)),
        "primary_stage_policy_families": int(len(sign_stability)),
        "primary_families_with_strict_sign_reversal": int(sign_stability["strict_sign_reversal_across_budgets"].sum()),
        "max_abs_10pct_replay_error": max_replay_error,
        "replay_tolerance": 1e-12,
        "inputs": {
            "oulad_point_metrics_sha256": sha256(args.oulad_reference / "results/c12b/point_metrics.csv"),
            "uci_oof_sha256": sha256(args.uci_reference / "models_predictions/predictions/oof_predictions.csv.gz"),
            "uci_absolute_metrics_sha256": sha256(args.uci_reference / "statistics/absolute_metrics_long.csv"),
        },
        "errors": [] if max_replay_error <= 1e-12 else ["10% replay exceeded tolerance"],
    }
    atomic_json(verification, args.output / "C14B_VERIFICATION.json")
    if verification["status"] != "PASS":
        raise SystemExit(2)
    print(json.dumps(verification, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
