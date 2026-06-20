#!/usr/bin/env python3
"""Architecture tests for the Omi Behavioral NN foundation (no training).

Torch-free tests (schema + vector assembly + metrics) always run. Model tests
need PyTorch and are skipped (not failed) when it is unavailable. Runnable as:
    python -m pytest ml/models/omi_behavioral_nn/test_nn_foundation.py -q
    python ml/models/omi_behavioral_nn/test_nn_foundation.py
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from unittest import SkipTest

import numpy as np

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import dataset_builder as db  # noqa: E402
import evaluate_nn as ev  # noqa: E402

HAS_TORCH = importlib.util.find_spec("torch") is not None


def _need_torch():
    if not HAS_TORCH:
        raise SkipTest("PyTorch not installed")


# --- schema / vector assembly (torch-free) --------------------------------- #
def test_schema_is_42_dims():
    assert db.INPUT_DIM == 42
    assert len(db.FEATURE_NAMES) == 42 == len(set(db.FEATURE_NAMES))
    assert sum(db.BLOCKS.values()) == 42
    assert db.FEATURE_SCHEMA_VERSION == 1


def test_block_membership():
    assert db.FEATURE_NAMES[:21] == db.FINGERPRINT_FEATURES
    assert db.FEATURE_NAMES[21:37] == db.DETECTOR_FEATURES
    assert db.FEATURE_NAMES[37:] == db.METADATA_FEATURES
    assert len(db.DETECTOR_FEATURES) == 16


def test_build_vector_defaults():
    vec = db.build_vector({})
    assert len(vec) == 42
    i = db.FEATURE_NAMES.index
    assert vec[i("det_temporal_probability")] == 0.5   # absent detector prob
    assert vec[i("det_temporal_confidence")] == 0.0     # absent detector conf
    assert vec[i("fp_interval_cov")] == 0.0
    assert vec[i("meta_verified")] == 0.0


def test_build_vector_sets_values():
    feats = {"det_temporal_probability": 0.9, "fp_overall_probability": 0.3,
             "meta_verified": 1.0}
    vec = db.build_vector(feats)
    i = db.FEATURE_NAMES.index
    assert vec[i("det_temporal_probability")] == 0.9
    assert vec[i("fp_overall_probability")] == 0.3
    assert vec[i("meta_verified")] == 1.0


def test_normalize_fingerprint():
    n = db.normalize_fingerprint({"fp_posts_per_day": 50, "fp_follower_ratio_log": 0,
                                  "fp_mean_cosine": 2.0})
    assert abs(n["fp_posts_per_day"] - 0.5) < 1e-9
    assert abs(n["fp_follower_ratio_log"] - 0.5) < 1e-9   # range -3..3
    assert n["fp_mean_cosine"] == 1.0                      # clipped


def test_vectorize_many_and_synthetic():
    X = db.vectorize_many([{}, {"fp_confidence": 0.7}])
    assert X.shape == (2, 42) and X.dtype == np.float32
    Xs, ys = db.synthetic_batch(16, seed=1)
    assert Xs.shape == (16, 42) and ys.shape == (16,)
    assert Xs.min() >= 0.0 and Xs.max() <= 1.0 and set(np.unique(ys)) <= {0.0, 1.0}


# --- metrics (torch-free) -------------------------------------------------- #
def test_metrics_basic():
    assert ev.accuracy([1, 0, 1], [0.6, 0.4, 0.6]) == 1.0
    assert ev.roc_auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0
    assert ev.roc_auc([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]) == 0.0
    assert ev.roc_auc([1, 1], [0.4, 0.6]) == 0.5
    assert ev.brier([1, 0], [1.0, 0.0]) == 0.0
    p, r, f1 = ev._prf([1, 1, 0], [0.9, 0.2, 0.1])
    assert r == 0.5 and p == 1.0
    m = ev.compute_metrics([0, 1, 0, 1], [0.2, 0.8, 0.3, 0.7])
    assert set(m) >= {"accuracy", "f1", "roc_auc", "brier", "ece", "n"}


# --- model architecture (needs torch) -------------------------------------- #
def test_model_forward_shape():
    _need_torch()
    from model import build_model
    m = build_model()
    import torch
    X, _ = db.synthetic_batch(8, seed=0)
    logits = m(torch.as_tensor(X))
    probs = m.predict_proba(torch.as_tensor(X))
    assert tuple(logits.shape) == (8, 1) and tuple(probs.shape) == (8, 1)
    assert float(probs.min()) >= 0.0 and float(probs.max()) <= 1.0
    assert m.count_parameters() > 0


def test_model_input_dim_guard():
    _need_torch()
    from model import ModelConfig, OmiBehavioralNet
    try:
        OmiBehavioralNet(ModelConfig(input_dim=10))
        raise AssertionError("should reject non-42 input_dim")
    except ValueError:
        pass


def test_model_forward_rejects_bad_width():
    _need_torch()
    import torch
    from model import build_model
    m = build_model()
    try:
        m(torch.zeros((4, 40)))
        raise AssertionError("should reject width != 42")
    except ValueError:
        pass


def test_model_deterministic_seed():
    _need_torch()
    import torch
    from model import build_model, set_seed
    set_seed(0)
    a = build_model()
    set_seed(0)
    b = build_model()
    pa = next(a.parameters())
    pb = next(b.parameters())
    assert torch.allclose(pa, pb)


def test_save_load_roundtrip():
    _need_torch()
    import torch
    from model import build_model, OmiBehavioralNet, set_seed
    set_seed(0)
    m = build_model()
    X, _ = db.synthetic_batch(5, seed=2)
    before = m.predict_proba(torch.as_tensor(X))
    with tempfile.TemporaryDirectory() as d:
        path = str(Path(d) / "m.pt")
        m.save(path, metrics={"note": "architecture-only"})
        loaded = OmiBehavioralNet.load(path)
    after = loaded.predict_proba(torch.as_tensor(X))
    assert torch.allclose(before, after, atol=1e-6)


def test_predict_one_path():
    _need_torch()
    from model import build_model, set_seed
    import predict_nn
    set_seed(0)
    out = predict_nn.predict_one(build_model(), {"det_temporal_probability": 0.9})
    assert 0.0 <= out["probability_inauthentic"] <= 1.0
    assert out["feature_schema_version"] == 1 and out["label"] in {"authentic", "inauthentic"}


def _run_all() -> bool:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = skipped = failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
            passed += 1
        except SkipTest as exc:
            print(f"SKIP {fn.__name__}: {exc}")
            skipped += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {fn.__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {skipped} skipped, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)
