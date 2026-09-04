from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


SEED = 42
KEY = ["code_module", "code_presentation", "id_student"]
SENSITIVE = ["gender", "region", "highest_education", "imd_band", "age_band", "disability"]
CONTEXT = ["code_module", "num_of_prev_attempts", "studied_credits", "registration_lead_days"]
DIGITAL = [
    "clicks_total",
    "active_days",
    "clicks_daily_mean",
    "clicks_daily_std",
    "clicks_daily_max",
    "first_activity_day",
    "last_activity_day",
    "clicks_last7",
    "active_days_last7",
    "clicks_prev7",
    "active_days_prev7",
    "clicks_prestart",
    "active_days_prestart",
    "inactivity_days",
    "click_trend_log",
    "assessments_submitted",
    "assessment_weight_completed",
    "late_submissions",
    "assessments_expected",
    "assessment_weight_expected",
    "assessment_submission_ratio",
    "assessment_weight_completion_ratio",
]
STRICT_BASE = [
    "assessments_submitted",
    "assessment_weight_completed",
    "late_submissions",
    "assessments_expected",
    "assessment_weight_expected",
    "assessment_submission_ratio",
    "assessment_weight_completion_ratio",
]
STRICT_TIMING = [
    "assessments_missed",
    "assessment_weight_missed",
    "early_submissions",
    "on_due_submissions",
    "early_submission_weight",
    "on_due_submission_weight",
    "late_submission_weight",
    "first_submission_day",
    "last_submission_day",
    "submission_span_days",
    "days_since_first_submission",
    "days_since_last_submission",
    "days_before_due_mean",
    "days_before_due_std",
    "days_before_due_min",
    "days_before_due_max",
]
STRICT_TYPED = [
    f"{kind}_{suffix}"
    for kind in ("tma", "cma", "exam")
    for suffix in (
        "expected",
        "submitted",
        "missed",
        "weight_expected",
        "weight_completed",
        "weight_missed",
        "completion_ratio",
        "weight_completion_ratio",
    )
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def split_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train = frame.loc[frame["code_presentation"].isin(["2013B", "2013J"])].copy()
    validation = frame.loc[frame["code_presentation"].eq("2014B")].copy()
    test = frame.loc[frame["code_presentation"].eq("2014J")].copy()
    if min(len(train), len(validation), len(test)) == 0:
        raise RuntimeError("Temporal split produced an empty partition")
    return train, validation, test


def make_pipeline(categorical: list[str], numeric: list[str], leaf_nodes: int) -> Pipeline:
    categorical_pipe = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    numeric_pipe = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
        ]
    )
    preprocessor = ColumnTransformer(
        [("categorical", categorical_pipe, categorical), ("numeric", numeric_pipe, numeric)],
        remainder="drop",
    )
    model = HistGradientBoostingClassifier(
        learning_rate=0.05,
        max_iter=250,
        max_leaf_nodes=leaf_nodes,
        min_samples_leaf=30,
        l2_regularization=1.0,
        early_stopping=False,
        random_state=SEED,
    )
    return Pipeline([("preprocess", preprocessor), ("model", model)])


def fit_platt(y: np.ndarray, probabilities: np.ndarray) -> LogisticRegression:
    eps = 1e-6
    clipped = np.clip(probabilities, eps, 1 - eps)
    logits = np.log(clipped / (1 - clipped))
    calibrator = LogisticRegression(C=1000.0, random_state=SEED)
    calibrator.fit(logits.reshape(-1, 1), y)
    if float(calibrator.coef_[0, 0]) <= 0:
        raise RuntimeError("Platt calibration slope is not positive")
    return calibrator


def apply_platt(calibrator: LogisticRegression, probabilities: np.ndarray) -> np.ndarray:
    eps = 1e-6
    clipped = np.clip(probabilities, eps, 1 - eps)
    logits = np.log(clipped / (1 - clipped))
    return calibrator.predict_proba(logits.reshape(-1, 1))[:, 1]


def stable_tie_keys(frame: pd.DataFrame) -> np.ndarray:
    return np.asarray(
        [
            hashlib.sha256(f"{module}|{presentation}|{student}".encode("utf-8")).hexdigest()
            for module, presentation, student in frame[KEY].itertuples(index=False, name=None)
        ],
        dtype=str,
    )


def top_budget_indices(
    probabilities: np.ndarray,
    modules: np.ndarray,
    tie_keys: np.ndarray,
    budget: float = 0.10,
) -> np.ndarray:
    p = np.asarray(probabilities, dtype=float)
    module_values = np.asarray(modules).astype(str)
    tie_values = np.asarray(tie_keys).astype(str)
    selected: list[np.ndarray] = []
    for module in sorted(np.unique(module_values)):
        positions = np.flatnonzero(module_values == module)
        k = max(1, min(len(positions), int(math.ceil(budget * len(positions)))))
        order = np.lexsort((tie_values[positions], -p[positions]))
        selected.append(positions[order[:k]])
    return np.concatenate(selected)


def ece10(y: np.ndarray, p: np.ndarray) -> float:
    edges = np.linspace(0.0, 1.0, 11)
    bins = np.clip(np.digitize(p, edges[1:-1], right=True), 0, 9)
    result = 0.0
    for index in range(10):
        mask = bins == index
        if mask.any():
            result += float(mask.mean()) * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return result


def metrics(
    y: np.ndarray,
    p: np.ndarray,
    modules: np.ndarray,
    tie_keys: np.ndarray,
) -> dict[str, float | int]:
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    selected = top_budget_indices(p, modules, tie_keys)
    true_alerts = int(y[selected].sum())
    alerts = int(len(selected))
    positives = int(y.sum())
    prevalence = float(y.mean())
    precision = true_alerts / alerts
    return {
        "n": int(len(y)),
        "positives": positives,
        "prevalence": prevalence,
        "average_precision": float(average_precision_score(y, p)),
        "roc_auc": float(roc_auc_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "ece10": ece10(y, p),
        "alerts": alerts,
        "true_alerts": true_alerts,
        "false_alerts": alerts - true_alerts,
        "precision_at_10": precision,
        "recall_at_10": true_alerts / positives,
        "lift_at_10": precision / prevalence,
    }
