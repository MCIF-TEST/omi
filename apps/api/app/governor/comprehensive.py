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

import logging
from typing import Any, Sequence

logger = logging.getLogger("omi.governor.comprehensive")

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


# A representative OMI score for each verdict, used ONLY as a fallback when the model commits to a verdict
# but omits the numeric omi_score. Each value sits squarely inside the verdict's tier band so the derived
# score and any derived tier agree with the model's own categorical call.
_VERDICT_TO_SCORE = {
    "confirmed_bot_ring": 90,
    "likely_inauthentic": 72,
    "mixed": 50,
    "inconclusive": 40,
    "likely_authentic": 12,
}


# A representative score inside each tier band — used only to backfill a per-account omi_score when the
# model gave the tier but not the number.
_TIER_MIDPOINT = {"low": 12, "moderate": 37, "elevated": 62, "high": 87}


def _tier_for_score(score: int) -> str:
    """The canonical omi_score→suspicion_tier bands (mirrors the engine cutoffs 0.25/0.50/0.75)."""
    if score < 25:
        return "low"
    if score < 50:
        return "moderate"
    if score < 75:
        return "elevated"
    return "high"


def _verdict_for_score(score: int) -> str:
    """A conservative omi_score→verdict mapping, used only to derive the executive verdict from the
    model's OWN per-account scores when it omitted the wrapper (never over-accuses on a derivation)."""
    if score >= 75:
        return "likely_inauthentic"
    if score >= 50:
        return "mixed"
    if score >= 25:
        return "inconclusive"
    return "likely_authentic"


def coerce_comprehensive_model_output(
    obj: Any, *, schema: dict, section_keys: Sequence[str],
) -> Any:
    """Best-effort STRUCTURAL normalization so a good-faith model reply RENDERS instead of floorng on a
    harmless deviation. AI-first doctrine: be liberal in what we accept from the model.

    This repairs SHAPE only — it never invents the analytical substance. The model MUST still supply the
    core it alone can produce (``verdict``, ``omi_score``, ``headline``, ``assessment``); if any of those
    is missing the object still fails validation downstream and the deterministic Floor stands in. What we
    DO fix are the mechanical mismatches that otherwise waste a real inference:

    * drop unknown top-level keys (the model loves to add ``summary``/``notes`` — ``additionalProperties:
      false`` would otherwise reject the whole object);
    * ensure each of the six reasoning domains is an object with a non-empty ``assessment`` (a bare string
      is wrapped; a missing/empty one becomes an explicit "not provided" marker — honest, not invented);
    * coerce the evidence arrays to lists and DROP malformed items (missing signal/claim/refs) rather than
      fail the whole response;
    * guarantee the required non-empty list fields (``uncertainty`` / ``what_would_change_this``);
    * satisfy the F5 counter-evidence rule when ``evidence_against`` is legitimately empty;
    * clamp ``omi_score`` to an int in [0,100] and derive ``suspicion_tier`` / default ``confidence_band``
      when absent;
    * default the boilerplate scalar fields (``confidence_rationale`` / ``limits_statement``).

    Returns the coerced object (a new dict); non-dict input is returned unchanged."""
    if not isinstance(obj, dict):
        return obj
    props: dict = schema.get("properties", {})
    # Envelope unwrap: some models wrap the whole assessment in one top-level key (e.g.
    # {"investigation": {…}} / {"result": {…}}). If unwrapping the single dict value exposes materially
    # more schema fields, do it so the real assessment isn't discarded by the additionalProperties filter.
    if len(obj) == 1:
        _inner = next(iter(obj.values()))
        if isinstance(_inner, dict) and sum(k in props for k in _inner) > sum(k in props for k in obj):
            obj = _inner
    out: dict = {k: v for k, v in obj.items() if k in props}  # additionalProperties: false — drop unknowns

    for key in section_keys:
        sec = out.get(key)
        if isinstance(sec, str):                              # a bare string → wrap it
            sec = {"assessment": sec}
        if not isinstance(sec, dict):
            sec = {}
        else:
            sec = dict(sec)
        if not (isinstance(sec.get("assessment"), str) and sec["assessment"].strip()):
            sec["assessment"] = "No specific reasoning was provided for this domain."
        if sec.get("citations") is not None and not isinstance(sec.get("citations"), list):
            sec.pop("citations", None)
        out[key] = sec

    for arr_key in ("evidence_for", "evidence_against"):
        if arr_key not in out:
            continue
        arr = out.get(arr_key)
        if not isinstance(arr, list):
            out[arr_key] = []
            continue
        clean: list[dict] = []
        for item in arr:
            if not isinstance(item, dict):
                continue
            signal = str(item.get("signal", "")).strip()
            claim = str(item.get("claim", "")).strip()
            refs = item.get("evidence_refs")
            refs = [str(r) for r in refs if str(r).strip()] if isinstance(refs, list) else []
            if signal and claim and refs:                     # keep only well-formed items (F1)
                keep = {"signal": signal, "claim": claim, "evidence_refs": refs}
                for opt in ("direction", "impact"):
                    if opt in item:
                        keep[opt] = item[opt]
                clean.append(keep)
        out[arr_key] = clean

    # Per-account items: each needs a ref, an omi_score (0-100), a tier, and an assessment. Coerce the
    # shape so a good-faith reply renders EVERY account it named: clamp the score; derive tier↔score when
    # one is missing; and when the model gave a per-account item with a ref + assessment but no usable
    # number, KEEP it and backfill the score from the overall read (a per-account judgment the model
    # actually wrote should never be silently dropped — that showed up as "0 of N assessed"). Only an item
    # with no usable ref is discarded. commenter_assessments is optional, so this never floors.
    _overall = out.get("omi_score")
    try:
        _overall = max(0, min(100, int(round(float(_overall))))) if _overall is not None else None
    except (TypeError, ValueError):
        _overall = None
    ca = out.get("commenter_assessments")
    if isinstance(ca, list):
        # Everything the item schema declares beyond the load-bearing four rides through untouched.
        #
        # This was a hardcoded allow-list, and that made it a silent field shredder: any property
        # added to the per-account schema afterwards reached this function and left it deleted. That
        # is exactly what happened to `signals` and `confidence` — the model returned all eight
        # scored dimensions, this dropped them on the floor, and every account rendered eight "n/a"
        # rows with nothing failing anywhere to say so. Driving the passthrough off the schema means
        # the next field added does not depend on anyone remembering this line.
        #
        # Passing through raw is safe because these are declared properties (so the
        # additionalProperties filter downstream still accepts the object) and because the values
        # are normalised later: analyst._normalise_signals rebuilds the eight in canonical order from
        # whatever arrived, and _clamp_int bounds the confidence.
        _COERCED_HERE = ("ref", "omi_score", "suspicion_tier", "assessment", "citations")
        _item_props: dict = (
            ((props.get("commenter_assessments") or {}).get("items") or {}).get("properties") or {}
        )
        _passthrough = tuple(k for k in _item_props if k not in _COERCED_HERE)
        clean_ca: list[dict] = []
        for item in ca:
            if not isinstance(item, dict):
                continue
            ref = str(item.get("ref", "")).strip()
            if not ref:
                continue
            score = item.get("omi_score")
            try:
                score = max(0, min(100, int(round(float(score))))) if score is not None else None
            except (TypeError, ValueError):
                score = None
            tier = item.get("suspicion_tier")
            if score is None and tier in _TIER_MIDPOINT:
                score = _TIER_MIDPOINT[tier]
            if score is None:                                     # keep the account; inherit the overall read
                score = _overall if _overall is not None else 40
            if tier not in ("low", "moderate", "elevated", "high"):
                tier = _tier_for_score(score)
            assessment = item.get("assessment")
            if not (isinstance(assessment, str) and assessment.strip()):
                assessment = "No account-specific reasoning was provided."
            keep = {"ref": ref, "omi_score": score, "suspicion_tier": tier, "assessment": assessment}
            if isinstance(item.get("citations"), list):
                keep["citations"] = item["citations"]
            for _k in _passthrough:
                if _k in item:
                    keep[_k] = item[_k]
            clean_ca.append(keep)
        out["commenter_assessments"] = clean_ca

    for arr_key in ("uncertainty", "what_would_change_this"):
        arr = out.get(arr_key)
        if not (isinstance(arr, list) and any(str(x).strip() for x in arr)):
            out[arr_key] = ["Not specified by the analyst."]

    if isinstance(out.get("evidence_against"), list) and len(out["evidence_against"]) == 0:
        rationale = str(out.get("confidence_rationale", "")).strip()
        if "no exculpat" not in rationale.lower() and "no counter" not in rationale.lower():
            out["confidence_rationale"] = f"{rationale} No exculpatory signal was present.".strip()

    if "omi_score" in out:
        try:
            out["omi_score"] = max(0, min(100, int(round(float(out["omi_score"])))))
        except (TypeError, ValueError):
            out.pop("omi_score", None)                            # non-numeric → treat as absent (derive below)
    # If the model omitted the numeric OMI score but DID commit to a verdict, derive a representative score
    # from ITS OWN verdict (not the deterministic engine) so a complete, verdict-bearing reply still renders
    # instead of floorng. Some models reliably produce the categorical verdict + prose but drop the number;
    # this keeps the score AI-consistent rather than inventing an unrelated value.
    if not isinstance(out.get("omi_score"), int):
        derived = _VERDICT_TO_SCORE.get(str(out.get("verdict", "")).strip().lower())
        if derived is not None:
            out["omi_score"] = derived
    # WRAPPER SALVAGE — some models produce the substantive PER-ACCOUNT output but omit the executive
    # wrapper (verdict/omi_score/headline/assessment). Rather than discard real per-account AI work, derive
    # the overall read from the model's OWN per-account scores so the response renders. Gated on actually
    # having per-account results — a genuinely empty reply still floors. These are honest derivations /
    # factual summaries of the model's output, not invented analysis.
    _ca_final = out.get("commenter_assessments")
    _ca_scores = ([c["omi_score"] for c in _ca_final
                   if isinstance(c, dict) and isinstance(c.get("omi_score"), int)]
                  if isinstance(_ca_final, list) else [])
    _verdict_enum_l = [str(v).lower() for v in props.get("verdict", {}).get("enum", [])]
    if _ca_scores and not isinstance(out.get("omi_score"), int):
        # Reflect the most-suspicious accounts without letting a single account dominate: the mean of the
        # worse half of the per-account scores.
        _worse = sorted(_ca_scores, reverse=True)[: (len(_ca_scores) + 1) // 2]
        out["omi_score"] = max(0, min(100, int(round(sum(_worse) / len(_worse)))))
    if _ca_scores and isinstance(out.get("omi_score"), int) and (
            str(out.get("verdict", "")).strip().lower() not in _verdict_enum_l
            or not str(out.get("headline", "")).strip()
            or not str(out.get("assessment", "")).strip()):
        if str(out.get("verdict", "")).strip().lower() not in _verdict_enum_l:
            out["verdict"] = _verdict_for_score(out["omi_score"])
        _n = len(_ca_scores)
        _flagged = sum(1 for s in _ca_scores if s >= 50)
        if not str(out.get("headline", "")).strip():
            out["headline"] = (f"Assessed {_n} account{'' if _n == 1 else 's'}; "
                               f"{_flagged} at elevated risk or higher.")
        if not str(out.get("assessment", "")).strip():
            out["assessment"] = ("Overall read derived from the individual account assessments below — "
                                 "see each account for its reasoning.")
        for _ek in ("evidence_for", "evidence_against"):
            if not isinstance(out.get(_ek), list):
                out[_ek] = []
        logger.info("coerce: synthesized the executive wrapper from %d per-account results "
                    "(the model omitted it) — check the OpenRouter preset is current", _n)
    tier_enum = props.get("suspicion_tier", {}).get("enum", [])
    if isinstance(out.get("omi_score"), int) and out.get("suspicion_tier") not in tier_enum:
        out["suspicion_tier"] = _tier_for_score(out["omi_score"])
    band_enum = props.get("confidence_band", {}).get("enum", [])
    if band_enum and out.get("confidence_band") not in band_enum:
        out["confidence_band"] = "moderate" if "moderate" in band_enum else band_enum[0]

    if not str(out.get("confidence_rationale", "")).strip():
        out["confidence_rationale"] = (
            "Confidence reflects the strength and convergence of the available evidence.")
    if not str(out.get("limits_statement", "")).strip():
        out["limits_statement"] = (
            "This is a probabilistic assessment; the human analyst sets the final verdict.")
    return out


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


__all__ = [
    "validate_comprehensive_sections",
    "validate_comprehensive_model_output",
    "coerce_comprehensive_model_output",
]
