"""Deterministic replay (Sprint 007) — engineering + evaluation only.

Given the same inputs — Evidence Bundle (re-bound from the stored payload), Memory revision,
and Model revision — re-run the shadow pipeline and compare to a previously stored
``ShadowReport``. The deterministic production path **must** reproduce bit-for-bit (same
bundle ⇒ same assessment + same ``ValidationTrace`` id). The shadow path reproduces exactly
under a deterministic provider (or the deterministic fallback); under a *live* model it may
drift, which is precisely what replay surfaces — drift is attributable to a changed model or
memory revision, never to nondeterminism in the architecture.
"""
from __future__ import annotations

from typing import Any

from .runner import run_shadow

_CATEGORICAL = ("verdict", "suspicion_tier", "confidence_band", "coordination_label")


def _diff(previous: dict, current: dict) -> dict:
    """Categorical fields that changed between two assessments (previous → current)."""
    return {
        f: {"previous": previous.get(f), "current": current.get(f)}
        for f in _CATEGORICAL if previous.get(f) != current.get(f)
    }


def replay(
    payload: dict, *, previous: Any, ref: str, platform: str = "youtube",
    grain: str = "comment_section", settings: Any | None = None,
    store: Any = None, now: Any = None, provider: Any = None,
) -> dict:
    """Re-run the shadow pipeline and compare to ``previous`` (a ``ShadowReport`` or its dict).

    Returns a replay result: whether each path reproduced, whether the pinned inputs matched
    (bundle / memory / model revision), and any drift. Determinism guarantee: the production
    path reproduces whenever the bundle id matches; the shadow path reproduces under a
    deterministic provider."""
    prev = previous.to_dict() if hasattr(previous, "to_dict") else dict(previous)
    current = run_shadow(
        payload, ref=ref, platform=platform, grain=grain,
        settings=settings, store=store, now=now, provider=provider,
    )

    same_inputs = {
        "bundle_id": current.bundle_id == prev["bundle_id"],
        "memory_revision": current.memory_revision == prev["memory_revision"],
        "model_revision": current.model_revision == prev["model_revision"],
    }
    production_reproduced = (
        same_inputs["bundle_id"]
        and current.production["assessment"] == prev["production"]["assessment"]
        and current.production["trace"]["trace_id"] == prev["production"]["trace"]["trace_id"]
    )
    shadow_reproduced = (
        current.shadow["assessment"] == prev["shadow"]["assessment"]
        and current.shadow["trace"]["trace_id"] == prev["shadow"]["trace"]["trace_id"]
    )

    drift: dict = {}
    if not production_reproduced:
        drift["production"] = _diff(prev["production"]["assessment"], current.production["assessment"])
    if not shadow_reproduced:
        drift["shadow"] = _diff(prev["shadow"]["assessment"], current.shadow["assessment"])

    return {
        "reproduced": production_reproduced and shadow_reproduced,
        "production_reproduced": production_reproduced,
        "shadow_reproduced": shadow_reproduced,
        "same_inputs": same_inputs,
        "drift": drift,
        "current": current.to_dict(),
    }
