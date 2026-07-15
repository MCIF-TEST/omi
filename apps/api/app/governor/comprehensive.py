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


def _domain_shape_errors(obj: dict, section_keys: Sequence[str]) -> list[str]:
    """Gate the six per-domain sections' SHAPE: each must be present and be an object with a non-empty
    ``assessment`` string (``citations``, when present, an array). This makes a missing / malformed /
    empty domain a canonical-validation FAILURE (→ deterministic Floor), not a silently-recorded one."""
    errors: list[str] = []
    for key in section_keys:
        if key not in obj:
            errors.append(f"missing required reasoning domain: {key}")
            continue
        val = obj.get(key)
        if not isinstance(val, dict):
            errors.append(f"{key}: reasoning domain must be an object")
            continue
        assessment = val.get("assessment")
        if not (isinstance(assessment, str) and assessment.strip()):
            errors.append(f"{key}: 'assessment' must be a non-empty string")
        cits = val.get("citations")
        if cits is not None and not isinstance(cits, list):
            errors.append(f"{key}: 'citations' must be an array")
    return errors


def validate_comprehensive_model_output(
    obj: Any, *, schema: dict, section_keys: Sequence[str],
) -> list[str]:
    """Validate a comprehensive MODEL response against the ONE canonical comprehensive-assessment schema.

    Returns a list of human-readable errors; empty == valid. This is the single canonical parser/validator
    for the model's output: it validates the Lead-Investigator synthesis wrapper + required top-level
    fields + ``additionalProperties: false`` against the supplied canonical ``schema`` (reusing the wrapper
    validator, so the evidence-item, counter-evidence (F5), and banned-phrase doctrine still apply), and it
    gates the SHAPE of the six first-class reasoning domains. It does NOT require the Omi-owned
    provenance/subject, the echoed engine numbers, or corroboration — the canonical schema already omits
    those from ``required`` (OmiSphere injects/overlays them after validation). Never raises."""
    if not isinstance(obj, dict):
        return ["response is not a JSON object"]
    errors: list[str] = []
    try:
        from omi_analyst.schema_validate import validate_analyst_response

        errors.extend(validate_analyst_response(obj, schema=schema))
    except Exception as exc:  # noqa: BLE001 — validator unreachable is itself a hard validation failure
        errors.append(f"canonical validator unavailable: {type(exc).__name__}")
    errors.extend(_domain_shape_errors(obj, section_keys))
    # de-dupe, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for e in errors:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


__all__ = ["validate_comprehensive_sections", "validate_comprehensive_model_output"]
