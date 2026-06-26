"""The Shadow Mode runner (Sprint 007).

Runs **both** councils over the same investigation and produces a single ``ShadowReport``:

1. the **deterministic** council result (the production path — what the user receives),
2. the **AI-backed** council result (shadow — for evaluation only),
3. the **Constitutional Governor** outcome on each (mandatory on both paths),
4. the deterministic **comparison artifact**.

The two councils are identical except the Behavior Analyst (deterministic vs AI-backed), so
the comparison isolates exactly one variable: *does AI behavioral reasoning change the read?*
The production result is never affected by the shadow run, and — per the runtime requirement —
when no live endpoint is configured the AI council's RemoteAnalyst simply falls back to the
deterministic analyst, so Shadow Mode stays fully operational with or without a model.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.evidence.bundle import digest

from app.reasoning.orchestrator import (
    BehaviorAnalyst,
    CounterEvidenceAnalyst,
    MemoryAnalyst,
    Orchestrator,
    RemoteAnalyst,
    ai_behavior_analyst,
    build_council,
)

from .compare import compare, council_view


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def memory_revision(store: Any) -> str:
    """A deterministic version stamp of the memory state used for a run — so replay can pin
    (Evidence Bundle + Memory revision + Model revision)."""
    if store is None:
        return "none"
    objs = sorted(store.all(include_superseded=True), key=lambda k: k.id)
    core = [
        {"id": k.id, "sig": sorted(k.signature), "obs": len(k.ledger), "superseded_by": k.superseded_by}
        for k in objs
    ]
    return digest(core, prefix="mem:")


def _deterministic_council(store: Any, now: Any) -> list:
    council = [BehaviorAnalyst()]
    if store is not None:
        council.append(MemoryAnalyst(store, now=now))
    council.append(CounterEvidenceAnalyst())
    return council


def _ai_council(provider: Any, store: Any, now: Any) -> list:
    council = [ai_behavior_analyst(provider, store=store, now=now)]
    if store is not None:
        council.append(MemoryAnalyst(store, now=now))
    council.append(CounterEvidenceAnalyst())
    return council


def _collect_diagnostics(shadow_modules: list, wall_ms: float) -> dict:
    """Pull the AI specialist's telemetry (mode, latency, attempts, fallback reason) out of
    the shadow council. ``ai_mode`` is one of ``ai`` | ``fallback`` | ``deterministic``."""
    ai = [m.last_diagnostics for m in shadow_modules if isinstance(m, RemoteAnalyst)]
    d = ai[0] if ai else {"mode": "deterministic", "provider": "none"}
    detail = str(d.get("detail", ""))
    return {
        "ai_mode": d.get("mode", "deterministic"),
        "provider": d.get("provider", "none"),
        "latency_ms": d.get("latency_ms"),
        "attempts": d.get("attempts"),
        "fallback_reason": d.get("reason"),
        "citation_failure": "fabricated" in detail,
        "wall_ms": round(wall_ms, 2),
    }


@dataclass
class ShadowReport:
    """One investigation's full shadow evaluation — replayable, serializable, persistable."""

    bundle_id: str
    memory_revision: str
    model_revision: str | None
    production: dict
    shadow: dict
    comparison: dict
    diagnostics: dict
    inputs: dict
    generated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)


def run_shadow(
    payload: dict, *, ref: str, platform: str = "youtube", grain: str = "comment_section",
    settings: Any | None = None, store: Any = None, now: Any = None, provider: Any = None,
) -> ShadowReport:
    """Run the deterministic + AI-backed councils over ``payload`` and build the comparison.

    ``provider`` (optional) injects an explicit reasoning provider for the shadow council;
    otherwise the council is assembled from settings (``build_council``) — AI-backed when an
    endpoint is configured, deterministic-fallback otherwise. The production result is always
    the deterministic council."""
    if settings is None:
        from app.core.config import get_settings
        settings = get_settings()

    prod_modules = _deterministic_council(store, now)
    if provider is not None:
        shadow_modules = _ai_council(provider, store, now)
    else:
        shadow_modules = build_council(settings, store=store, now=now)

    prod_result = Orchestrator(modules=prod_modules).run(payload, ref=ref, platform=platform, grain=grain)
    t0 = time.perf_counter()
    shadow_result = Orchestrator(modules=shadow_modules).run(payload, ref=ref, platform=platform, grain=grain)
    wall_ms = (time.perf_counter() - t0) * 1000.0

    production = council_view(prod_result)
    shadow = council_view(shadow_result)
    return ShadowReport(
        bundle_id=shadow_result.bundle_id,
        memory_revision=memory_revision(store),
        model_revision=getattr(settings, "analyst_hf_revision", None),
        production=production,
        shadow=shadow,
        comparison=compare(production, shadow),
        diagnostics=_collect_diagnostics(shadow_modules, wall_ms),
        inputs={"ref": ref, "platform": platform, "grain": grain},
    )
