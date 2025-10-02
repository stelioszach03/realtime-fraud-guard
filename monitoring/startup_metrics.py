from __future__ import annotations

import json
import os
from pathlib import Path

from monitoring.exporters.custom_metrics import PR_AUC, PRECISION_AT_K, DRIFT_SCORE


def load_metrics() -> None:
    model_dir = os.getenv("MODEL_DIR", "models")
    mpath = Path(model_dir) / "metrics.json"
    if mpath.exists():
        try:
            data = json.loads(mpath.read_text())
            # Try nested or flat
            if isinstance(data, dict):
                if "lr" in data or "xgb" in data:
                    # choose selected if available
                    sel = data.get("selected")
                    metrics = data.get(sel, {}) if sel else {}
                else:
                    metrics = data
                pr = float(metrics.get("pr_auc", float("nan")))
                if pr == pr:  # not NaN
                    PR_AUC.set(pr)
                for k in (100, 500, 1000):
                    val = metrics.get(f"precision_at_{k}")
                    if val is not None:
                        PRECISION_AT_K.labels(k=str(k)).set(float(val))
        except Exception:
            pass

    dpath = Path("evaluation") / "drift_report.json"
    if dpath.exists():
        try:
            data = json.loads(dpath.read_text())
            agg = data.get("aggregate", {})
            ds = agg.get("drift_score")
            if ds is not None:
                DRIFT_SCORE.set(float(ds))
        except Exception:
            pass


# Execute on import
try:
    load_metrics()
except Exception:
    pass

