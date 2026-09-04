#!/usr/bin/env python3
"""Independent replay and scope verification for SecureEWS C14D."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


TOLERANCE = 1e-12
OULAD_SES = {"highest_education", "imd_band"}
UCI320_SES = {"Medu", "Fedu", "Mjob", "Fjob"}
FORBIDDEN = {"final_result", "target_risk", "Target", "G3", "row_id", "id_student", "code_presentation"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def calibrated(bundle: dict, frame: pd.DataFrame, features: list[str]) -> np.ndarray:
    raw = bundle["pipeline"].predict_proba(frame[features])[:, 1]
    clipped = np.clip(raw, 1e-6, 1 - 1e-6)
    logits = np.log(clipped / (1 - clipped))
    return bundle["calibrator"].predict_proba(logits.reshape(-1, 1))[:, 1]


def oulad_id(frame: pd.DataFrame) -> pd.Series:
    return frame["code_module"].astype(str) + "|" + frame["code_presentation"].astype(str) + "|" + frame["id_student"].astype(str)


def uci_source(c13e: Path, subject: str) -> pd.DataFrame:
    name = "student-mat.csv" if subject == "mathematics" else "student-por.csv"
    source = pd.read_csv(c13e / "c13_work/inputs/uci320_current" / name, sep=";")
    source["row_id"] = np.arange(len(source), dtype=int)
    return source


def atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--oulad-reference", type=Path, required=True)
    parser.add_argument("--c13e-root", type=Path, required=True)
    parser.add_argument("--c05-archive", type=Path, required=True)
    parser.add_argument("--write-json", type=Path)
    args = parser.parse_args()
    result = args.result_dir.resolve()
    errors: list[str] = []

    for name in ["new_model_predictions.csv.gz", "harmonized_predictions.csv.gz", "candidate_selection.csv.gz"]:
        try:
            with gzip.open(result / name, "rb") as handle:
                while handle.read(1024 * 1024):
                    pass
        except Exception as exc:
            errors.append(f"gzip integrity failed for {name}: {exc}")
    if list(result.rglob("*.tmp")):
        errors.append("temporary files remain inside result directory")

    inventory = pd.read_csv(result / "new_model_inventory.csv")
    predictions = pd.read_csv(result / "new_model_predictions.csv.gz", low_memory=False)
    selections = pd.read_csv(result / "candidate_selection.csv.gz")
    replay_report = pd.read_csv(result / "full_control_replay.csv")
    harmonized = pd.read_csv(result / "harmonized_predictions.csv.gz", low_memory=False)
    pairs = pd.read_csv(result / "pair_inventory.csv")
    references = pd.read_csv(result / "reused_reference_inventory.csv")
    points = pd.read_csv(result / "point_metrics.csv")
    metadata = json.loads((result / "metadata.json").read_text(encoding="utf-8"))

    if len(inventory) != 28 or inventory["config_id"].nunique() != 28:
        errors.append("new model inventory is not 28 unique configurations")
    if (inventory["model"] != "histgb").any() or (inventory["dataset"] == "uci697").any():
        errors.append("new model scope contains a prohibited family or UCI697 refit")
    if int((inventory["dataset"] == "oulad").sum()) != 16 or int((inventory["dataset"] == "uci320").sum()) != 12:
        errors.append("new model dataset counts mismatch")
    if len(selections) != 408 or int(selections["selected"].sum()) != 136:
        errors.append("candidate-selection count mismatch")
    if len(replay_report) != 18 or (replay_report["status"] != "PASS").any():
        errors.append("recorded full-control replay gate failed")
    if len(pairs) != 30 or harmonized["pair_id"].nunique() != 30 or len(harmonized) != 274004:
        errors.append("harmonized pair or prediction count mismatch")
    if len(references) != 28 or len(points) != 60:
        errors.append("reference inventory or point-metric count mismatch")
    if not np.isfinite(harmonized["probability_calibrated"]).all() or not harmonized["probability_calibrated"].between(0, 1).all():
        errors.append("invalid harmonized probabilities")

    pair_identity_errors = 0
    identity = ["row_id", "cluster_id", "fold", "budget_group", "target_risk", "tie_key_sha256"]
    for pair_id, frame in harmonized.groupby("pair_id", sort=False):
        if set(frame["side"]) != {"full", "restricted"}:
            pair_identity_errors += 1
            continue
        full = frame[frame["side"] == "full"].sort_values("row_id").reset_index(drop=True)
        restricted = frame[frame["side"] == "restricted"].sort_values("row_id").reset_index(drop=True)
        if len(full) != len(restricted) or not full[identity].astype(str).equals(restricted[identity].astype(str)):
            pair_identity_errors += 1
    if pair_identity_errors:
        errors.append(f"paired identity errors: {pair_identity_errors}")

    max_model_replay = 0.0
    feature_errors = 0
    uci_cache: dict[str, pd.DataFrame] = {}
    for row in inventory.itertuples(index=False):
        bundle = joblib.load(result / row.path)
        observed = predictions[(predictions["config_id"] == row.config_id) & (predictions["split"].isin(["test", "oof_test"]))].copy()
        if row.dataset == "oulad":
            meta = bundle["metadata"]
            features = list(meta["features"])
            day = int(str(row.stage).removeprefix("day"))
            source = pd.read_csv(args.oulad_reference / f"data/processed/oulad_day{day}.csv.gz")
            test = source[source["code_presentation"] == "2014J"].copy()
            probability = calibrated(bundle, test, features)
            replay = pd.DataFrame({"row_id": oulad_id(test), "probability": probability}).sort_values("row_id")
        else:
            features = list(bundle["config"]["features"])
            if row.subject not in uci_cache:
                uci_cache[row.subject] = uci_source(args.c13e_root, row.subject)
            indexed = uci_cache[row.subject].set_index("row_id")
            pieces = []
            for fold in bundle["folds"]:
                row_ids = np.asarray(fold["test_row_ids"], dtype=int)
                test = indexed.loc[row_ids].reset_index()
                raw = fold["model"].predict_proba(test[features])[:, 1]
                clipped = np.clip(raw, 1e-6, 1 - 1e-6)
                logits = np.log(clipped / (1 - clipped))
                probability = fold["calibrator"].predict_proba(logits.reshape(-1, 1))[:, 1]
                pieces.append(pd.DataFrame({"row_id": row_ids.astype(str), "probability": probability}))
            replay = pd.concat(pieces, ignore_index=True).sort_values("row_id")
        observed["row_id"] = observed["row_id"].astype(str)
        observed = observed.sort_values("row_id")
        if not np.array_equal(replay["row_id"].to_numpy(), observed["row_id"].to_numpy()):
            errors.append(f"model replay identity mismatch: {row.config_id}")
            continue
        max_model_replay = max(max_model_replay, float(np.max(np.abs(replay["probability"].to_numpy() - observed["probability_calibrated"].to_numpy()))))
        if FORBIDDEN.intersection(features):
            feature_errors += 1
        if row.policy == "no_gender" and "gender" in features:
            feature_errors += 1
        if row.policy == "no_socioeconomic_family":
            block = OULAD_SES if row.dataset == "oulad" else UCI320_SES
            if block.intersection(features):
                feature_errors += 1
    if max_model_replay > TOLERANCE:
        errors.append("new model prediction replay tolerance exceeded")
    if feature_errors:
        errors.append(f"feature exclusion errors: {feature_errors}")

    max_full_replay = 0.0
    for day in [14, 28, 42, 56, 70, 90]:
        observed_all = predictions[(predictions["dataset"] == "oulad") & (predictions["stage"] == f"day{day}") & (predictions["policy"] == "full_control")]
        for split, prefix in [("calibration", "validation"), ("test", "test")]:
            observed = observed_all[observed_all["split"] == split].copy()
            frozen = pd.read_csv(args.oulad_reference / f"results/c12b/predictions/{prefix}__day{day}__full__standard.csv.gz", low_memory=False)
            observed["row_id"] = observed["row_id"].astype(str)
            frozen["row_id"] = oulad_id(frozen)
            observed = observed.sort_values("row_id")
            frozen = frozen.sort_values("row_id")
            max_full_replay = max(max_full_replay, float(np.max(np.abs(observed["probability_calibrated"].to_numpy() - frozen["probability_calibrated"].to_numpy()))))
    frozen_uci = pd.read_csv(args.c13e_root / "reference_uci/models_predictions/predictions/oof_predictions.csv.gz", low_memory=False)
    for subject in ["mathematics", "portuguese"]:
        for stage in ["baseline", "period1", "period2"]:
            observed = predictions[(predictions["dataset"] == "uci320") & (predictions["subject"] == subject) & (predictions["stage"] == stage) & (predictions["policy"] == "full_control")].copy()
            frozen = frozen_uci[(frozen_uci["dataset"] == "uci320") & (frozen_uci["subject"] == subject) & (frozen_uci["stage"] == stage) & (frozen_uci["policy"] == "full") & (frozen_uci["model"] == "histgb")].copy()
            observed["row_id"] = observed["row_id"].astype(int)
            observed = observed.sort_values("row_id")
            frozen = frozen.sort_values("row_id")
            max_full_replay = max(max_full_replay, float(np.max(np.abs(observed["probability_calibrated"].to_numpy() - frozen["probability_calibrated"].to_numpy()))))
    if max_full_replay > TOLERANCE:
        errors.append("independent full-control replay tolerance exceeded")

    c05_hash = sha256(args.c05_archive)
    if metadata["xuetangx_c05"]["archive_sha256"] != c05_hash:
        errors.append("C05 archive provenance hash mismatch")
    if any("xuetang" in str(path).lower() for path in (result / "models").glob("*")):
        errors.append("unexpected XuetangX model artifact")

    report = {
        "phase": "C14D",
        "status": "PASS" if not errors else "FAIL",
        "checks": 16,
        "new_models_replayed": len(inventory),
        "new_model_prediction_rows": len(predictions),
        "harmonized_pairs": len(pairs),
        "harmonized_prediction_rows": len(harmonized),
        "candidate_fit_rows": len(selections),
        "pair_identity_errors": pair_identity_errors,
        "feature_exclusion_errors": feature_errors,
        "max_abs_new_model_replay_error": max_model_replay,
        "max_abs_full_control_replay_error": max_full_replay,
        "replay_tolerance": TOLERANCE,
        "xuetangx_c05_sha256": c05_hash,
        "xuetangx_c05_retrained": False,
        "errors": errors,
    }
    if args.write_json:
        atomic_json(args.write_json, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
