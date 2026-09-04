#!/usr/bin/env python3
"""Shared, deterministic modeling utilities for SecureEWS C13B."""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


PROTOCOL_ID = "SecureEWS-C13A"
HGB_LEAVES = (7, 15, 31)


@dataclass(frozen=True)
class Config:
    dataset: str
    subject: str
    outcome: str
    stage: str
    policy: str
    model: str
    features: tuple[str, ...]
    categorical: tuple[str, ...]
    seed: int
    budget_group: str
    exploratory: bool = False

    @property
    def config_id(self) -> str:
        raw = "__".join(
            [self.dataset, self.subject, self.outcome, self.stage, self.policy, self.model]
        )
        slug = raw.lower().replace(" ", "_").replace("/", "_")
        return slug.replace("'", "").replace("(", "").replace(")", "")

    def as_dict(self) -> dict:
        return {
            "dataset": self.dataset,
            "subject": self.subject,
            "outcome": self.outcome,
            "stage": self.stage,
            "policy": self.policy,
            "model": self.model,
            "features": list(self.features),
            "categorical": list(self.categorical),
            "seed": self.seed,
            "budget_group": self.budget_group,
            "exploratory": self.exploratory,
            "config_id": self.config_id,
        }


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def make_pipeline(model_name: str, categorical: Iterable[str], numeric: Iterable[str], seed: int) -> Pipeline:
    categorical = list(categorical)
    numeric = list(numeric)
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
    preprocessor = ColumnTransformer(transformers, remainder="drop")
    if model_name == "logistic":
        model = LogisticRegression(C=1.0, max_iter=2000, random_state=seed)
    elif model_name == "histgb":
        model = HistGradientBoostingClassifier(
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
    return Pipeline([("preprocess", preprocessor), ("model", model)])


def fit_platt(y: np.ndarray, p: np.ndarray, seed: int) -> LogisticRegression:
    logits = probability_logit(p)
    calibrator = LogisticRegression(C=1000.0, max_iter=1000, random_state=seed)
    calibrator.fit(logits.reshape(-1, 1), np.asarray(y, dtype=int))
    return calibrator


def probability_logit(p: np.ndarray) -> np.ndarray:
    eps = 1e-6
    values = np.asarray(p, dtype=float)
    return np.log(np.clip(values, eps, 1 - eps) / np.clip(1 - values, eps, 1 - eps))


def apply_platt(calibrator: LogisticRegression, p: np.ndarray) -> np.ndarray:
    return calibrator.predict_proba(probability_logit(p).reshape(-1, 1))[:, 1]


def fit_selected_model(
    fit_frame: pd.DataFrame,
    calibration_frame: pd.DataFrame,
    config: Config,
    target_col: str = "target_risk",
) -> tuple[Pipeline, LogisticRegression, int | None, list[dict]]:
    features = list(config.features)
    categorical = list(config.categorical)
    numeric = [c for c in features if c not in categorical]
    selection: list[dict] = []
    if config.model == "histgb":
        candidates = []
        for leaves in HGB_LEAVES:
            candidate = make_pipeline("histgb", categorical, numeric, config.seed)
            candidate.set_params(model__max_leaf_nodes=leaves)
            candidate.fit(fit_frame[features], fit_frame[target_col].to_numpy(dtype=int))
            validation_p = candidate.predict_proba(calibration_frame[features])[:, 1]
            score = float(average_precision_score(calibration_frame[target_col], validation_p))
            candidates.append((score, -leaves, leaves, candidate, validation_p))
            selection.append(
                {"max_leaf_nodes": leaves, "validation_average_precision": score, "selected": False}
            )
        _, _, selected_leaves, model, calibration_raw = max(candidates, key=lambda x: (x[0], x[1]))
        for row in selection:
            row["selected"] = row["max_leaf_nodes"] == selected_leaves
    else:
        selected_leaves = None
        model = make_pipeline("logistic", categorical, numeric, config.seed)
        model.fit(fit_frame[features], fit_frame[target_col].to_numpy(dtype=int))
        calibration_raw = model.predict_proba(calibration_frame[features])[:, 1]
    calibrator = fit_platt(calibration_frame[target_col].to_numpy(dtype=int), calibration_raw, config.seed)
    return model, calibrator, selected_leaves, selection


def bundle_predict(bundle: dict, source: pd.DataFrame) -> pd.DataFrame:
    rows = []
    features = bundle["config"]["features"]
    for fold in bundle["folds"]:
        row_ids = np.asarray(fold["test_row_ids"], dtype=int)
        test = source.set_index("row_id").loc[row_ids].reset_index()
        raw = fold["model"].predict_proba(test[features])[:, 1]
        calibrated = apply_platt(fold["calibrator"], raw)
        rows.append(pd.DataFrame({"row_id": row_ids, "fold": fold["fold"], "probability_calibrated": calibrated}))
    return pd.concat(rows, ignore_index=True).sort_values("row_id").reset_index(drop=True)


def save_bundle(bundle: dict, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    if temporary.exists():
        raise RuntimeError(f"temporary bundle already exists: {temporary}")
    joblib.dump(bundle, temporary, compress=3)
    # Force the bytes to stable storage and prove that the serialized estimator
    # can be loaded before publishing the final filename.
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    joblib.load(temporary)
    os.replace(temporary, path)
    return {"path": path.as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256(path)}


def deterministic_tie_key(dataset: str, row_id: int, seed: int) -> str:
    raw = f"{PROTOCOL_ID}|{dataset}|{int(row_id)}|{seed}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def selected_at_budget(
    frame: pd.DataFrame,
    probability_col: str,
    group_col: str,
    budget: float = 0.10,
    tie_rule: str = "canonical_hash",
    dataset: str | None = None,
    seed: int | None = None,
) -> np.ndarray:
    selected = np.zeros(len(frame), dtype=bool)
    working = frame.reset_index(drop=True)
    for group in sorted(working[group_col].astype(str).unique()):
        idx = np.flatnonzero(working[group_col].astype(str).to_numpy() == group)
        k = max(1, min(len(idx), int(math.ceil(budget * len(idx)))))
        if tie_rule == "legacy_stable":
            order = idx[np.argsort(-working.loc[idx, probability_col].to_numpy(), kind="stable")]
        elif tie_rule == "canonical_hash":
            if dataset is None or seed is None:
                raise ValueError("dataset and seed are required for canonical_hash tie-breaking")
            keys = np.asarray(
                [deterministic_tie_key(dataset, rid, seed) for rid in working.loc[idx, "row_id"]]
            )
            probabilities = working.loc[idx, probability_col].to_numpy(dtype=float)
            order = idx[np.lexsort((keys, -probabilities))]
        else:
            raise ValueError(tie_rule)
        selected[order[:k]] = True
    return selected


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
