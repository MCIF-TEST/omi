#!/usr/bin/env python3
"""Evaluation for the Omi Behavioral NN — ARCHITECTURE ONLY (no training).

Pure-numpy metric functions (importable + testable without PyTorch) plus a
torch-lazy ``evaluate`` that runs a model forward pass and scores it. No model is
trained here; this defines the offline evaluation contract a future trained
artifact will be measured against.

CPU-only. No production integration, no scoring change.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))


def accuracy(y_true: np.ndarray, y_prob: np.ndarray, threshold: float = 0.5) -> float:
    y_pred = (np.asarray(y_prob) >= threshold).astype(int)
    return float((y_pred == np.asarray(y_true).astype(int)).mean())


def _prf(y_true: np.ndarray, y_prob: np.ndarray, threshold: float = 0.5):
    y_true = np.asarray(y_true).astype(int)
    y_pred = (np.asarray(y_prob) >= threshold).astype(int)
    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def roc_auc(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Rank-based AUC (Mann-Whitney U). Undefined for one-class -> 0.5."""
    y_true = np.asarray(y_true).astype(int)
    y_prob = np.asarray(y_prob, dtype=float)
    pos, neg = y_prob[y_true == 1], y_prob[y_true == 0]
    if len(pos) == 0 or len(neg) == 0:
        return 0.5
    ranks = np.argsort(np.argsort(y_prob)) + 1
    rank_pos = ranks[y_true == 1].sum()
    u = rank_pos - len(pos) * (len(pos) + 1) / 2
    return float(u / (len(pos) * len(neg)))


def brier(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    return float(np.mean((np.asarray(y_prob, dtype=float) - np.asarray(y_true)) ** 2))


def expected_calibration_error(y_true, y_prob, bins: int = 10) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)
    edges = np.linspace(0, 1, bins + 1)
    ece, n = 0.0, len(y_prob)
    for i in range(bins):
        m = (y_prob >= edges[i]) & (y_prob < edges[i + 1] if i < bins - 1 else y_prob <= edges[i + 1])
        if m.any():
            ece += abs(y_prob[m].mean() - y_true[m].mean()) * m.sum() / n
    return float(ece)


def compute_metrics(y_true: np.ndarray, y_prob: np.ndarray) -> dict:
    precision, recall, f1 = _prf(y_true, y_prob)
    return {
        "n": int(len(y_true)),
        "accuracy": accuracy(y_true, y_prob),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "roc_auc": roc_auc(y_true, y_prob),
        "brier": brier(y_true, y_prob),
        "ece": expected_calibration_error(y_true, y_prob),
    }


def evaluate(model, X: np.ndarray, y: np.ndarray) -> dict:
    """Forward-pass a model over (X, y) and return metrics (no grad, CPU)."""
    import torch
    from dataset_builder import to_tensor
    with torch.no_grad():
        probs = model.predict_proba(to_tensor(X)).cpu().numpy().reshape(-1)
    return compute_metrics(np.asarray(y).reshape(-1), probs)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Omi Behavioral NN evaluation (architecture only)")
    p.add_argument("--model", default=None, help="path to a saved model artifact")
    p.add_argument("--data", default=None, help="path to a labeled eval dataset")
    args = p.parse_args(argv)

    if not args.model or not args.data:
        print("ARCHITECTURE-ONLY: metric functions are defined and unit-tested; "
              "pass --model and --data once a trained artifact + labeled eval set "
              "exist. No model is trained or evaluated here.")
        return 0
    try:
        from model import OmiBehavioralNet
    except ImportError as exc:
        print(f"PyTorch not installed: {exc}")
        return 1
    print("REFUSED: no trained artifact exists yet (V1 foundation is architecture only).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
