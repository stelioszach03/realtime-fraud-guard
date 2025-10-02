from __future__ import annotations

import json
import os
import time
from pathlib import Path
import math
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from features.featurizer import featurize
from features.schema import FEATURE_VERSION
from model.registry import save_model_bundle


def _ensure_feature_space(examples: List[Tuple[List[float], List[str]]]) -> Tuple[np.ndarray, List[str]]:
    name_to_idx: Dict[str, int] = {}
    X_rows: List[List[float]] = []
    for vec, names in examples:
        # Expand space if new names come
        for n in names:
            if n not in name_to_idx:
                name_to_idx[n] = len(name_to_idx)
                # pad previous rows
                for row in X_rows:
                    row.append(0.0)
        row = [0.0] * len(name_to_idx)
        for v, n in zip(vec, names):
            row[name_to_idx[n]] = v
        X_rows.append(row)
    # Convert to ndarray
    feature_names = [None] * len(name_to_idx)
    for n, i in name_to_idx.items():
        feature_names[i] = n
    return np.array(X_rows, dtype=float), feature_names  # type: ignore


def _load_jsonl(path: Path) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    examples: List[Tuple[List[float], List[str]]] = []
    labels: List[int] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            et = row.get("event_type", "")
            ev = row.get("event", {})
            y = int(row.get("label", 0))
            vec, names = featurize(et, ev)
            examples.append((vec, names))
            labels.append(y)
    X, feature_names = _ensure_feature_space(examples)
    return X, np.array(labels, dtype=int), feature_names


def _load_parquet(path: Path) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    df = pd.read_parquet(path)
    examples: List[Tuple[List[float], List[str]]] = []
    labels: List[int] = []
    for _, row in df.iterrows():
        et = row.get("event_type", "")
        ev = row.get("event", {})
        if isinstance(ev, str):
            try:
                ev = json.loads(ev)
            except Exception:
                ev = {}
        y = int(row.get("label", 0))
        vec, names = featurize(et, ev)
        examples.append((vec, names))
        labels.append(y)
    X, feature_names = _ensure_feature_space(examples)
    return X, np.array(labels, dtype=int), feature_names


def _precision_at_k(y_true: np.ndarray, y_scores: np.ndarray, k: int) -> float:
    if len(y_true) == 0:
        return float("nan")
    kk = max(1, min(k, len(y_scores)))
    idx = np.argsort(y_scores)[-kk:]
    y_hat = np.zeros_like(y_true)
    y_hat[idx] = 1
    if y_true.sum() == 0:
        return float("nan")
    return float(precision_score(y_true, y_hat))


def _metrics(y_true: np.ndarray, y_scores: np.ndarray) -> Dict[str, float]:
    has_pos = int(y_true.sum()) > 0
    has_both = len(np.unique(y_true)) > 1
    metrics: Dict[str, float] = {}
    metrics["roc_auc"] = float(roc_auc_score(y_true, y_scores)) if has_both else float("nan")
    metrics["pr_auc"] = float(average_precision_score(y_true, y_scores)) if has_both else float("nan")
    for k in (100, 500, 1000):
        metrics[f"precision_at_{k}"] = _precision_at_k(y_true, y_scores, k) if has_pos else float("nan")
    return metrics


def _choose_best(m_lr: Dict[str, float], m_xgb: Dict[str, float]) -> str:
    # Prefer higher PR-AUC, tie-break by ROC-AUC
    a, b = m_lr.get("pr_auc", float("nan")), m_xgb.get("pr_auc", float("nan"))
    if (not math.isnan(b)) and (math.isnan(a) or b > a):
        return "xgb"
    if (not math.isnan(a)) and (math.isnan(b) or a > b):
        return "lr"
    # tie -> compare ROC
    if m_xgb.get("roc_auc", float("nan")) > m_lr.get("roc_auc", float("nan")):
        return "xgb"
    return "lr"


def train(dataset_path: str | Path, version: str = "0.1.0", model_dir: str | None = None) -> Dict[str, str]:
    path = Path(dataset_path)
    if path.suffix.lower() in (".parquet", ".pq"):
        X, y, feature_names = _load_parquet(path)
    else:
        X, y, feature_names = _load_jsonl(path)
    if X.size == 0:
        raise ValueError("Empty dataset")

    # Train Logistic Regression pipeline
    lr_pipe = Pipeline([
        ("scaler", StandardScaler(with_mean=False)),
        ("clf", LogisticRegression(max_iter=500, n_jobs=1)),
    ])
    lr_pipe.fit(X, y)
    lr_scores = lr_pipe.predict_proba(X)[:, 1]
    lr_metrics = _metrics(y, lr_scores)

    # Train XGBoost
    xgb = XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        n_jobs=2,
        tree_method="hist",
        random_state=42,
    )
    xgb.fit(X, y)
    xgb_scores = xgb.predict_proba(X)[:, 1]
    xgb_metrics = _metrics(y, xgb_scores)

    # Choose best
    best = _choose_best(lr_metrics, xgb_metrics)
    best_model = lr_pipe if best == "lr" else xgb

    # Save bundle atomically
    model_dir_env = model_dir or os.getenv("MODEL_DIR", str(Path.cwd() / "models"))
    meta = {
        "version": version,
        "trained_at": int(time.time()),
        "feature_version": FEATURE_VERSION,
        "model_type": "logreg" if best == "lr" else "xgb",
        "metrics_lr": lr_metrics,
        "metrics_xgb": xgb_metrics,
    }
    out_path = save_model_bundle(best_model, feature_names, version, meta)

    # Write metrics.json for CI artifact
    metrics_out = Path(model_dir_env) / "metrics.json"
    metrics_out.parent.mkdir(parents=True, exist_ok=True)
    with metrics_out.open("w", encoding="utf-8") as f:
        json.dump({"lr": lr_metrics, "xgb": xgb_metrics, "selected": best, "model_path": str(out_path)}, f)

    return {"model_path": str(out_path), "metrics_path": str(metrics_out)}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="evaluation/datasets/sample.jsonl")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--model-dir", default=None)
    args = parser.parse_args()
    res = train(args.data, args.version, args.model_dir)
    print(json.dumps(res))
