"""Governor extension for the comprehensive single-inference response — STRUCTURAL validation only.

The comprehensive investigation response is the Lead-Investigator synthesis wrapper (validated by the
constitutional :class:`~app.governor.governor.Governor` exactly as every other stage) PLUS six
per-domain reasoning sidecars. This module adds the ONLY new Governor capability the single-inference
architecture needs: **structural validation + citation resolution** of those six sidecars. It does NOT
reason, score, or repair; it does not move the served verdict (the wrapper Governor remains the gate for
the served ruling). It reports which sidecars are well-formed and which citations resolve against the
investigation's evidence universe (the stable evidence index + the reversible alias legend + the
governance bundle's ``ev:`` ids), so the presentation layer can surface only resolved citations.
"""
from __future__ import annotations

from typing import Any, Sequence

_SECTION_SHAPE = "object with a string 'assessment' and an optional 'citations' array"


def _citation_universe(evidence_index: Sequence[str], legend: dict | None) -> set[str]:
    """The set of citation tokens a sidecar may reference — every stable evidence ref plus every alias
    in the reversible legend. (The governance bundle's ``ev:`` ids are resolved separately, live.)"""
    universe: set[str] = set(evidence_index or ())
    for kind in ("accounts", "clusters", "narratives"):
        universe |= set((legend or {}).get(kind, {}).keys())
    return universe


def _resolves(cit: str, universe: set[str], gov_bundle: Any) -> bool:
    if cit in universe:
        return True
    if gov_bundle is not None:
        try:
            return bool(gov_bundle.resolve(cit))
        except Exception:  # noqa: BLE001 — a resolver error is a non-resolution, never a crash
            return False
    return False


def validate_comprehensive_sections(
    raw_obj: dict | None,
    *,
    section_keys: Sequence[str],
    evidence_index: Sequence[str],
    legend: dict | None = None,
    gov_bundle: Any = None,
) -> dict:
    """Structurally validate the six per-domain reasoning sidecars and resolve their citations.

    Returns a deterministic report: per-section presence + shape + citation resolution, and an overall
    ``structurally_valid`` flag (every required section present and well-formed). Never raises; a
    missing/malformed section is reported, not thrown. This is validation, not reasoning — it changes no
    number and rejects no served ruling.
    """
    obj = raw_obj if isinstance(raw_obj, dict) else {}
    universe = _citation_universe(evidence_index, legend)
    sections: dict[str, dict] = {}
    unresolved_total = 0
    all_ok = True
    for key in section_keys:
        val = obj.get(key)
        present = key in obj
        shape_ok = isinstance(val, dict) and isinstance(val.get("assessment"), str) and bool(
            val.get("assessment", "").strip())
        cits = list(val.get("citations") or []) if isinstance(val, dict) else []
        cits = [str(c) for c in cits]
        unresolved = [c for c in cits if not _resolves(c, universe, gov_bundle)]
        resolved = [c for c in cits if c not in unresolved]
        unresolved_total += len(unresolved)
        section_ok = present and shape_ok
        all_ok = all_ok and section_ok
        sections[key] = {
            "present": present, "shape_ok": shape_ok, "expected_shape": _SECTION_SHAPE,
            "citation_count": len(cits), "resolved": resolved, "unresolved": unresolved,
        }
    return {
        "structurally_valid": all_ok,
        "sections": sections,
        "citation_universe_size": len(universe),
        "unresolved_total": unresolved_total,
        "missing_sections": [k for k in section_keys if k not in obj],
    }


__all__ = ["validate_comprehensive_sections"]
