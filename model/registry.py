from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from joblib import dump, load


def _model_dir() -> Path:
    base = os.getenv("MODEL_DIR", str(Path.cwd() / "models"))
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _bundle(model: Any, feature_names: list[str], meta: Dict[str, Any]) -> Dict[str, Any]:
    return {"model": model, "feature_names": feature_names, "meta": meta}


def save_model_bundle(model: Any, feature_names: list[str], version: str, meta: Optional[Dict[str, Any]] = None) -> Path:
    """Atomically save a model bundle (model + feature_names + meta) to MODEL_DIR.

    Returns final path.
    """
    meta = meta or {}
    out = _model_dir() / f"model_{version}.joblib"
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=out.name + ".", dir=str(out.parent))
    os.close(tmp_fd)
    dump(_bundle(model, feature_names, meta), tmp_path)
    os.replace(tmp_path, out)
    return out


def save_model(model: Any, version: str) -> Path:
    # Back-compat: save plain model only
    return save_model_bundle(model, feature_names=[], version=version, meta={"kind": "plain"})


def latest_model_path() -> Optional[Path]:
    paths = sorted(_model_dir().glob("model_*.joblib"))
    return paths[-1] if paths else None


def load_model(path: Path | str) -> Tuple[Any, list[str], Dict[str, Any]]:
    obj = load(path)
    if isinstance(obj, dict) and "model" in obj and "feature_names" in obj:
        return obj["model"], list(obj.get("feature_names", [])), dict(obj.get("meta", {}))
    # Plain model fallback
    return obj, [], {"kind": "plain"}


def load_latest_model() -> Tuple[Optional[Any], str, list[str], Dict[str, Any]]:
    p = latest_model_path()
    if not p:
        return None, "none", [], {}
    model, feature_names, meta = load_model(p)
    version = p.stem.replace("model_", "")
    return model, version, feature_names, meta
