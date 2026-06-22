#!/usr/bin/env python3
"""Training scaffold for the Omi Behavioral NN — ARCHITECTURE ONLY (no training).

The full CPU training loop is defined here, but by default this script does NOT
train: it builds the model and runs a forward-only wiring smoke, then exits. Real
training is gated behind --run AND a labeled dataset, which is the documented
blocker (engine-independent analyst/disclosure labels do not exist yet —
ml/features/OMI_FEATURE_SCHEMA_V1.md §C/§D).

CPU-only. No production integration, no scoring change, no Hugging Face, no upload.
torch is imported lazily so this module imports without PyTorch installed.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from dataset_builder import INPUT_DIM, synthetic_batch  # noqa: E402 (torch-free)


@dataclass
class TrainConfig:
    epochs: int = 20
    lr: float = 1e-3
    weight_decay: float = 1e-4
    batch_size: int = 64
    val_fraction: float = 0.2
    seed: int = 0


def build_loaders(X, y, batch_size: int, val_fraction: float, seed: int):
    """Split (X, y) into train/val CPU DataLoaders."""
    import torch
    from torch.utils.data import DataLoader, random_split
    from dataset_builder import make_dataset

    ds = make_dataset(X, y)
    n_val = max(1, int(len(ds) * val_fraction))
    n_train = len(ds) - n_val
    gen = torch.Generator().manual_seed(seed)
    train_ds, val_ds = random_split(ds, [n_train, n_val], generator=gen)
    return (DataLoader(train_ds, batch_size=batch_size, shuffle=True),
            DataLoader(val_ds, batch_size=batch_size, shuffle=False))


def train_one_epoch(model, loader, optimizer, loss_fn) -> float:
    """One optimization pass; returns mean loss."""
    model.train()
    total, n = 0.0, 0
    for xb, yb in loader:
        optimizer.zero_grad()
        loss = loss_fn(model(xb), yb)
        loss.backward()
        optimizer.step()
        total += float(loss) * len(xb)
        n += len(xb)
    return total / max(1, n)


def evaluate_loss(model, loader, loss_fn) -> float:
    import torch
    model.eval()
    total, n = 0.0, 0
    with torch.no_grad():
        for xb, yb in loader:
            total += float(loss_fn(model(xb), yb)) * len(xb)
            n += len(xb)
    return total / max(1, n)


def train(model, X, y, config: TrainConfig):
    """Full CPU training loop (invoked only via --run with a real dataset)."""
    import torch
    from model import set_seed

    set_seed(config.seed)
    train_loader, val_loader = build_loaders(X, y, config.batch_size,
                                             config.val_fraction, config.seed)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.lr,
                                 weight_decay=config.weight_decay)
    loss_fn = torch.nn.BCEWithLogitsLoss()
    history = []
    for epoch in range(1, config.epochs + 1):
        tr = train_one_epoch(model, train_loader, optimizer, loss_fn)
        va = evaluate_loss(model, val_loader, loss_fn)
        history.append({"epoch": epoch, "train_loss": tr, "val_loss": va})
        print(f"  epoch {epoch:>3}  train {tr:.4f}  val {va:.4f}")
    return history


def _wiring_smoke() -> int:
    """Build the model + run a forward-only pass on synthetic data (no training)."""
    try:
        import torch  # noqa: F401
        from model import build_model
    except ImportError as exc:
        print(f"PyTorch not installed: {exc}. Architecture files are present; "
              "install torch (CPU) to run the wiring smoke.")
        return 0
    from model import set_seed
    set_seed(0)
    model = build_model()
    X, _ = synthetic_batch(8, seed=0)
    import torch
    with torch.no_grad():
        logits = model(torch.as_tensor(X))
        probs = model.predict_proba(torch.as_tensor(X))
    print(f"Model: OmiBehavioralNet  input_dim={INPUT_DIM}  "
          f"params={model.count_parameters()}")
    print(f"Forward smoke: logits {tuple(logits.shape)} -> probs {tuple(probs.shape)} "
          f"in [{float(probs.min()):.3f}, {float(probs.max()):.3f}]")
    print("ARCHITECTURE-ONLY: training intentionally NOT run.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Omi Behavioral NN training scaffold (architecture only)")
    p.add_argument("--run", action="store_true",
                   help="run real training (requires --data; intentionally gated)")
    p.add_argument("--data", default=None, help="path to a labeled feature dataset")
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--batch-size", type=int, default=64)
    args = p.parse_args(argv)

    if not args.run:
        return _wiring_smoke()

    if not args.data or not Path(args.data).is_file():
        print("REFUSED: --run needs --data <labeled dataset>. None exists yet — "
              "engine-independent labels are the documented training blocker "
              "(OMI_FEATURE_SCHEMA_V1 §C). Architecture foundation only.")
        return 1
    print("REFUSED: real training is out of scope for the V1 foundation "
          "(architecture only). Wire labels + dataset, then enable here.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
