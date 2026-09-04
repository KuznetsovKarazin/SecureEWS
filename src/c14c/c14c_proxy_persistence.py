#!/usr/bin/env python3
"""SecureEWS C14C: held-out predictability of directly excluded fields."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, balanced_accuracy_score, brier_score_loss, roc_auc_score, roc_curve
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


DAYS = (14, 28, 42, 56, 70, 90)
PROXY_MODELS = ("logistic", "histgb")
UCI697_CATEGORICAL = {
    "Marital status", "Application mode", "Course", "Daytime/evening attendance",
    "Previous qualification", "Nacionality", "Mother's qualification",
    "Father's qualification", "Mother's occupation", "Father's occupation",
    "Displaced", "Educational special needs", "Debtor", "Tuition fees up to date",
    "Gender", "Scholarship holder", "International",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_csv(frame: pd.DataFrame, path: Path, compression: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, compression=compression)
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    if temporary.exists():
        raise RuntimeError(f"temporary CSV remained after atomic publish: {temporary}")


def atomic_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def make_pipeline(model_name: str, frame: pd.DataFrame, features: list[str], seed: int) -> Pipeline:
    categorical = [feature for feature in features if frame[feature].dtype == "object" or str(frame[feature].dtype).startswith("category")]
    numeric = [feature for feature in features if feature not in categorical]
    transformers = []
    if categorical:
        transformers.append(
            (
                "categorical",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                    ]
                ),
                categorical,
            )
        )
    if numeric:
        transformers.append(
            (
                "numeric",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
                        ("scale", StandardScaler()),
                    ]
                ),
                numeric,
            )
        )
    if model_name == "logistic":
        estimator = LogisticRegression(C=1.0, max_iter=2000, random_state=seed)
    elif model_name == "histgb":
        estimator = HistGradientBoostingClassifier(
            learning_rate=0.05,
            max_iter=250,
            max_leaf_nodes=15,
            min_samples_leaf=30,
            l2_regularization=1.0,
            early_stopping=False,
            random_state=seed,
        )
    else:
        raise ValueError(model_name)
    return Pipeline([("preprocess", ColumnTransformer(transformers, remainder="drop")), ("model", estimator)])


def select_threshold(y: np.ndarray, p: np.ndarray) -> float:
    fpr, tpr, thresholds = roc_curve(y, p)
    finite = np.isfinite(thresholds)
    if not finite.any():
        return 0.5
    scores = tpr[finite] - fpr[finite]
    candidates = thresholds[finite][np.isclose(scores, scores.max(), atol=1e-15, rtol=0)]
    return float(candidates.max())


def metrics(y: np.ndarray, p: np.ndarray, predicted: np.ndarray) -> dict:
    prevalence = float(y.mean())
    ap = float(average_precision_score(y, p))
    return {
        "n": int(len(y)),
        "positive_cases": int(y.sum()),
        "prevalence": prevalence,
        "auroc": float(roc_auc_score(y, p)),
        "average_precision": ap,
        "ap_lift_over_prevalence": ap / prevalence if prevalence else float("nan"),
        "balanced_accuracy": float(balanced_accuracy_score(y, predicted)),
        "brier": float(brier_score_loss(y, p)),
        "constant_prevalence_brier": prevalence * (1.0 - prevalence),
    }


def save_bundle(bundle: dict, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    joblib.dump(bundle, temporary, compress=3)
    joblib.load(temporary)
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return {"path": path.as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256(path)}


def run_oulad(reference: Path, output: Path) -> tuple[list[pd.DataFrame], list[dict], list[dict]]:
    predictions: list[pd.DataFrame] = []
    metric_rows: list[dict] = []
    inventory: list[dict] = []
    for day in DAYS:
        snapshot_path = reference / f"data/processed/oulad_day{day}.csv.gz"
        selection_path = reference / f"results/c12b/selections/day{day}__partial_gender_disability__standard.json"
        snapshot = pd.read_csv(snapshot_path, dtype={"imd_band": str}, low_memory=False)
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        features = list(selection["features"])
        forbidden = {"gender", "disability", "final_result", "target_risk", "id_student", "code_presentation", "date_unregistration"}
        if forbidden.intersection(features):
            raise AssertionError(f"forbidden OULAD proxy features at day {day}: {forbidden.intersection(features)}")
        train = snapshot[snapshot["code_presentation"].isin(["2013B", "2013J"])].copy()
        validation = snapshot[snapshot["code_presentation"] == "2014B"].copy()
        test = snapshot[snapshot["code_presentation"] == "2014J"].copy()
        seen_ids = set(train["id_student"].astype(int))
        unseen_mask = ~test["id_student"].astype(int).isin(seen_ids)

        for target, positive in [("gender", "M"), ("disability", "Y")]:
            y_train = (train[target].astype(str) == positive).astype(int).to_numpy()
            y_validation = (validation[target].astype(str) == positive).astype(int).to_numpy()
            y_test = (test[target].astype(str) == positive).astype(int).to_numpy()
            for model_name in PROXY_MODELS:
                seed = 20260902 + day + (0 if target == "gender" else 1000) + (0 if model_name == "logistic" else 10000)
                pipeline = make_pipeline(model_name, train, features, seed)
                pipeline.fit(train[features], y_train)
                validation_p = pipeline.predict_proba(validation[features])[:, 1]
                threshold = select_threshold(y_validation, validation_p)
                test_p = pipeline.predict_proba(test[features])[:, 1]
                predicted = (test_p >= threshold).astype(int)
                config_id = f"oulad__day{day}__{target}__{model_name}"
                pred = pd.DataFrame(
                    {
                        "dataset": "oulad",
                        "subject": "all",
                        "stage": f"day{day}",
                        "target_field": target,
                        "positive_class": positive,
                        "model": model_name,
                        "config_id": config_id,
                        "row_id": test["code_module"].astype(str) + "|" + test["code_presentation"].astype(str) + "|" + test["id_student"].astype(str),
                        "id_student": test["id_student"].astype(int).to_numpy(),
                        "fold": 0,
                        "target_binary": y_test,
                        "probability": test_p,
                        "decision_threshold": threshold,
                        "predicted_binary": predicted,
                        "unseen_student": unseen_mask.to_numpy(dtype=bool),
                    }
                )
                predictions.append(pred)
                base = {
                    "dataset": "oulad", "subject": "all", "stage": f"day{day}", "target_field": target,
                    "positive_class": positive, "model": model_name, "config_id": config_id,
                    "threshold_median": threshold, "threshold_min": threshold, "threshold_max": threshold,
                }
                metric_rows.append({**base, "evaluation_cohort": "all_2014J", **metrics(y_test, test_p, predicted)})
                metric_rows.append(
                    {
                        **base,
                        "evaluation_cohort": "unseen_student_2014J",
                        **metrics(y_test[unseen_mask], test_p[unseen_mask], predicted[unseen_mask]),
                    }
                )
                model_path = output / "models" / f"{config_id}.joblib"
                inv = save_bundle(
                    {
                        "protocol_id": "SecureEWS-C14A",
                        "config_id": config_id,
                        "dataset": "oulad",
                        "stage": f"day{day}",
                        "target_field": target,
                        "positive_class": positive,
                        "features": features,
                        "model": model_name,
                        "fit_presentations": ["2013B", "2013J"],
                        "threshold_selection_presentation": "2014B",
                        "test_presentation": "2014J",
                        "decision_threshold": threshold,
                        "pipeline": pipeline,
                    },
                    model_path,
                )
                inv.update({"dataset": "oulad", "subject": "all", "stage": f"day{day}", "target_field": target, "model": model_name, "config_id": config_id})
                inv["path"] = model_path.relative_to(output).as_posix()
                inventory.append(inv)
    return predictions, metric_rows, inventory


def load_uci697(data_path: Path) -> pd.DataFrame:
    source = pd.read_csv(data_path, sep=";")
    source.columns = [str(column).strip() for column in source.columns]
    source["row_id"] = np.arange(len(source), dtype=int)
    source = source[source["Target"].isin(["Dropout", "Graduate"])].copy()
    for column in sorted(UCI697_CATEGORICAL.intersection(source.columns)):
        source[column] = source[column].astype(str)
    return source


def uci697_features(source: pd.DataFrame, stage: str) -> list[str]:
    semester1 = [column for column in source if column.startswith("Curricular units 1st sem")]
    semester2 = [column for column in source if column.startswith("Curricular units 2nd sem")]
    excluded = semester2 + ["Target", "row_id"]
    full = [column for column in source if column not in excluded and (stage == "semester1" or column not in semester1)]
    return [column for column in full if column not in ["Gender", "Educational special needs"]]


def load_uci320(data_path: Path) -> pd.DataFrame:
    source = pd.read_csv(data_path, sep=";")
    source["row_id"] = np.arange(len(source), dtype=int)
    return source


def uci320_features(source: pd.DataFrame, stage: str) -> list[str]:
    base = [column for column in source if column not in ["G1", "G2", "G3", "row_id"]]
    full = base + (["G1"] if stage in ["period1", "period2"] else []) + (["G2"] if stage == "period2" else [])
    return [column for column in full if column != "sex"]


def run_uci_configuration(
    source: pd.DataFrame,
    split_path: Path,
    dataset: str,
    subject: str,
    stage: str,
    target: str,
    positive: int | str,
    features: list[str],
    model_name: str,
    output: Path,
) -> tuple[pd.DataFrame, dict, dict]:
    split = pd.read_csv(split_path)
    folds = []
    predictions = []
    thresholds = []
    target_binary = (source[target].astype(str) == str(positive)).astype(int)
    seed_base = 20260902 + (0 if dataset == "uci697" else 20000)
    for fold in sorted(split["outer_fold"].unique()):
        current = split[split["outer_fold"] == fold]
        fit_ids = current.loc[current["role"] == "fit", "row_id"].astype(int).to_numpy()
        calibration_ids = current.loc[current["role"] == "calibration", "row_id"].astype(int).to_numpy()
        test_ids = current.loc[current["role"] == "test", "row_id"].astype(int).to_numpy()
        indexed = source.set_index("row_id")
        fit = indexed.loc[fit_ids].reset_index()
        calibration = indexed.loc[calibration_ids].reset_index()
        test = indexed.loc[test_ids].reset_index()
        y_fit = target_binary.loc[fit_ids].to_numpy(dtype=int)
        y_calibration = target_binary.loc[calibration_ids].to_numpy(dtype=int)
        y_test = target_binary.loc[test_ids].to_numpy(dtype=int)
        if min(y_fit.sum(), len(y_fit) - y_fit.sum(), y_calibration.sum(), len(y_calibration) - y_calibration.sum(), y_test.sum(), len(y_test) - y_test.sum()) == 0:
            raise AssertionError(f"single-class proxy split: {dataset}/{subject}/{stage}/{target}/fold{fold}")
        seed = seed_base + int(fold) + (0 if model_name == "logistic" else 10000)
        pipeline = make_pipeline(model_name, fit, features, seed)
        pipeline.fit(fit[features], y_fit)
        calibration_p = pipeline.predict_proba(calibration[features])[:, 1]
        threshold = select_threshold(y_calibration, calibration_p)
        test_p = pipeline.predict_proba(test[features])[:, 1]
        thresholds.append(threshold)
        predictions.append(
            pd.DataFrame(
                {
                    "row_id": test_ids,
                    "fold": int(fold),
                    "target_binary": y_test,
                    "probability": test_p,
                    "decision_threshold": threshold,
                    "predicted_binary": (test_p >= threshold).astype(int),
                }
            )
        )
        folds.append(
            {
                "fold": int(fold),
                "fit_row_ids": fit_ids,
                "calibration_row_ids": calibration_ids,
                "test_row_ids": test_ids,
                "decision_threshold": threshold,
                "pipeline": pipeline,
            }
        )
    config_id = f"{dataset}__{subject}__{stage}__{target.lower().replace(' ', '_')}__{model_name}"
    pred = pd.concat(predictions, ignore_index=True).sort_values("row_id").reset_index(drop=True)
    pred.insert(0, "config_id", config_id)
    pred.insert(0, "model", model_name)
    pred.insert(0, "positive_class", positive)
    pred.insert(0, "target_field", target)
    pred.insert(0, "stage", stage)
    pred.insert(0, "subject", subject)
    pred.insert(0, "dataset", dataset)
    pred["id_student"] = np.nan
    pred["unseen_student"] = np.nan
    metric = {
        "dataset": dataset,
        "subject": subject,
        "stage": stage,
        "target_field": target,
        "positive_class": positive,
        "model": model_name,
        "config_id": config_id,
        "evaluation_cohort": "all_oof",
        "threshold_median": float(np.median(thresholds)),
        "threshold_min": float(np.min(thresholds)),
        "threshold_max": float(np.max(thresholds)),
        **metrics(pred["target_binary"].to_numpy(dtype=int), pred["probability"].to_numpy(dtype=float), pred["predicted_binary"].to_numpy(dtype=int)),
    }
    model_path = output / "models" / f"{config_id}.joblib"
    inventory = save_bundle(
        {
            "protocol_id": "SecureEWS-C14A",
            "config_id": config_id,
            "dataset": dataset,
            "subject": subject,
            "stage": stage,
            "target_field": target,
            "positive_class": positive,
            "features": features,
            "model": model_name,
            "split_source_sha256": sha256(split_path),
            "folds": folds,
        },
        model_path,
    )
    inventory.update({"dataset": dataset, "subject": subject, "stage": stage, "target_field": target, "model": model_name, "config_id": config_id})
    inventory["path"] = model_path.relative_to(output).as_posix()
    return pred, metric, inventory


def run_uci(uci_root: Path, output: Path) -> tuple[list[pd.DataFrame], list[dict], list[dict]]:
    prediction_tables: list[pd.DataFrame] = []
    metric_rows: list[dict] = []
    inventory: list[dict] = []
    uci697 = load_uci697(uci_root / "c13_work/inputs/uci697/data.csv")
    split697 = uci_root / "reference_uci/models_predictions/splits/uci697__all__dropout_vs_graduate.csv.gz"
    for stage in ["enrollment", "semester1"]:
        features = uci697_features(uci697, stage)
        forbidden = {"Gender", "Educational special needs", "Target", "row_id"}
        if forbidden.intersection(features):
            raise AssertionError(f"forbidden UCI697 features: {forbidden.intersection(features)}")
        for target in ["Gender", "Educational special needs"]:
            for model_name in PROXY_MODELS:
                pred, metric, inv = run_uci_configuration(
                    uci697, split697, "uci697", "all", stage, target, 1, features, model_name, output
                )
                prediction_tables.append(pred); metric_rows.append(metric); inventory.append(inv)

    input_dir = uci_root / "c13_work/inputs/uci320_current"
    split_dir = uci_root / "reference_uci/models_predictions/splits"
    for subject, filename in [("mathematics", "student-mat.csv"), ("portuguese", "student-por.csv")]:
        source = load_uci320(input_dir / filename)
        split_path = split_dir / f"uci320__{subject}__fail_g3_lt_10.csv.gz"
        for stage in ["baseline", "period1", "period2"]:
            features = uci320_features(source, stage)
            forbidden = {"sex", "G3", "row_id"}
            if forbidden.intersection(features):
                raise AssertionError(f"forbidden UCI320 features: {forbidden.intersection(features)}")
            for model_name in PROXY_MODELS:
                pred, metric, inv = run_uci_configuration(
                    source, split_path, "uci320", subject, stage, "sex", "M", features, model_name, output
                )
                prediction_tables.append(pred); metric_rows.append(metric); inventory.append(inv)
    return prediction_tables, metric_rows, inventory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oulad-reference", type=Path, required=True)
    parser.add_argument("--c13e-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if (output / "models").exists() and any((output / "models").iterdir()):
        raise SystemExit(f"Refusing to overwrite existing proxy models in {output / 'models'}")
    (output / "models").mkdir(parents=True, exist_ok=True)

    oulad_pred, oulad_metrics, oulad_inventory = run_oulad(args.oulad_reference.resolve(), output)
    uci_pred, uci_metrics, uci_inventory = run_uci(args.c13e_root.resolve(), output)
    predictions = pd.concat(oulad_pred + uci_pred, ignore_index=True, sort=False)
    metric_frame = pd.DataFrame(oulad_metrics + uci_metrics)
    inventory = pd.DataFrame(oulad_inventory + uci_inventory)
    atomic_csv(predictions, output / "proxy_predictions.csv.gz", compression="gzip")
    atomic_csv(metric_frame, output / "proxy_metrics.csv")
    atomic_csv(inventory, output / "model_inventory.csv")

    verification = {
        "phase": "C14C",
        "status": "PASS",
        "protocol_id": "SecureEWS-C14A",
        "configurations": int(len(inventory)),
        "metric_rows": int(len(metric_frame)),
        "prediction_rows": int(len(predictions)),
        "models": {"logistic": int((inventory["model"] == "logistic").sum()), "histgb": int((inventory["model"] == "histgb").sum())},
        "expected_configurations": 44,
        "all_probabilities_finite": bool(np.isfinite(predictions["probability"]).all()),
        "all_probabilities_in_unit_interval": bool(predictions["probability"].between(0, 1).all()),
        "minimum_positive_cases_in_evaluation": int(metric_frame["positive_cases"].min()),
        "inputs": {
            "oulad_snapshots_manifest_sha256": sha256(args.oulad_reference / "data/processed/snapshots_manifest.json"),
            "uci697_csv_sha256": sha256(args.c13e_root / "c13_work/inputs/uci697/data.csv"),
            "uci320_math_sha256": sha256(args.c13e_root / "c13_work/inputs/uci320_current/student-mat.csv"),
            "uci320_portuguese_sha256": sha256(args.c13e_root / "c13_work/inputs/uci320_current/student-por.csv"),
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
        },
        "errors": [],
    }
    if len(inventory) != 44 or not verification["all_probabilities_finite"] or not verification["all_probabilities_in_unit_interval"]:
        verification["status"] = "FAIL"
        verification["errors"].append("configuration count or probability validity guard failed")
    atomic_json(verification, output / "C14C_VERIFICATION.json")
    print(json.dumps(verification, indent=2, sort_keys=True))
    return 0 if verification["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
