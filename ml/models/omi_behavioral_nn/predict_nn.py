#!/usr/bin/env python3
"""Inference for the Omi Behavioral NN — ARCHITECTURE ONLY (no trained model).

Defines the inference path: a feature dict in the OMI_FEATURE_SCHEMA_V1 contract
-> ordered 42-dim vector -> model -> P(inauthentic). The feature-assembly side is
torch-free; the forward pass imports torch lazily. With --random-init the path can
be exercised end-to-end with an UNTRAINED model (random weights) purely to verify
wiring — the probability carries no meaning until a model is trained.

CPU-only. No production integration, no scoring change.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from dataset_builder import FEATURE_SCHEMA_VERSION, build_vector  # noqa: E402


def predict_one(model, features: dict) -> dict:
    """Score a single feature dict -> {probability, feature_schema_version, trained}."""
    import numpy as np
    import torch
    vec = np.asarray([build_vector(features)], dtype=np.float32)
    with torch.no_grad():
        prob = float(model.predict_proba(torch.as_tensor(vec)).reshape(-1)[0])
    return {
        "probability_inauthentic": prob,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "label": "inauthentic" if prob >= 0.5 else "authentic",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Omi Behavioral NN inference (architecture only)")
    p.add_argument("--model", default=None, help="path to a saved model artifact")
    p.add_argument("--features", default=None, help="path to a JSON feature dict")
    p.add_argument("--random-init", action="store_true",
                   help="use an UNTRAINED random model to verify the path (no meaning)")
    args = p.parse_args(argv)

    try:
        import torch  # noqa: F401
        from model import OmiBehavioralNet, build_model, set_seed
    except ImportError as exc:
        print(f"PyTorch not installed: {exc}. Feature assembly works; install torch "
              "(CPU) to run inference.")
        return 0

    if args.model and Path(args.model).is_file():
        model = OmiBehavioralNet.load(args.model)
    elif args.random_init:
        set_seed(0)
        model = build_model()
        print("WARNING: untrained random-init model — output is meaningless (wiring check only).")
    else:
        print("ARCHITECTURE-ONLY: no trained artifact. Pass --model <artifact>, or "
              "--random-init to verify the inference path. No real prediction is made.")
        return 0

    features = json.loads(Path(args.features).read_text()) if args.features else {}
    print(json.dumps(predict_one(model, features), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
