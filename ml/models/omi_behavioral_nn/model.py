"""Omi Behavioral Neural Network — architecture (OMI_BEHAVIORAL_NEURAL_NETWORK_V1).

A small, CPU-only PyTorch MLP over the canonical 42-dim OMI_FEATURE_SCHEMA_V1
account vector (21 fingerprint + 16 detector + 5 metadata) → one logit =
P(inauthentic). Architecture only; no training is performed here.

Design notes:
  * Input is already normalized to [0,1]; an input LayerNorm stabilizes the
    detector/metadata blocks and the engine-prior fingerprint dims.
  * The model is an additive *re-aggregator* over engine signals (it consumes the
    engine's own prior via fp_overall_probability + the detector block), matching
    the dormant serving seam (apps/api/app/ml/scorer.py) — but is NOT wired to it.
  * CPU-only by construction (device is always cpu; no .cuda calls).
  * The artifact bundle carries feature_schema_version so a loader can refuse a
    mismatched contract (forward-compatible with the scorer convention).
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field

import torch
from torch import nn

from dataset_builder import FEATURE_SCHEMA_VERSION, INPUT_DIM

DEVICE = torch.device("cpu")  # CPU-only foundation


@dataclass
class ModelConfig:
    input_dim: int = INPUT_DIM            # 42 (OMI_FEATURE_SCHEMA_V1)
    hidden_dims: tuple[int, ...] = (128, 64, 32)
    dropout: float = 0.2
    activation: str = "gelu"              # "gelu" | "relu"
    input_norm: bool = True
    feature_schema_version: int = FEATURE_SCHEMA_VERSION


_ACTIVATIONS = {"gelu": nn.GELU, "relu": nn.ReLU}


def set_seed(seed: int = 0) -> None:
    """Deterministic CPU init/training."""
    import random
    random.seed(seed)
    torch.manual_seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:  # pragma: no cover
        pass


class OmiBehavioralNet(nn.Module):
    """MLP: [LayerNorm] -> (Linear -> Act -> Dropout) x N -> Linear(->1) logit."""

    def __init__(self, config: ModelConfig | None = None):
        super().__init__()
        self.config = config or ModelConfig()
        if self.config.input_dim != INPUT_DIM:
            raise ValueError(
                f"input_dim {self.config.input_dim} != OMI_FEATURE_SCHEMA_V1 dim {INPUT_DIM}"
            )
        act = _ACTIVATIONS.get(self.config.activation)
        if act is None:
            raise ValueError(f"unknown activation '{self.config.activation}'")

        layers: list[nn.Module] = []
        if self.config.input_norm:
            layers.append(nn.LayerNorm(self.config.input_dim))
        prev = self.config.input_dim
        for h in self.config.hidden_dims:
            layers += [nn.Linear(prev, h), act(), nn.Dropout(self.config.dropout)]
            prev = h
        layers.append(nn.Linear(prev, 1))  # single logit
        self.net = nn.Sequential(*layers)
        self.to(DEVICE)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """(N, 42) -> (N, 1) logits."""
        if x.dim() != 2 or x.size(-1) != self.config.input_dim:
            raise ValueError(
                f"expected (N, {self.config.input_dim}) input, got {tuple(x.shape)}"
            )
        return self.net(x.to(DEVICE))

    @torch.no_grad()
    def predict_proba(self, x: torch.Tensor) -> torch.Tensor:
        """(N, 42) -> (N, 1) probabilities in [0,1] = P(inauthentic)."""
        self.eval()
        return torch.sigmoid(self.forward(x))

    def count_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    # --- artifact I/O (parallel to the scorer bundle; NOT wired to production) - #
    def save(self, path: str, metrics: dict | None = None) -> None:
        torch.save({
            "kind": "pytorch_mlp",
            "feature_schema_version": self.config.feature_schema_version,
            "config": asdict(self.config),
            "state_dict": self.state_dict(),
            "metrics": metrics or {},
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }, path)

    @classmethod
    def load(cls, path: str) -> "OmiBehavioralNet":
        bundle = torch.load(path, map_location=DEVICE, weights_only=False)
        if bundle.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
            raise ValueError(
                f"artifact feature_schema_version {bundle.get('feature_schema_version')} "
                f"!= expected {FEATURE_SCHEMA_VERSION}"
            )
        cfg = bundle.get("config", {})
        cfg["hidden_dims"] = tuple(cfg.get("hidden_dims", (128, 64, 32)))
        model = cls(ModelConfig(**cfg))
        model.load_state_dict(bundle["state_dict"])
        model.eval()
        return model


def build_model(config: ModelConfig | None = None) -> OmiBehavioralNet:
    return OmiBehavioralNet(config)
