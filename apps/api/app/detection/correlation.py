"""Signal-correlation model: hand-tuned by default, learned from data when available.

The aggregator must not treat correlated detectors as independent evidence
(GAP-02). *How* correlated they are is a question the data should answer, not a
constant we guess. This module provides a single interface — ``axis_of`` (the
independence axis a detector belongs to) and ``compute_factors`` (the per-detector
redundancy discount) — backed by either:

* the **default** model: the hand-curated correlation *groups* with their
  redundancy factors taken from Settings. This is exactly the behavior shipped
  with the first GAP-02 cut, and is what runs when no learned artifact exists.

* a **learned** model: a measured pairwise correlation matrix (fitted by
  :mod:`app.detection.correlation_fit` over the labeled corpus). Redundancy
  becomes a continuous function of the observed correlation, and the discrete
  independence axes are the connected components of the correlation graph — so
  whether ``coordination`` really clusters with the timing detectors stops being
  an assumption and becomes whatever the data shows.

Loading is safe: a missing or malformed artifact silently falls back to the
default model. The runtime path never imports numpy or any heavy dependency —
it only evaluates a small matrix that the offline fitter produced.
"""

from __future__ import annotations

import json
import logging
import math
import os
from functools import lru_cache

_log = logging.getLogger("omi.detection.correlation")

# Detectors in a stable order. New detectors append here.
DETECTORS: tuple[str, ...] = (
    "temporal", "semantic", "ai_writing", "profile",
    "memory", "voice", "engagement", "coordination",
    "narrative",
)

# Hand-curated correlation groups: which detectors share an evidence basis, the
# Settings attribute holding the group's redundancy factor, and a human label.
# This is the single source of truth for the *default* model's membership and
# for the static axis helper used elsewhere.
CORRELATION_GROUPS: dict[str, dict] = {
    "content_text": {
        "members": frozenset({"semantic", "ai_writing"}),
        "setting": "decorrelation_redundancy_content",
        "label": "text-pattern",
    },
    "behavioral_timing": {
        "members": frozenset({"temporal", "engagement", "coordination"}),
        "setting": "decorrelation_redundancy_timing",
        "label": "posting-timing",
    },
}


def static_axis_of(name: str) -> str:
    """Independence axis under the default group model. Correlated detectors
    share their group's axis; everything else is its own axis."""
    for axis, group in CORRELATION_GROUPS.items():
        if name in group["members"]:
            return axis
    return name


def default_prior_matrix(
    settings,
    detectors: tuple[str, ...] = DETECTORS,
    strength: float = 0.5,
) -> list[list[float]]:
    """The correlation matrix implied by the hand-tuned default groups.

    Used as the *prior* the learned fitter shrinks toward: where the data has no
    evidence for a pair (e.g. ``coordination``, which only fires in cross-account
    scans), the model should fall back to this curated belief rather than
    asserting independence (0.0). The within-group correlation is chosen so the
    learned discount formula ``1 - ρ·strength`` reproduces the group's redundancy
    factor exactly, keeping the prior self-consistent with the default model.
    """
    n = len(detectors)
    idx = {d: i for i, d in enumerate(detectors)}
    m = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for g in CORRELATION_GROUPS.values():
        r = float(getattr(settings, g["setting"], 1.0))
        if r >= 1.0 or strength <= 0:
            continue
        rho = max(0.0, min(1.0, (1.0 - r) / strength))
        members = [mn for mn in g["members"] if mn in idx]
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                ia, ib = idx[members[a]], idx[members[b]]
                m[ia][ib] = m[ib][ia] = round(rho, 4)
    return m


def _logit(p: float) -> float:
    p = min(0.999, max(0.001, p))
    return math.log(p / (1 - p))


def _signal_info(signals, weights, prior_logit) -> dict[str, float]:
    """Contribution magnitude per *contributing* detector — the basis for
    ranking which member of a correlated set is the 'primary' one."""
    info: dict[str, float] = {}
    for s in signals:
        w = weights.get(s.name, 0.0)
        if s.confidence <= 0 or w <= 0:
            continue
        p = min(0.98, max(0.02, s.probability))
        info[s.name] = abs(_logit(p) - prior_logit) * s.confidence * w
    return info


class CorrelationModel:
    """One interface, two backings. Construct via :meth:`default` or
    :meth:`from_artifact`; the aggregator only calls ``axis_of`` and
    ``compute_factors``."""

    def __init__(
        self,
        *,
        mode: str,
        groups: dict | None = None,
        detectors: list[str] | None = None,
        matrix: list[list[float]] | None = None,
        strength: float = 0.5,
        floor: float = 0.15,
        axis_threshold: float = 0.5,
        source: str = "default",
        n_observations: int = 0,
    ) -> None:
        self.mode = mode
        self.source = source
        self.groups = groups or {}
        self.detectors = detectors or []
        self.matrix = matrix or []
        self.strength = strength
        self.floor = floor
        self.axis_threshold = axis_threshold
        self.n_observations = n_observations
        self._idx = {d: i for i, d in enumerate(self.detectors)}
        self._axis_cache = self._build_axes()

    # -- construction ------------------------------------------------------

    @classmethod
    def default(cls, settings) -> "CorrelationModel":
        groups: dict[str, dict] = {}
        for axis, g in CORRELATION_GROUPS.items():
            groups[axis] = {
                "members": g["members"],
                "redundancy": float(getattr(settings, g["setting"], 1.0)),
                "label": g["label"],
            }
        return cls(mode="default", groups=groups, source="default")

    @classmethod
    def from_artifact(cls, data: dict) -> "CorrelationModel":
        detectors = list(data["detectors"])
        matrix = [[float(x) for x in row] for row in data["matrix"]]
        if len(matrix) != len(detectors) or any(len(r) != len(detectors) for r in matrix):
            raise ValueError("correlation matrix shape does not match detector list")
        return cls(
            mode="learned",
            detectors=detectors,
            matrix=matrix,
            strength=float(data.get("strength", 0.5)),
            floor=float(data.get("floor", 0.15)),
            axis_threshold=float(data.get("axis_threshold", 0.5)),
            source="learned",
            n_observations=int(data.get("n_observations", 0)),
        )

    # -- axes --------------------------------------------------------------

    def _build_axes(self) -> dict[str, str]:
        if self.mode == "default":
            # Group axes; detectors outside a group are their own axis.
            return {}  # resolved lazily by axis_of via static membership
        # Learned: connected components of the correlation graph at threshold.
        parent = {d: d for d in self.detectors}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        n = len(self.detectors)
        for i in range(n):
            for j in range(i + 1, n):
                if self.matrix[i][j] >= self.axis_threshold:
                    union(self.detectors[i], self.detectors[j])
        return {d: f"axis_{find(d)}" for d in self.detectors}

    def axis_of(self, name: str) -> str:
        if self.mode == "default":
            for axis, group in self.groups.items():
                if name in group["members"]:
                    return axis
            return name
        return self._axis_cache.get(name, name)

    # -- redundancy factors ------------------------------------------------

    def compute_factors(self, signals, weights, prior_logit) -> tuple[dict[str, float], list[str]]:
        info = _signal_info(signals, weights, prior_logit)
        if self.mode == "default":
            return self._factors_default(info)
        return self._factors_learned(info)

    def _factors_default(self, info: dict[str, float]) -> tuple[dict[str, float], list[str]]:
        factors = {name: 1.0 for name in info}
        notes: list[str] = []
        for group in self.groups.values():
            present = [n for n in info if n in group["members"]]
            if len(present) <= 1:
                continue
            r = group["redundancy"]
            if r >= 1.0:
                continue
            ranked = sorted(present, key=lambda n: info[n], reverse=True)
            discounted = []
            for rank, name in enumerate(ranked):
                if rank == 0:
                    continue
                factors[name] = r ** rank
                discounted.append(name)
            if discounted:
                notes.append(
                    f"Discounted overlapping {group['label']} evidence "
                    f"({', '.join(discounted)}) so correlated detectors aren't "
                    f"counted as independent corroboration."
                )
        return factors, notes

    def _factors_learned(self, info: dict[str, float]) -> tuple[dict[str, float], list[str]]:
        factors = {name: 1.0 for name in info}
        notes: list[str] = []
        ranked = sorted(info, key=lambda n: info[n], reverse=True)
        counted: list[str] = []
        discounted: list[str] = []
        for name in ranked:
            if name not in self._idx:
                counted.append(name)
                continue
            disc = 1.0
            for j in counted:
                if j not in self._idx:
                    continue
                rho = self.matrix[self._idx[name]][self._idx[j]]
                if rho > 0:
                    disc *= (1.0 - rho * self.strength)
            factor = max(self.floor, disc)
            factors[name] = factor
            if factor < 0.999:
                discounted.append(name)
            counted.append(name)
        if discounted:
            notes.append(
                f"Discounted correlated detectors ({', '.join(discounted)}) using "
                f"the fitted signal-correlation model (n={self.n_observations}) so "
                f"overlapping evidence isn't counted as independent."
            )
        return factors, notes


# ---------------------------------------------------------------------------
# Runtime loading
#
# The default model is cheap to build (a few dicts) so we build it per call,
# which keeps Settings-tunable redundancy factors live. The learned artifact is
# parsed from disk and cached by (path, mtime) so edits are picked up but reads
# are not repeated on every scan.
# ---------------------------------------------------------------------------


@lru_cache(maxsize=8)
def _load_artifact(path: str, mtime: float) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:  # noqa: BLE001
        _log.warning("failed to load correlation artifact %s: %s", path, e)
        return None


def get_correlation_model(settings) -> CorrelationModel:
    path = getattr(settings, "correlation_model_path", None)
    if path and os.path.exists(path):
        try:
            data = _load_artifact(path, os.path.getmtime(path))
            if data:
                return CorrelationModel.from_artifact(data)
        except Exception as e:  # noqa: BLE001
            _log.warning("correlation artifact %s invalid, using default model: %s", path, e)
    return CorrelationModel.default(settings)
