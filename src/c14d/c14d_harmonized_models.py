#!/usr/bin/env python3
"""C14D: fit only missing harmonized HGB exclusions with same-run controls."""

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
import sklearn
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold, train_test_split

from c11_common import (
    CONTEXT,
    DIGITAL,
    SENSITIVE,
    apply_platt as apply_platt_oulad,
    fit_platt as fit_platt_oulad,
    make_pipeline as make_oulad_pipeline,
    split_frame,
    stable_tie_keys,
)
from c13_modeling import (
    Config,
    apply_platt as apply_platt_uci,
    deterministic_tie_key,
    fit_selected_model,
)


PROTOCOL_ID = "SecureEWS-C14A/C14D"
TOLERANCE = 1e-12
OULAD_SEED = 42
UCI320_SEED = 20260902
LEAVES = [7, 15, 31]
OULAD_DAYS = [14, 28, 42, 56, 70, 90]
SEX_NEW_DAYS = {28, 56, 70, 90}
OULAD_SES = {"highest_education", "imd_band"}
UCI320_SES = {"Medu", "Fedu", "Mjob", "Fjob"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_csv(frame: pd.DataFrame, path: Path, *, gzip: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    compression = {"method": "gzip", "compresslevel": 9, "mtime": 0} if gzip else None
    frame.to_csv(temporary, index=False, compression=compression)
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_joblib(payload: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    if temporary.exists():
        raise RuntimeError(f"stale temporary model: {temporary}")
    joblib.dump(payload, temporary, compress=3)
    joblib.load(temporary)
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def oulad_features(frame: pd.DataFrame, policy: str) -> list[str]:
    full = CONTEXT + DIGITAL + SENSITIVE
    if policy == "full_control":
        candidates = full
    elif policy == "no_gender":
        candidates = [name for name in full if name != "gender"]
    elif policy == "no_socioeconomic_family":
        candidates = [name for name in full if name not in OULAD_SES]
    else:
        raise ValueError(policy)
    return [name for name in candidates if name in frame.columns]


def oulad_row_id(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["code_module"].astype(str)
        + "|"
        + frame["code_presentation"].astype(str)
        + "|"
        + frame["id_student"].astype(str)
    )


def fit_oulad(
    frame: pd.DataFrame,
    cutoff: int,
    policy: str,
    output: Path,
) -> tuple[pd.DataFrame, dict, list[dict]]:
    train, validation, test = split_frame(frame)
    requested = oulad_features(frame, policy)
    features = [name for name in requested if not train[name].isna().all()]
    categorical = [name for name in features if train[name].dtype == "object"]
    numeric = [name for name in features if name not in categorical]
    candidates = []
    candidate_rows = []
    for leaves in LEAVES:
        model = make_oulad_pipeline(categorical, numeric, leaves)
        model.fit(train[features], train["target_risk"].to_numpy(dtype=int))
        validation_raw = model.predict_proba(validation[features])[:, 1]
        score = float(average_precision_score(validation["target_risk"], validation_raw))
        candidates.append((score, -leaves, leaves, model, validation_raw))
        candidate_rows.append(
            {
                "dataset": "oulad",
                "subject": "all",
                "outcome": "withdrawal_or_fail",
                "stage": f"day{cutoff}",
                "policy": policy,
                "fold": 0,
                "max_leaf_nodes": leaves,
                "validation_average_precision": score,
            }
        )
        print(f"OULAD day{cutoff} {policy} leaves={leaves} AP={score:.9f}", flush=True)
    _, _, selected_leaves, model, validation_raw = max(candidates, key=lambda item: (item[0], item[1]))
    for row in candidate_rows:
        row["selected"] = row["max_leaf_nodes"] == selected_leaves
    calibrator = fit_platt_oulad(validation["target_risk"].to_numpy(dtype=int), validation_raw)
    config_id = f"oulad__day{cutoff}__{policy}__histgb"
    model_path = output / "models" / f"{config_id}.joblib"
    metadata = {
        "protocol_id": PROTOCOL_ID,
        "dataset": "oulad",
        "subject": "all",
        "outcome": "withdrawal_or_fail",
        "stage": f"day{cutoff}",
        "policy": policy,
        "model": "histgb",
        "features": features,
        "categorical": categorical,
        "numeric": numeric,
        "selected_max_leaf_nodes": selected_leaves,
        "seed": OULAD_SEED,
        "splits": {"fit": ["2013B", "2013J"], "calibration": ["2014B"], "test": ["2014J"]},
    }
    atomic_joblib({"pipeline": model, "calibrator": calibrator, "metadata": metadata}, model_path)
    prediction_parts = []
    for split_name, split, raw in [
        ("calibration", validation, validation_raw),
        ("test", test, model.predict_proba(test[features])[:, 1]),
    ]:
        calibrated = apply_platt_oulad(calibrator, raw)
        prediction_parts.append(
            pd.DataFrame(
                {
                    "config_id": config_id,
                    "dataset": "oulad",
                    "subject": "all",
                    "outcome": "withdrawal_or_fail",
                    "stage": f"day{cutoff}",
                    "policy": policy,
                    "model": "histgb",
                    "split": split_name,
                    "row_id": oulad_row_id(split),
                    "cluster_id": split["id_student"].astype(str).to_numpy(),
                    "fold": 0,
                    "budget_group": split["code_module"].astype(str).to_numpy(),
                    "target_risk": split["target_risk"].to_numpy(dtype=int),
                    "tie_key_sha256": stable_tie_keys(split),
                    "probability_raw": raw,
                    "probability_calibrated": calibrated,
                }
            )
        )
    inventory = {
        "config_id": config_id,
        **{key: metadata[key] for key in ["dataset", "subject", "outcome", "stage", "policy", "model"]},
        "selected_max_leaf_nodes": selected_leaves,
        "raw_feature_count": len(features),
        "path": model_path.relative_to(output).as_posix(),
        "size_bytes": model_path.stat().st_size,
        "sha256": sha256(model_path),
    }
    return pd.concat(prediction_parts, ignore_index=True), inventory, candidate_rows


def load_uci320(c13e_root: Path, subject: str) -> pd.DataFrame:
    name = "student-mat.csv" if subject == "mathematics" else "student-por.csv"
    source = pd.read_csv(c13e_root / "c13_work/inputs/uci320_current" / name, sep=";")
    source["row_id"] = np.arange(len(source), dtype=int)
    source["target_risk"] = (source["G3"] < 10).astype(int)
    source["budget_group"] = source["school"].astype(str)
    return source


def uci320_stage_features(source: pd.DataFrame, stage: str, policy: str) -> list[str]:
    base = [name for name in source if name not in ["G1", "G2", "G3", "row_id", "target_risk", "budget_group"]]
    full = base + (["G1"] if stage in {"period1", "period2"} else []) + (["G2"] if stage == "period2" else [])
    if policy == "full_control":
        return full
    if policy == "no_socioeconomic_family":
        return [name for name in full if name not in UCI320_SES]
    raise ValueError(policy)


def make_uci_splits(source: pd.DataFrame) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    y = source["target_risk"].to_numpy(dtype=int)
    outer = StratifiedKFold(n_splits=10, shuffle=True, random_state=UCI320_SEED)
    splits = []
    for fold, (train_pos, test_pos) in enumerate(outer.split(source, y), start=1):
        fit_rel, calibration_rel = train_test_split(
            np.arange(len(train_pos)),
            test_size=0.20,
            stratify=y[train_pos],
            random_state=UCI320_SEED + fold,
        )
        splits.append((train_pos[fit_rel], train_pos[calibration_rel], test_pos))
    return splits


def fit_uci320(
    source: pd.DataFrame,
    subject: str,
    stage: str,
    policy: str,
    splits: list[tuple[np.ndarray, np.ndarray, np.ndarray]],
    output: Path,
) -> tuple[pd.DataFrame, dict, list[dict]]:
    features = uci320_stage_features(source, stage, policy)
    categorical = [name for name in features if source[name].dtype == "object"]
    config = Config(
        "uci320",
        subject,
        "fail_g3_lt_10",
        stage,
        policy,
        "histgb",
        tuple(features),
        tuple(categorical),
        UCI320_SEED,
        "school",
    )
    folds = []
    predictions = []
    selection_rows = []
    for fold, (fit_pos, calibration_pos, test_pos) in enumerate(splits, start=1):
        fit = source.iloc[fit_pos]
        calibration = source.iloc[calibration_pos]
        test = source.iloc[test_pos]
        model, calibrator, selected_leaves, selection = fit_selected_model(fit, calibration, config)
        raw = model.predict_proba(test[features])[:, 1]
        calibrated = apply_platt_uci(calibrator, raw)
        predictions.append(
            pd.DataFrame(
                {
                    "config_id": config.config_id,
                    "dataset": "uci320",
                    "subject": subject,
                    "outcome": "fail_g3_lt_10",
                    "stage": stage,
                    "policy": policy,
                    "model": "histgb",
                    "split": "oof_test",
                    "row_id": test["row_id"].astype(str).to_numpy(),
                    "cluster_id": test["row_id"].astype(str).to_numpy(),
                    "fold": fold,
                    "budget_group": test["budget_group"].astype(str).to_numpy(),
                    "target_risk": test["target_risk"].to_numpy(dtype=int),
                    "tie_key_sha256": [deterministic_tie_key("uci320", int(row_id), UCI320_SEED) for row_id in test["row_id"]],
                    "probability_raw": raw,
                    "probability_calibrated": calibrated,
                }
            )
        )
        folds.append(
            {
                "fold": fold,
                "fit_row_ids": fit["row_id"].to_numpy(dtype=int),
                "calibration_row_ids": calibration["row_id"].to_numpy(dtype=int),
                "test_row_ids": test["row_id"].to_numpy(dtype=int),
                "selected_max_leaf_nodes": selected_leaves,
                "model": model,
                "calibrator": calibrator,
            }
        )
        for row in selection:
            selection_rows.append(
                {
                    "dataset": "uci320",
                    "subject": subject,
                    "outcome": "fail_g3_lt_10",
                    "stage": stage,
                    "policy": policy,
                    "fold": fold,
                    **row,
                }
            )
        print(f"UCI320 {subject} {stage} {policy} fold={fold} selected={selected_leaves}", flush=True)
    model_path = output / "models" / f"{config.config_id}.joblib"
    bundle = {"protocol_id": PROTOCOL_ID, "config": config.as_dict(), "folds": folds}
    atomic_joblib(bundle, model_path)
    inventory = {
        "config_id": config.config_id,
        "dataset": "uci320",
        "subject": subject,
        "outcome": "fail_g3_lt_10",
        "stage": stage,
        "policy": policy,
        "model": "histgb",
        "selected_max_leaf_nodes": "fold_specific",
        "raw_feature_count": len(features),
        "path": model_path.relative_to(output).as_posix(),
        "size_bytes": model_path.stat().st_size,
        "sha256": sha256(model_path),
    }
    return pd.concat(predictions, ignore_index=True), inventory, selection_rows


def standardize_oulad_reference(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "row_id": oulad_row_id(frame),
            "cluster_id": frame["id_student"].astype(str),
            "fold": 0,
            "budget_group": frame["code_module"].astype(str),
            "target_risk": frame["target_risk"].astype(int),
            "tie_key_sha256": frame["tie_key_sha256"].astype(str),
            "probability_calibrated": frame["probability_calibrated"].astype(float),
        }
    )


def standardize_new(frame: pd.DataFrame) -> pd.DataFrame:
    columns = ["row_id", "cluster_id", "fold", "budget_group", "target_risk", "tie_key_sha256", "probability_calibrated"]
    return frame[columns].copy()


def standardize_uci_reference(frame: pd.DataFrame, dataset: str, seed: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "row_id": frame["row_id"].astype(str),
            "cluster_id": frame["row_id"].astype(str),
            "fold": frame["fold"].astype(int),
            "budget_group": frame["budget_group"].astype(str),
            "target_risk": frame["target_risk"].astype(int),
            "tie_key_sha256": [deterministic_tie_key(dataset, int(row_id), seed) for row_id in frame["row_id"]],
            "probability_calibrated": frame["probability_calibrated"].astype(float),
        }
    )


def assemble_pair(
    *,
    dataset: str,
    subject: str,
    outcome: str,
    stage: str,
    block: str,
    source: str,
    full: pd.DataFrame,
    restricted: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    keys = ["row_id", "cluster_id", "fold", "budget_group", "target_risk", "tie_key_sha256"]
    a = full.sort_values("row_id").reset_index(drop=True)
    b = restricted.sort_values("row_id").reset_index(drop=True)
    if len(a) != len(b) or not a[keys].astype(str).equals(b[keys].astype(str)):
        raise RuntimeError(f"pair identity mismatch: {dataset}/{subject}/{outcome}/{stage}/{block}")
    pair_id = "__".join([dataset, subject, outcome, stage, block])
    parts = []
    for side, frame in [("full", a), ("restricted", b)]:
        part = frame.copy()
        part.insert(0, "pair_id", pair_id)
        part.insert(1, "dataset", dataset)
        part.insert(2, "subject", subject)
        part.insert(3, "outcome", outcome)
        part.insert(4, "stage", stage)
        part.insert(5, "block", block)
        part.insert(6, "side", side)
        part.insert(7, "pair_source", source)
        parts.append(part)
    return pd.concat(parts, ignore_index=True), {
        "pair_id": pair_id,
        "dataset": dataset,
        "subject": subject,
        "outcome": outcome,
        "stage": stage,
        "block": block,
        "pair_source": source,
        "n": len(a),
        "positives": int(a["target_risk"].sum()),
    }


def full_replay(
    *, dataset: str, subject: str, outcome: str, stage: str, split: str,
    new: pd.DataFrame, reference: pd.DataFrame,
) -> dict:
    a = new.copy()
    b = reference.copy()
    a["row_id"] = a["row_id"].astype(str)
    b["row_id"] = b["row_id"].astype(str)
    a = a.sort_values("row_id")
    b = b.sort_values("row_id")
    if not np.array_equal(a["row_id"].to_numpy(), b["row_id"].to_numpy()):
        raise RuntimeError(f"full replay identity mismatch: {dataset}/{subject}/{stage}/{split}")
    error = float(np.max(np.abs(a["probability_calibrated"].to_numpy() - b["probability_calibrated"].to_numpy())))
    return {
        "dataset": dataset,
        "subject": subject,
        "outcome": outcome,
        "stage": stage,
        "split": split,
        "n": len(a),
        "max_abs_probability_error": error,
        "tolerance": TOLERANCE,
        "status": "PASS" if error <= TOLERANCE else "FAIL",
    }


def select_budget(frame: pd.DataFrame, budget: float = 0.10) -> np.ndarray:
    chosen = np.zeros(len(frame), dtype=bool)
    working = frame.reset_index(drop=True)
    for group in sorted(working["budget_group"].astype(str).unique()):
        positions = np.flatnonzero(working["budget_group"].astype(str).to_numpy() == group)
        k = max(1, min(len(positions), int(math.ceil(budget * len(positions)))))
        order = np.lexsort((working.loc[positions, "tie_key_sha256"].astype(str), -working.loc[positions, "probability_calibrated"].to_numpy()))
        chosen[positions[order[:k]]] = True
    return chosen


def point_metrics(harmonized: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (pair_id, side), frame in harmonized.groupby(["pair_id", "side"], sort=True):
        y = frame["target_risk"].to_numpy(dtype=int)
        p = frame["probability_calibrated"].to_numpy(dtype=float)
        selected = select_budget(frame)
        precision = float(y[selected].mean())
        rows.append(
            {
                "pair_id": pair_id,
                "side": side,
                "n": len(frame),
                "positives": int(y.sum()),
                "average_precision": float(average_precision_score(y, p)),
                "auroc": float(roc_auc_score(y, p)),
                "brier": float(brier_score_loss(y, p)),
                "alerts_at_10": int(selected.sum()),
                "precision_at_10": precision,
                "recall_at_10": float(y[selected].sum() / y.sum()),
            }
        )
    return pd.DataFrame(rows)


def reference_record(
    pair_id: str, side: str, config_id: str, model_inventory: pd.DataFrame,
    prediction_path: Path,
) -> dict:
    match = model_inventory[model_inventory["config_id"] == config_id]
    if len(match) != 1:
        raise RuntimeError(f"missing reference model inventory row: {config_id}")
    row = match.iloc[0]
    return {
        "pair_id": pair_id,
        "side": side,
        "config_id": config_id,
        "model_path": row["path"],
        "model_sha256": row["sha256"],
        "prediction_path": prediction_path.as_posix(),
        "prediction_sha256": sha256(prediction_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oulad-reference", type=Path, required=True)
    parser.add_argument("--c13e-root", type=Path, required=True)
    parser.add_argument("--c05-archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty output: {output}")
    (output / "models").mkdir(parents=True, exist_ok=True)

    c12_results = args.oulad_reference / "results/c12b"
    c13_results = args.c13e_root / "reference_uci/models_predictions"
    frozen_uci = pd.read_csv(c13_results / "predictions/oof_predictions.csv.gz", low_memory=False)
    frozen_uci = frozen_uci[(frozen_uci["model"] == "histgb")].copy()
    frozen_inventory = pd.read_csv(c13_results / "model_inventory.csv")

    new_predictions = []
    new_inventory = []
    selection_rows = []
    replay_rows = []
    harmonized_parts = []
    pair_rows = []
    reference_rows = []

    oulad_new: dict[tuple[int, str], pd.DataFrame] = {}
    for day in OULAD_DAYS:
        frame = pd.read_csv(args.oulad_reference / f"data/processed/oulad_day{day}.csv.gz")
        policies = ["full_control", "no_socioeconomic_family"] + (["no_gender"] if day in SEX_NEW_DAYS else [])
        for policy in policies:
            predictions, inventory, candidates = fit_oulad(frame, day, policy, output)
            new_predictions.append(predictions)
            new_inventory.append(inventory)
            selection_rows.extend(candidates)
            oulad_new[(day, policy)] = predictions[predictions["split"] == "test"].copy()
        full_new = oulad_new[(day, "full_control")]
        for split_name, reference_prefix in [("calibration", "validation"), ("test", "test")]:
            reference_path = c12_results / "predictions" / f"{reference_prefix}__day{day}__full__standard.csv.gz"
            reference = standardize_oulad_reference(pd.read_csv(reference_path, low_memory=False))
            observed = new_predictions[-len(policies)]
            observed = observed[observed["split"] == split_name]
            replay_rows.append(
                full_replay(
                    dataset="oulad", subject="all", outcome="withdrawal_or_fail", stage=f"day{day}",
                    split=split_name, new=observed, reference=reference,
                )
            )

    for day in OULAD_DAYS:
        if day in SEX_NEW_DAYS:
            full = standardize_new(oulad_new[(day, "full_control")])
            restricted = standardize_new(oulad_new[(day, "no_gender")])
            source = "new_C14D_same_run"
        else:
            full_path = c12_results / "predictions" / f"test__day{day}__full__standard.csv.gz"
            restricted_path = c12_results / "predictions" / f"test__day{day}__loo_no_gender__standard.csv.gz"
            full = standardize_oulad_reference(pd.read_csv(full_path, low_memory=False))
            restricted = standardize_oulad_reference(pd.read_csv(restricted_path, low_memory=False))
            source = "reused_C12_same_run"
            pair_id = f"oulad__all__withdrawal_or_fail__day{day}__sex_gender"
            c12_selected = pd.read_csv(c12_results / "selected_configurations.csv")
            for side, config_id, path in [
                ("full", f"day{day}__full__standard", full_path),
                ("restricted", f"day{day}__loo_no_gender__standard", restricted_path),
            ]:
                match = c12_selected[c12_selected["name"] == config_id]
                if len(match) != 1:
                    raise RuntimeError(f"missing C12 selection row: {config_id}")
                reference_rows.append(
                    {
                        "pair_id": pair_id,
                        "side": side,
                        "config_id": config_id,
                        "model_path": f"models/{config_id}.joblib",
                        "model_sha256": match.iloc[0]["model_sha256"],
                        "prediction_path": path.as_posix(),
                        "prediction_sha256": sha256(path),
                    }
                )
        pair, inventory = assemble_pair(
            dataset="oulad", subject="all", outcome="withdrawal_or_fail", stage=f"day{day}",
            block="sex_gender", source=source, full=full, restricted=restricted,
        )
        harmonized_parts.append(pair); pair_rows.append(inventory)

        pair, inventory = assemble_pair(
            dataset="oulad", subject="all", outcome="withdrawal_or_fail", stage=f"day{day}",
            block="socioeconomic_family", source="new_C14D_same_run",
            full=standardize_new(oulad_new[(day, "full_control")]),
            restricted=standardize_new(oulad_new[(day, "no_socioeconomic_family")]),
        )
        harmonized_parts.append(pair); pair_rows.append(inventory)

    uci_new: dict[tuple[str, str, str], pd.DataFrame] = {}
    for subject in ["mathematics", "portuguese"]:
        source = load_uci320(args.c13e_root, subject)
        splits = make_uci_splits(source)
        for stage in ["baseline", "period1", "period2"]:
            for policy in ["full_control", "no_socioeconomic_family"]:
                predictions, inventory, candidates = fit_uci320(source, subject, stage, policy, splits, output)
                new_predictions.append(predictions)
                new_inventory.append(inventory)
                selection_rows.extend(candidates)
                uci_new[(subject, stage, policy)] = predictions
            frozen = frozen_uci[
                (frozen_uci["dataset"] == "uci320")
                & (frozen_uci["subject"] == subject)
                & (frozen_uci["outcome"] == "fail_g3_lt_10")
                & (frozen_uci["stage"] == stage)
                & (frozen_uci["policy"] == "full")
            ]
            replay_rows.append(
                full_replay(
                    dataset="uci320", subject=subject, outcome="fail_g3_lt_10", stage=stage,
                    split="oof_test", new=uci_new[(subject, stage, "full_control")],
                    reference=standardize_uci_reference(frozen, "uci320", UCI320_SEED),
                )
            )

    for subject in ["mathematics", "portuguese"]:
        for stage in ["baseline", "period1", "period2"]:
            for block, full_policy, restricted_policy, source_name in [
                ("sex_gender", "full", "targeted_no_sex", "reused_C13_same_run"),
                ("socioeconomic_family", "full_control", "no_socioeconomic_family", "new_C14D_same_run"),
            ]:
                if source_name.startswith("reused"):
                    subset = frozen_uci[
                        (frozen_uci["dataset"] == "uci320")
                        & (frozen_uci["subject"] == subject)
                        & (frozen_uci["outcome"] == "fail_g3_lt_10")
                        & (frozen_uci["stage"] == stage)
                    ]
                    full_rows = subset[subset["policy"] == full_policy]
                    restricted_rows = subset[subset["policy"] == restricted_policy]
                    full = standardize_uci_reference(full_rows, "uci320", UCI320_SEED)
                    restricted = standardize_uci_reference(restricted_rows, "uci320", UCI320_SEED)
                else:
                    full = standardize_new(uci_new[(subject, stage, full_policy)])
                    restricted = standardize_new(uci_new[(subject, stage, restricted_policy)])
                pair, inventory = assemble_pair(
                    dataset="uci320", subject=subject, outcome="fail_g3_lt_10", stage=stage,
                    block=block, source=source_name, full=full, restricted=restricted,
                )
                harmonized_parts.append(pair); pair_rows.append(inventory)
                if source_name.startswith("reused"):
                    pair_id = inventory["pair_id"]
                    for side, policy in [("full", full_policy), ("restricted", restricted_policy)]:
                        config_id = f"uci320__{subject}__fail_g3_lt_10__{stage}__{policy}__histgb"
                        reference_rows.append(reference_record(pair_id, side, config_id, frozen_inventory, c13_results / "predictions/oof_predictions.csv.gz"))

    for outcome in ["dropout_vs_graduate", "dropout_vs_all_other"]:
        for stage in ["enrollment", "semester1"]:
            blocks = [("socioeconomic_family", "no_family_financial")]
            if outcome == "dropout_vs_graduate":
                blocks.insert(0, ("sex_gender", "loo__gender"))
            subset = frozen_uci[
                (frozen_uci["dataset"] == "uci697")
                & (frozen_uci["subject"] == "all")
                & (frozen_uci["outcome"] == outcome)
                & (frozen_uci["stage"] == stage)
            ]
            for block, restricted_policy in blocks:
                full_rows = subset[subset["policy"] == "full"]
                restricted_rows = subset[subset["policy"] == restricted_policy]
                pair, inventory = assemble_pair(
                    dataset="uci697", subject="all", outcome=outcome, stage=stage, block=block,
                    source="reused_C13_same_run",
                    full=standardize_uci_reference(full_rows, "uci697", 20260830),
                    restricted=standardize_uci_reference(restricted_rows, "uci697", 20260830),
                )
                harmonized_parts.append(pair); pair_rows.append(inventory)
                pair_id = inventory["pair_id"]
                for side, policy in [("full", "full"), ("restricted", restricted_policy)]:
                    config_id = f"uci697__all__{outcome}__{stage}__{policy}__histgb"
                    reference_rows.append(reference_record(pair_id, side, config_id, frozen_inventory, c13_results / "predictions/oof_predictions.csv.gz"))

    replay = pd.DataFrame(replay_rows)
    if len(replay) != 18 or (replay["status"] != "PASS").any():
        raise RuntimeError(f"full replay gate failed:\n{replay}")
    # Twelve distinct controls are trained; OULAD has calibration and test replay rows.
    if replay.groupby(["dataset", "subject", "stage"]).ngroups != 12:
        raise RuntimeError("unexpected distinct full-control count")

    new_predictions_frame = pd.concat(new_predictions, ignore_index=True)
    inventory_frame = pd.DataFrame(new_inventory).sort_values(["dataset", "subject", "stage", "policy"])
    selection_frame = pd.DataFrame(selection_rows).sort_values(["dataset", "subject", "stage", "policy", "fold", "max_leaf_nodes"])
    harmonized = pd.concat(harmonized_parts, ignore_index=True)
    pairs = pd.DataFrame(pair_rows).sort_values(["dataset", "subject", "outcome", "stage", "block"])
    references = pd.DataFrame(reference_rows).sort_values(["pair_id", "side"])
    points = point_metrics(harmonized)

    if len(inventory_frame) != 28 or inventory_frame["model"].ne("histgb").any():
        raise RuntimeError("new model inventory violates frozen count/model family")
    if len(selection_frame) != 408:
        raise RuntimeError(f"unexpected candidate fit rows: {len(selection_frame)}")
    if len(pairs) != 30 or harmonized["pair_id"].nunique() != 30:
        raise RuntimeError("unexpected harmonized pair count")

    atomic_csv(new_predictions_frame, output / "new_model_predictions.csv.gz", gzip=True)
    atomic_csv(inventory_frame, output / "new_model_inventory.csv")
    atomic_csv(selection_frame, output / "candidate_selection.csv.gz", gzip=True)
    atomic_csv(replay, output / "full_control_replay.csv")
    atomic_csv(harmonized, output / "harmonized_predictions.csv.gz", gzip=True)
    atomic_csv(pairs, output / "pair_inventory.csv")
    atomic_csv(references, output / "reused_reference_inventory.csv")
    atomic_csv(points, output / "point_metrics.csv")

    metadata = {
        "phase": "C14D",
        "protocol_id": PROTOCOL_ID,
        "status": "MODELS_AND_PREDICTIONS_LOCKED_BEFORE_C14E",
        "new_selected_models": len(inventory_frame),
        "new_oulad_selected_models": int((inventory_frame["dataset"] == "oulad").sum()),
        "new_uci320_selected_bundles": int((inventory_frame["dataset"] == "uci320").sum()),
        "new_uci697_models": 0,
        "new_logistic_models": 0,
        "candidate_fit_rows": len(selection_frame),
        "distinct_new_full_controls": 12,
        "full_replay_rows": len(replay),
        "full_replay_max_abs_error": float(replay["max_abs_probability_error"].max()),
        "full_replay_tolerance": TOLERANCE,
        "harmonized_pairs": len(pairs),
        "harmonized_prediction_rows": len(harmonized),
        "xuetangx_c05": {
            "action": "preserved; not extracted; not retrained; not analyzed",
            "archive": args.c05_archive.name,
            "archive_sha256": sha256(args.c05_archive),
        },
        "inputs": {
            "c12_oulad_predictions_sha256": sha256(c12_results / "predictions/test__day42__full__standard.csv.gz"),
            "c13_uci_oof_sha256": sha256(c13_results / "predictions/oof_predictions.csv.gz"),
        },
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
            "platform": platform.platform(),
        },
    }
    atomic_json(output / "metadata.json", metadata)
    print(json.dumps(metadata, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
