from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
from scipy.spatial.distance import jensenshannon

from features.featurizer import featurize


def _ensure_feature_space(examples: List[Tuple[List[float], List[str]]]) -> Tuple[np.ndarray, List[str]]:
    name_to_idx: Dict[str, int] = {}
    X_rows: List[List[float]] = []
    for vec, names in examples:
        for n in names:
            if n not in name_to_idx:
                name_to_idx[n] = len(name_to_idx)
                for row in X_rows:
                    row.append(0.0)
        row = [0.0] * len(name_to_idx)
        for v, n in zip(vec, names):
            row[name_to_idx[n]] = v
        X_rows.append(row)
    feature_names = [None] * len(name_to_idx)
    for n, i in name_to_idx.items():
        feature_names[i] = n
    return np.array(X_rows, dtype=float), feature_names  # type: ignore


def _load_jsonl_features(path: Path) -> Tuple[np.ndarray, List[str]]:
    examples: List[Tuple[List[float], List[str]]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            et = row.get("event_type", "")
            ev = row.get("event", {})
            vec, names = featurize(et, ev)
            examples.append((vec, names))
    return _ensure_feature_space(examples)


def psi(expected: np.ndarray, observed: np.ndarray, bins: int = 10) -> float:
    ec, eb = np.histogram(expected, bins=bins)
    oc, _ = np.histogram(observed, bins=eb)
    ep = ec / max(ec.sum(), 1)
    op = oc / max(oc.sum(), 1)
    ep = np.clip(ep, 1e-8, 1)
    op = np.clip(op, 1e-8, 1)
    return float(np.sum((ep - op) * np.log(ep / op)))


def js_divergence(expected: np.ndarray, observed: np.ndarray, bins: int = 10) -> float:
    ec, eb = np.histogram(expected, bins=bins)
    oc, _ = np.histogram(observed, bins=eb)
    ep = ec / max(ec.sum(), 1)
    op = oc / max(oc.sum(), 1)
    return float(jensenshannon(ep, op) ** 2)


def drift_report(baseline: Path, current: Path, bins: int = 10, select: Iterable[str] | None = None) -> Dict:
    Xb, names_b = _load_jsonl_features(baseline)
    Xc, names_c = _load_jsonl_features(current)
    # Align spaces: merge name sets and re-project
    all_names = list(dict.fromkeys(list(names_b) + list(names_c)))
    name_to_idx_b = {n: i for i, n in enumerate(names_b)}
    name_to_idx_c = {n: i for i, n in enumerate(names_c)}
    # Build aligned matrices
    def project(X: np.ndarray, names_src: List[str]) -> np.ndarray:
        src_map = {n: i for i, n in enumerate(names_src)}
        out = np.zeros((X.shape[0], len(all_names)), dtype=float)
        for j, n in enumerate(all_names):
            if n in src_map:
                out[:, j] = X[:, src_map[n]]
        return out

    Xb_aligned = project(Xb, names_b)
    Xc_aligned = project(Xc, names_c)

    # Optionally select subset
    if select:
        select_set = set(select)
        idx = [i for i, n in enumerate(all_names) if n in select_set]
        names = [all_names[i] for i in idx]
        Xb_sel = Xb_aligned[:, idx]
        Xc_sel = Xc_aligned[:, idx]
    else:
        names = all_names
        Xb_sel = Xb_aligned
        Xc_sel = Xc_aligned

    # Compute per-feature PSI and JS
    features: Dict[str, Dict[str, float]] = {}
    psi_vals: List[float] = []
    js_vals: List[float] = []
    for j, n in enumerate(names):
        eb = Xb_sel[:, j]
        ec = Xc_sel[:, j]
        # skip constant all-zero features
        if np.all(eb == 0) and np.all(ec == 0):
            p, d = 0.0, 0.0
        else:
            p = psi(eb, ec, bins=bins)
            d = js_divergence(eb, ec, bins=bins)
        features[n] = {"psi": float(p), "js": float(d)}
        psi_vals.append(float(p))
        js_vals.append(float(d))

    # Aggregate drift score to [0,1]
    # Map PSI to [0,1] using 1 - exp(-psi) to compress heavy tails
    psi_norm = [1.0 - float(np.exp(-max(0.0, p))) for p in psi_vals]
    # JS is already [0,1]
    # Combine by average per-feature, then average across features
    combined = [(pn + jv) / 2.0 for pn, jv in zip(psi_norm, js_vals)]
    drift_score = float(np.mean(combined)) if combined else 0.0

    report = {
        "features": features,
        "aggregate": {
            "drift_score": drift_score,
            "avg_psi": float(np.mean(psi_vals)) if psi_vals else 0.0,
            "avg_js": float(np.mean(js_vals)) if js_vals else 0.0,
            "n_features": len(names),
        },
    }
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Feature drift report (PSI + JS)")
    # Accept both baseline/current and ref/cur for convenience
    parser.add_argument("--baseline", "--ref", dest="baseline", required=False, help="Baseline labeled JSONL")
    parser.add_argument("--current", "--cur", dest="current", required=False, help="Current labeled JSONL")
    parser.add_argument("--out", default="drift_report.json")
    parser.add_argument("--bins", type=int, default=10)
    parser.add_argument("--select", type=str, default="", help="Comma-separated feature names to include")
    args = parser.parse_args()
    # Validate required paths
    if not args.baseline or not args.current:
        parser.error("--baseline/--ref and --current/--cur are required")
    select = [s.strip() for s in args.select.split(",") if s.strip()] if args.select else None
    rep = drift_report(Path(args.baseline), Path(args.current), bins=args.bins, select=select)
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    with outp.open("w", encoding="utf-8") as f:
        json.dump(rep, f)
    print(json.dumps({"drift_score": rep["aggregate"]["drift_score"]}))
