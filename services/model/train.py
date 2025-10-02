from __future__ import annotations

import json
import os
from pathlib import Path

from model.train import train  # re-export for convenience

__all__ = ["train"]


if __name__ == "__main__":  # CLI wrapper
    import argparse

    parser = argparse.ArgumentParser(description="Train models (LR, XGB) and save best bundle")
    parser.add_argument("--data", required=True, help="Path to labeled JSONL or Parquet")
    parser.add_argument("--out", required=False, default="models/", help="Output model directory (sets MODEL_DIR)")
    parser.add_argument("--version", default="0.1.0")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Ensure registry saves into the requested directory
    os.environ["MODEL_DIR"] = str(out_dir.resolve())
    res = train(args.data, args.version, str(out_dir))
    print(json.dumps(res))
