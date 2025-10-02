from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
from rich.console import Console
from rich.table import Table
from sklearn.metrics import average_precision_score, precision_score, roc_auc_score

from model.inference_core import InferenceEngine


def _load(jsonl_path: str | Path) -> Tuple[List[str], List[dict], np.ndarray]:
    types, events, labels = [], [], []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            types.append(row.get("event_type", ""))
            events.append(row.get("event", {}))
            labels.append(int(row.get("label", 0)))
    return types, events, np.array(labels, dtype=int)


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


def evaluate(jsonl_path: str | Path, k_list: Iterable[int] = (100, 500, 1000)) -> Dict[str, float]:
    etypes, events, y = _load(jsonl_path)
    engine = InferenceEngine()
    scores: List[float] = []
    for t, e in zip(etypes, events):
        s, _, _, _ = engine.predict_proba_and_reasons(t, e)
        scores.append(s)
    y_scores = np.array(scores, dtype=float)
    # Metrics
    has_both = len(np.unique(y)) > 1
    roc = float(roc_auc_score(y, y_scores)) if has_both else float("nan")
    pr_auc = float(average_precision_score(y, y_scores)) if has_both else float("nan")
    out: Dict[str, float] = {"roc_auc": roc, "pr_auc": pr_auc}
    for k in k_list:
        out[f"precision_at_{k}"] = _precision_at_k(y, y_scores, int(k))
    return out


def _print_table(metrics: Dict[str, float]) -> None:
    table = Table(title="Offline Evaluation")
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    for key in ["roc_auc", "pr_auc", "precision_at_100", "precision_at_500", "precision_at_1000"]:
        if key in metrics:
            val = metrics[key]
            table.add_row(key, f"{val:.4f}" if not (np.isnan(val)) else "nan")
    Console().print(table)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Offline evaluation on labeled JSONL")
    parser.add_argument("--data", default="evaluation/datasets/sample.jsonl")
    parser.add_argument("--out", default="metrics.json")
    parser.add_argument("--k", nargs="*", default=[100, 500, 1000], help="k values for precision@k")
    args = parser.parse_args()
    k_list = [int(k) for k in args.k]
    res = evaluate(args.data, k_list)
    _print_table(res)
    # Write metrics.json next to input by default if relative path
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(res, f)
    print(f"Wrote metrics to {out_path}")
