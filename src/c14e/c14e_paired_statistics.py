#!/usr/bin/env python3
"""C14E paired bootstrap statistics with frozen family-wise multiplicity."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


BUDGETS = (0.05, 0.10, 0.20, 0.30)
PROBABILITY_METRICS = ("average_precision_difference", "auroc_difference", "brier_difference")
WORKLOAD_METRICS = (
    "precision_difference",
    "recall_difference",
    "alert_jaccard",
    "retained_full_alert_fraction",
)
DIFFERENCE_METRICS = {
    "precision_difference", "recall_difference", "average_precision_difference",
    "auroc_difference", "brier_difference",
}
SEEDS = {"oulad": 42, "uci697": 20260830, "uci320": 20260902}
TOLERANCE = 1e-12


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_csv(frame: pd.DataFrame, path: Path, *, gzip: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    compression = {"method": "gzip", "compresslevel": 9, "mtime": 0} if gzip else None
    frame.to_csv(temporary, index=False, compression=compression)
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def tie_key(dataset: str, row_id: int, seed: int) -> str:
    return hashlib.sha256(f"SecureEWS-C13A|{dataset}|{int(row_id)}|{seed}".encode()).hexdigest()


def stable_seed(text: str) -> int:
    return int.from_bytes(hashlib.sha256(f"SecureEWS-C14E|{text}".encode()).digest()[:4], "big")


def probability_preparation(y: np.ndarray, p: np.ndarray) -> dict:
    order = np.argsort(-p, kind="stable")
    ordered_p = p[order]
    starts = np.r_[0, np.flatnonzero(ordered_p[1:] != ordered_p[:-1]) + 1]
    return {
        "order": order,
        "starts": starts,
        "ordered_y": y[order].astype(np.int8),
        "squared_error": (p - y) ** 2,
    }


def weighted_probability_metrics(weights: np.ndarray, prepared: dict) -> np.ndarray:
    order = prepared["order"]
    ordered_weights = weights[order].astype(np.int64, copy=False)
    total = int(ordered_weights.sum())
    weighted_y = ordered_weights * prepared["ordered_y"]
    positives = int(weighted_y.sum())
    negatives = total - positives
    brier = float(np.dot(weights, prepared["squared_error"]) / total)
    if positives == 0 or negatives == 0:
        return np.asarray([np.nan, np.nan, brier])
    starts = prepared["starts"]
    pos_group = np.add.reduceat(weighted_y, starts)
    total_group = np.add.reduceat(ordered_weights, starts)
    present = total_group > 0
    pos_group = pos_group[present]
    total_group = total_group[present]
    neg_group = total_group - pos_group
    cum_pos = np.cumsum(pos_group)
    cum_count = np.cumsum(total_group)
    ap = float(np.sum((pos_group / positives) * (cum_pos / cum_count)))
    neg_before = np.r_[0, np.cumsum(neg_group)[:-1]]
    neg_below = negatives - neg_before - neg_group
    auc = float(np.sum(pos_group * (neg_below + 0.5 * neg_group)) / (positives * negatives))
    return np.asarray([ap, auc, brier], dtype=float)


def ranking_preparation(p: np.ndarray, groups: np.ndarray, ties: np.ndarray) -> list[np.ndarray]:
    prepared = []
    text = groups.astype(str)
    for group in sorted(np.unique(text)):
        positions = np.flatnonzero(text == group)
        prepared.append(positions[np.lexsort((ties[positions], -p[positions]))])
    return prepared


def weighted_workload_metrics(
    y: np.ndarray,
    weights: np.ndarray,
    rankings: list[np.ndarray],
) -> dict[float, tuple[float, float, np.ndarray]]:
    total_positives = int(np.dot(weights, y))
    selected_by_budget = {budget: np.zeros(len(y), dtype=np.int32) for budget in BUDGETS}
    true_by_budget = {budget: 0 for budget in BUDGETS}
    alerts_by_budget = {budget: 0 for budget in BUDGETS}
    for order in rankings:
        local_weights = weights[order].astype(np.int64, copy=False)
        group_total = int(local_weights.sum())
        if group_total == 0:
            continue
        cumulative = np.cumsum(local_weights)
        for budget in BUDGETS:
            k = max(1, min(group_total, int(math.ceil(budget * group_total))))
            boundary = int(np.searchsorted(cumulative, k, side="left"))
            selected = selected_by_budget[budget]
            if boundary:
                selected[order[:boundary]] = local_weights[:boundary]
                before = int(cumulative[boundary - 1])
            else:
                before = 0
            selected[order[boundary]] = k - before
            alerts_by_budget[budget] += k
            true_by_budget[budget] += int(np.dot(selected[order[: boundary + 1]], y[order[: boundary + 1]]))
    result = {}
    for budget in BUDGETS:
        alerts = alerts_by_budget[budget]
        true_alerts = true_by_budget[budget]
        result[budget] = (
            true_alerts / alerts,
            true_alerts / total_positives,
            selected_by_budget[budget],
        )
    return result


def materialized_metrics(y: np.ndarray, p: np.ndarray, groups: np.ndarray, ties: np.ndarray, indices: np.ndarray) -> tuple[np.ndarray, dict]:
    yy, pp, gg, tt = y[indices], p[indices], groups[indices], ties[indices]
    prep = probability_preparation(yy, pp)
    prob = weighted_probability_metrics(np.ones(len(indices), dtype=np.int32), prep)
    workload = weighted_workload_metrics(yy, np.ones(len(indices), dtype=np.int32), ranking_preparation(pp, gg, tt))
    return prob, workload


def summarize_array(values: np.ndarray, estimate: float, family_size: int, is_difference: bool) -> dict:
    alpha = 0.05
    point_low, point_high = np.quantile(values, [0.025, 0.975])
    family_low, family_high = np.quantile(values, [alpha / (2 * family_size), 1 - alpha / (2 * family_size)])
    if is_difference:
        p_sign = min(
            1.0,
            2 * min(
                (float(np.sum(values <= 0)) + 1) / (len(values) + 1),
                (float(np.sum(values >= 0)) + 1) / (len(values) + 1),
            ),
        )
        p_adjusted = min(1.0, p_sign * family_size)
        excludes = bool(family_low > 0 or family_high < 0)
    else:
        p_sign = np.nan
        p_adjusted = np.nan
        excludes = False
    return {
        "estimate": estimate,
        "pointwise_ci95_low": float(point_low),
        "pointwise_ci95_high": float(point_high),
        "familywise_bonferroni_low": float(family_low),
        "familywise_bonferroni_high": float(family_high),
        "bootstrap_sign_p_two_sided": p_sign,
        "bonferroni_adjusted_sign_p": p_adjusted,
        "familywise_excludes_zero": excludes,
    }


def run_task(task: dict, output_text: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    output = Path(output_text)
    y = task["target"].astype(np.int8)
    groups = task["groups"].astype(str)
    ties = task["ties"].astype(str)
    cluster_codes = task["cluster_codes"].astype(np.int64)
    n_units = int(cluster_codes.max() + 1)
    probabilities = task["probabilities"]
    preparations = {label: probability_preparation(y, p) for label, p in probabilities.items()}
    rankings = {label: ranking_preparation(p, groups, ties) for label, p in probabilities.items()}
    points_prob = {label: weighted_probability_metrics(np.ones(len(y), dtype=np.int32), prep) for label, prep in preparations.items()}
    points_work = {label: weighted_workload_metrics(y, np.ones(len(y), dtype=np.int32), ranking) for label, ranking in rankings.items()}

    draws: dict[str, dict[str, np.ndarray]] = {}
    for contrast in task["contrasts"]:
        reps = contrast["replicates"]
        arrays = {metric: np.empty(reps, dtype=np.float64) for metric in PROBABILITY_METRICS}
        for budget in BUDGETS:
            for metric in WORKLOAD_METRICS:
                arrays[f"{metric}__{budget:.2f}"] = np.empty(reps, dtype=np.float64)
        draws[contrast["contrast_id"]] = arrays

    rng = np.random.default_rng(task["bootstrap_seed"])
    max_reps = max(item["replicates"] for item in task["contrasts"])
    completed = 0
    first_multiplicity_sha256 = None
    while completed < max_reps:
        sampled = rng.integers(0, n_units, size=n_units)
        unit_counts = np.bincount(sampled, minlength=n_units).astype(np.int32)
        weights = unit_counts[cluster_codes]
        positives = int(np.dot(weights, y))
        if positives == 0 or positives == int(weights.sum()):
            continue
        if completed == 0:
            first_multiplicity_sha256 = hashlib.sha256(unit_counts.astype("<i4").tobytes()).hexdigest()
        active = [item for item in task["contrasts"] if completed < item["replicates"]]
        labels = {item["full_label"] for item in active} | {item["restricted_label"] for item in active}
        current_prob = {label: weighted_probability_metrics(weights, preparations[label]) for label in labels}
        current_work = {label: weighted_workload_metrics(y, weights, rankings[label]) for label in labels}
        for contrast in active:
            arrays = draws[contrast["contrast_id"]]
            full_label = contrast["full_label"]
            restricted_label = contrast["restricted_label"]
            delta = current_prob[restricted_label] - current_prob[full_label]
            for index, metric in enumerate(PROBABILITY_METRICS):
                arrays[metric][completed] = delta[index]
            for budget in BUDGETS:
                full_precision, full_recall, full_selected = current_work[full_label][budget]
                restricted_precision, restricted_recall, restricted_selected = current_work[restricted_label][budget]
                intersection = int(np.minimum(full_selected, restricted_selected).sum())
                union = int(np.maximum(full_selected, restricted_selected).sum())
                arrays[f"precision_difference__{budget:.2f}"][completed] = restricted_precision - full_precision
                arrays[f"recall_difference__{budget:.2f}"][completed] = restricted_recall - full_recall
                arrays[f"alert_jaccard__{budget:.2f}"][completed] = intersection / union
                arrays[f"retained_full_alert_fraction__{budget:.2f}"][completed] = intersection / int(full_selected.sum())
        completed += 1

    task_slug = hashlib.sha256(task["task_id"].encode()).hexdigest()[:20]
    draw_path = output / "draws" / f"task_{task_slug}.npz"
    draw_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = draw_path.with_suffix(".npz.tmp")
    arrays_for_file = {}
    contrast_index = {}
    for number, contrast in enumerate(task["contrasts"]):
        prefix = f"c{number:03d}"
        contrast_index[contrast["contrast_id"]] = prefix
        for metric, values in draws[contrast["contrast_id"]].items():
            arrays_for_file[f"{prefix}__{metric}"] = values
    with temporary.open("wb") as handle:
        np.savez_compressed(handle, **arrays_for_file)
        handle.flush(); os.fsync(handle.fileno())
    with np.load(temporary) as loaded:
        if set(loaded.files) != set(arrays_for_file):
            raise RuntimeError("NPZ publication verification failed")
    os.replace(temporary, draw_path)

    rows = []
    inventory_rows = []
    for contrast in task["contrasts"]:
        full_label = contrast["full_label"]
        restricted_label = contrast["restricted_label"]
        prefix = contrast_index[contrast["contrast_id"]]
        common = {key: contrast[key] for key in [
            "analysis_source", "dataset", "subject", "outcome", "stage", "model", "grid",
            "contrast_name", "contrast_id", "family_id", "tier", "replicates", "family_stage_count",
        ]}
        prob_delta = points_prob[restricted_label] - points_prob[full_label]
        for index, metric in enumerate(PROBABILITY_METRICS):
            draw_key = f"{prefix}__{metric}"
            rows.append(
                {
                    **common,
                    "metric": metric,
                    "budget_fraction": np.nan,
                    "family_size": contrast["family_stage_count"],
                    "draw_file": draw_path.relative_to(output).as_posix(),
                    "draw_key": draw_key,
                    **summarize_array(draws[contrast["contrast_id"]][metric], float(prob_delta[index]), contrast["family_stage_count"], True),
                }
            )
        for budget in BUDGETS:
            fp, fr, fs = points_work[full_label][budget]
            rp, rr, rs = points_work[restricted_label][budget]
            intersection = int(np.minimum(fs, rs).sum())
            union = int(np.maximum(fs, rs).sum())
            estimates = {
                "precision_difference": rp - fp,
                "recall_difference": rr - fr,
                "alert_jaccard": intersection / union,
                "retained_full_alert_fraction": intersection / int(fs.sum()),
            }
            family_size = contrast["family_stage_count"] * len(BUDGETS)
            for metric in WORKLOAD_METRICS:
                key = f"{metric}__{budget:.2f}"
                draw_key = f"{prefix}__{key}"
                rows.append(
                    {
                        **common,
                        "metric": metric,
                        "budget_fraction": budget,
                        "family_size": family_size,
                        "draw_file": draw_path.relative_to(output).as_posix(),
                        "draw_key": draw_key,
                        **summarize_array(draws[contrast["contrast_id"]][key], float(estimates[metric]), family_size, metric in DIFFERENCE_METRICS),
                    }
                )
        inventory_rows.append(
            {
                **common,
                "task_id": task["task_id"],
                "resampling_stream": task["resampling_stream"],
                "draw_file": draw_path.relative_to(output).as_posix(),
                "draw_prefix": prefix,
                "draw_file_sha256": "PENDING",
                "bootstrap_unit": task["bootstrap_unit"],
                "bootstrap_units": n_units,
                "observations": len(y),
                "first_multiplicity_sha256": first_multiplicity_sha256,
            }
        )
    file_hash = sha256(draw_path)
    for row in inventory_rows:
        row["draw_file_sha256"] = file_hash
    return pd.DataFrame(rows), pd.DataFrame(inventory_rows)


def load_oulad_config(reference: Path, config_id: str) -> pd.DataFrame:
    frame = pd.read_csv(reference / "results/c12b/predictions" / f"test__{config_id}.csv.gz", dtype={"imd_band": str}, low_memory=False)
    frame["row_id"] = frame["code_module"].astype(str) + "|" + frame["code_presentation"].astype(str) + "|" + frame["id_student"].astype(str)
    frame["cluster_id"] = frame["id_student"].astype(str)
    frame["budget_group"] = frame["code_module"].astype(str)
    return frame[["row_id", "cluster_id", "target_risk", "budget_group", "tie_key_sha256", "probability_calibrated"]].sort_values("row_id").reset_index(drop=True)


def load_uci_config(frozen: pd.DataFrame, config_id: str) -> pd.DataFrame:
    frame = frozen[frozen["config_id"] == config_id].copy().sort_values("row_id").reset_index(drop=True)
    if frame.empty:
        raise RuntimeError(f"missing UCI config {config_id}")
    dataset = str(frame.iloc[0]["dataset"])
    seed = SEEDS[dataset]
    frame["row_id"] = frame["row_id"].astype(str)
    frame["cluster_id"] = frame["row_id"]
    frame["tie_key_sha256"] = [tie_key(dataset, int(row_id), seed) for row_id in frame["row_id"]]
    return frame[["row_id", "cluster_id", "target_risk", "budget_group", "tie_key_sha256", "probability_calibrated"]]


def task_from_aligned(
    *, task_id: str, keys: dict, identity: pd.DataFrame, probabilities: dict[str, np.ndarray], contrasts: list[dict],
) -> dict:
    clusters = identity["cluster_id"].astype(str).to_numpy()
    _, cluster_codes = np.unique(clusters, return_inverse=True)
    resampling_stream = "|".join(
        [str(keys["dataset"]), str(keys["subject"]), str(keys["outcome"]), str(keys["stage"])]
    )
    return {
        "task_id": task_id,
        "bootstrap_seed": stable_seed(resampling_stream),
        "resampling_stream": resampling_stream,
        "bootstrap_unit": "id_student_cluster" if keys["dataset"] == "oulad" else "row",
        "target": identity["target_risk"].to_numpy(dtype=np.int8),
        "groups": identity["budget_group"].astype(str).to_numpy(),
        "ties": identity["tie_key_sha256"].astype(str).to_numpy(),
        "cluster_codes": cluster_codes,
        "probabilities": probabilities,
        "contrasts": contrasts,
    }


def build_c14b_tasks(c14b: Path, oulad_reference: Path, c13e: Path) -> tuple[list[dict], pd.DataFrame, pd.DataFrame]:
    budget = pd.read_csv(c14b / "budget_contrasts_vs_full.csv")
    probability = pd.read_csv(c14b / "probability_contrasts_vs_full.csv")
    primary = pd.read_csv(c14b / "primary_budget_contrasts.csv")
    contrast_keys = ["dataset", "subject", "outcome", "stage", "model", "grid", "policy", "config_id", "full_config_id"]
    unique = budget[contrast_keys].drop_duplicates()
    primary_set = set(map(tuple, primary[contrast_keys].drop_duplicates().to_numpy()))
    unique["tier"] = ["primary" if tuple(row) in primary_set else "sensitivity" for row in unique[contrast_keys].to_numpy()]
    frozen_uci = pd.read_csv(c13e / "reference_uci/models_predictions/predictions/oof_predictions.csv.gz", dtype={"budget_group": str}, low_memory=False)
    cache: dict[str, pd.DataFrame] = {}
    tasks = []
    base_keys = ["dataset", "subject", "outcome", "stage", "model", "grid"]
    for base, contrasts_frame in unique.groupby(base_keys, sort=True, dropna=False):
        attrs = dict(zip(base_keys, map(str, base)))
        task_id = "c14b|" + "|".join(map(str, base))
        probabilities = {}
        identity = None
        contrasts = []
        for row in contrasts_frame.itertuples(index=False):
            for label, config_id in [("full", row.full_config_id), (str(row.policy), row.config_id)]:
                if label in probabilities:
                    continue
                if config_id not in cache:
                    cache[config_id] = load_oulad_config(oulad_reference, config_id) if row.dataset == "oulad" else load_uci_config(frozen_uci, config_id)
                frame = cache[config_id]
                current_identity = frame[["row_id", "cluster_id", "target_risk", "budget_group", "tie_key_sha256"]].astype(str)
                if identity is None:
                    identity = frame[["row_id", "cluster_id", "target_risk", "budget_group", "tie_key_sha256"]].copy()
                elif not current_identity.equals(identity.astype(str)):
                    raise RuntimeError(f"C14B alignment failed: {task_id}/{config_id}")
                probabilities[label] = frame["probability_calibrated"].to_numpy(dtype=float)
            family_id = "c14b|" + "|".join([str(row.dataset), str(row.subject), str(row.outcome), str(row.model), str(row.grid), str(row.policy)])
            contrasts.append(
                {
                    "analysis_source": "C14B_frozen",
                    **attrs,
                    "contrast_name": str(row.policy),
                    "contrast_id": f"c14b__{row.config_id}__minus__{row.full_config_id}",
                    "family_id": family_id,
                    "tier": str(row.tier),
                    "replicates": 5000 if row.tier == "primary" else 2000,
                    "full_label": "full",
                    "restricted_label": str(row.policy),
                    "family_stage_count": 0,
                }
            )
        assert identity is not None
        tasks.append(task_from_aligned(task_id=task_id, keys=attrs, identity=identity, probabilities=probabilities, contrasts=contrasts))
    return tasks, budget, probability


def build_c14d_tasks(c14d: Path) -> list[dict]:
    frozen = pd.read_csv(c14d / "harmonized_predictions.csv.gz", low_memory=False)
    tasks = []
    base_keys = ["dataset", "subject", "outcome", "stage"]
    for base, stage_frame in frozen.groupby(base_keys, sort=True):
        attrs0 = dict(zip(base_keys, map(str, base)))
        attrs = {**attrs0, "model": "histgb", "grid": "c14d_selected"}
        task_id = "c14d|" + "|".join(map(str, base))
        probabilities = {}
        contrasts = []
        identity = None
        for pair_id, pair in stage_frame.groupby("pair_id", sort=True):
            block = str(pair.iloc[0]["block"])
            for side in ["full", "restricted"]:
                label = f"{block}__{side}"
                frame = pair[pair["side"] == side].sort_values("row_id").reset_index(drop=True)
                current = frame[["row_id", "cluster_id", "target_risk", "budget_group", "tie_key_sha256"]].copy()
                current["row_id"] = current["row_id"].astype(str)
                current["cluster_id"] = current["cluster_id"].astype(str)
                if identity is None:
                    identity = current
                elif not current.astype(str).equals(identity.astype(str)):
                    raise RuntimeError(f"C14D alignment failed: {task_id}/{pair_id}/{side}")
                probabilities[label] = frame["probability_calibrated"].to_numpy(dtype=float)
            family_id = "c14d|" + "|".join([attrs0["dataset"], attrs0["subject"], attrs0["outcome"], block])
            contrasts.append(
                {
                    "analysis_source": "C14D_harmonized",
                    **attrs,
                    "contrast_name": block,
                    "contrast_id": f"c14d__{pair_id}",
                    "family_id": family_id,
                    "tier": "primary",
                    "replicates": 5000,
                    "full_label": f"{block}__full",
                    "restricted_label": f"{block}__restricted",
                    "family_stage_count": 0,
                }
            )
        assert identity is not None
        tasks.append(task_from_aligned(task_id=task_id, keys=attrs, identity=identity, probabilities=probabilities, contrasts=contrasts))
    return tasks


def assign_family_sizes(tasks: list[dict]) -> None:
    stages: dict[str, set[str]] = {}
    for task in tasks:
        for contrast in task["contrasts"]:
            stages.setdefault(contrast["family_id"], set()).add(contrast["stage"])
    for task in tasks:
        for contrast in task["contrasts"]:
            contrast["family_stage_count"] = len(stages[contrast["family_id"]])


def c14b_point_replay(summary: pd.DataFrame, budget: pd.DataFrame, probability: pd.DataFrame) -> tuple[float, int]:
    observed = summary[summary["analysis_source"] == "C14B_frozen"]
    errors = []
    checks = 0
    workload_map = {
        "precision_difference": "precision_difference",
        "recall_difference": "recall_difference",
        "alert_jaccard": "alert_jaccard_vs_full",
        "retained_full_alert_fraction": "retained_full_alert_fraction",
    }
    for row in observed[observed["metric"].isin(WORKLOAD_METRICS)].itertuples(index=False):
        reference = budget[
            (budget["config_id"].astype(str).map(lambda value: f"c14b__{value}__minus__") .str.len() > 0)
            & (budget["dataset"] == row.dataset)
            & (budget["subject"].astype(str) == row.subject)
            & (budget["outcome"] == row.outcome)
            & (budget["stage"] == row.stage)
            & (budget["model"] == row.model)
            & (budget["grid"] == row.grid)
            & (budget["policy"] == row.contrast_name)
            & np.isclose(budget["budget_fraction"], row.budget_fraction)
        ]
        if len(reference) != 1:
            raise RuntimeError(f"C14B workload replay lookup failed: {row.contrast_id}/{row.metric}")
        errors.append(abs(row.estimate - float(reference.iloc[0][workload_map[row.metric]]))); checks += 1
    probability_map = {"average_precision_difference": "average_precision", "auroc_difference": "auroc", "brier_difference": "brier"}
    for row in observed[observed["metric"].isin(PROBABILITY_METRICS)].itertuples(index=False):
        reference = probability[
            (probability["dataset"] == row.dataset)
            & (probability["subject"].astype(str) == row.subject)
            & (probability["outcome"] == row.outcome)
            & (probability["stage"] == row.stage)
            & (probability["model"] == row.model)
            & (probability["grid"] == row.grid)
            & (probability["policy"] == row.contrast_name)
            & (probability["metric"] == probability_map[row.metric])
        ]
        if len(reference) != 1:
            raise RuntimeError(f"C14B probability replay lookup failed: {row.contrast_id}/{row.metric}")
        errors.append(abs(row.estimate - float(reference.iloc[0]["difference"]))); checks += 1
    return max(errors), checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--c14b", type=Path, required=True)
    parser.add_argument("--c14d", type=Path, required=True)
    parser.add_argument("--oulad-reference", type=Path, required=True)
    parser.add_argument("--c13e-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=8)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty output: {output}")
    output.mkdir(parents=True, exist_ok=True)

    c14b_tasks, frozen_budget, frozen_probability = build_c14b_tasks(args.c14b, args.oulad_reference, args.c13e_root)
    c14d_tasks = build_c14d_tasks(args.c14d)
    tasks = c14b_tasks + c14d_tasks
    assign_family_sizes(tasks)
    contrast_count = sum(len(task["contrasts"]) for task in tasks)
    print(f"C14E tasks={len(tasks)} contrasts={contrast_count} jobs={args.jobs}", flush=True)
    results = joblib.Parallel(n_jobs=args.jobs, backend="loky", batch_size=1, verbose=10)(
        joblib.delayed(run_task)(task, str(output)) for task in tasks
    )
    summary = pd.concat([result[0] for result in results], ignore_index=True)
    inventory = pd.concat([result[1] for result in results], ignore_index=True)
    summary = summary.sort_values(["analysis_source", "dataset", "subject", "outcome", "contrast_name", "stage", "metric", "budget_fraction"], na_position="first")
    inventory = inventory.sort_values(["analysis_source", "dataset", "subject", "outcome", "contrast_name", "stage"])
    replay_error, replay_checks = c14b_point_replay(summary, frozen_budget, frozen_probability)
    if replay_error > TOLERANCE:
        raise RuntimeError(f"C14B point replay failed: {replay_error}")

    primary_precision = summary[
        (summary["tier"] == "primary") & (summary["metric"] == "precision_difference")
    ].copy()
    family_summary = []
    for family_id, frame in primary_precision.groupby("family_id", sort=True):
        family_summary.append(
            {
                "family_id": family_id,
                "analysis_source": frame.iloc[0]["analysis_source"],
                "dataset": frame.iloc[0]["dataset"],
                "subject": frame.iloc[0]["subject"],
                "outcome": frame.iloc[0]["outcome"],
                "contrast_name": frame.iloc[0]["contrast_name"],
                "cells": len(frame),
                "negative_estimates": int((frame["estimate"] < 0).sum()),
                "zero_estimates": int((frame["estimate"] == 0).sum()),
                "positive_estimates": int((frame["estimate"] > 0).sum()),
                "familywise_negative_cells": int((frame["familywise_bonferroni_high"] < 0).sum()),
                "familywise_positive_cells": int((frame["familywise_bonferroni_low"] > 0).sum()),
                "minimum_estimate": float(frame["estimate"].min()),
                "maximum_estimate": float(frame["estimate"].max()),
            }
        )
    family_summary_frame = pd.DataFrame(family_summary)

    atomic_csv(summary, output / "paired_statistics.csv.gz", gzip=True)
    atomic_csv(inventory, output / "bootstrap_draw_inventory.csv")
    atomic_csv(primary_precision, output / "primary_precision_familywise.csv")
    atomic_csv(family_summary_frame, output / "primary_family_summary.csv")
    metadata = {
        "phase": "C14E",
        "protocol_id": "SecureEWS-C14A/C14E",
        "status": "PAIRED_STATISTICS_LOCKED_BEFORE_C14F",
        "models_refitted": False,
        "bootstrap_tasks": len(tasks),
        "contrasts": contrast_count,
        "paired_statistic_rows": len(summary),
        "primary_contrasts": int((inventory["tier"] == "primary").sum()),
        "sensitivity_contrasts": int((inventory["tier"] == "sensitivity").sum()),
        "primary_replicates": 5000,
        "sensitivity_replicates": 2000,
        "bootstrap_units": {"oulad": "id_student cluster", "uci697": "row", "uci320": "row"},
        "paired_multiplicities": True,
        "resampling_stream_contract": "one deterministic RNG stream per dataset x subject/outcome x stage, shared across C14B and C14D when observation identities coincide",
        "multiplicity": "Bonferroni percentile and Bonferroni-adjusted bootstrap sign proportions within dataset x subject/outcome x named policy/block x metric across frozen stages x four budgets; probability metrics omit budgets",
        "c14b_point_replay_checks": replay_checks,
        "c14b_point_replay_max_abs_error": replay_error,
        "input_sha256": {
            "c14b_budget_contrasts": sha256(args.c14b / "budget_contrasts_vs_full.csv"),
            "c14b_probability_contrasts": sha256(args.c14b / "probability_contrasts_vs_full.csv"),
            "c14d_harmonized_predictions": sha256(args.c14d / "harmonized_predictions.csv.gz"),
        },
        "environment": {
            "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
            "joblib": joblib.__version__, "platform": platform.platform(),
        },
    }
    atomic_json(output / "metadata.json", metadata)
    print(json.dumps(metadata, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
