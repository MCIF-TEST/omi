"""Project existing OmiSphere engine outputs into the Evidence Bundle (spec Appendix A).

A faithful, structured, read-only projection of what the engine ALREADY computed —
never a recomputation. Inputs are the engine's serialized dicts (the same shapes
``app/reasoning/commentary.py`` consumes), so this module imports nothing from
``apps/api`` and changes no detector / scoring / OmiScore logic.

Each ``project_*`` returns a plain JSON-serializable bundle dict keyed by the
Appendix-A sections relevant to that grain.
"""
from __future__ import annotations

from typing import Any

DISCRIMINATIVE_METHODS = {"fingerprint_cluster", "co_engagement", "co_tag"}


# --------------------------------------------------------------------------- #
# Shared section projectors
# --------------------------------------------------------------------------- #
def _subject(grain: str, ref: str, platform: str) -> dict[str, Any]:
    plat = platform if platform in ("youtube", "twitter", "unknown") else "unknown"
    return {"grain": grain, "ref": ref, "platform": plat}


def _signals(scan: dict) -> list[dict[str, Any]]:
    out = []
    for s in scan.get("signals") or []:
        out.append({
            "name": s.get("name", "?"),
            "probability": float(s.get("probability") or 0.0),
            "confidence": float(s.get("confidence") or 0.0),
            "evidence": list(s.get("evidence") or [])[:5],
            "supplemental": bool(s.get("supplemental", False)),
        })
    return out


def _contributions(scan: dict) -> list[dict[str, Any]]:
    out = []
    for c in scan.get("contributions") or []:
        out.append({
            "name": c.get("name", "?"),
            "impact": float(c.get("impact") or 0.0),
            "logit_delta": float(c.get("logit_delta") or 0.0),
            "direction": c.get("direction", "neutral"),
            "decorrelation_factor": float(c.get("decorrelation_factor") or 1.0),
            "supplemental": bool(c.get("supplemental", False)),
            "headline": c.get("headline") or "",
            "evidence": c.get("evidence") or "",
        })
    return out


def _headline_scores(scan: dict) -> dict[str, Any]:
    return {
        "overall_probability": float(scan.get("overall_probability") or 0.0),
        "tier": scan.get("tier") or "low",
        "confidence": float(scan.get("confidence") or 0.0),
        "summary": (scan.get("summary") or "")[:600],
    }


def _score_breakdown(scan: dict) -> dict[str, Any]:
    sb = scan.get("score_breakdown") or {}
    return {
        "single_axis_capped": bool(sb.get("single_axis_capped", False)),
        "convergence_bonus_logit": float(sb.get("convergence_bonus_logit") or 0.0),
        "posterior_logit": sb.get("posterior_logit"),
        "final_probability": sb.get("final_probability"),
    }


def _intelligence(scan: dict) -> dict[str, Any] | None:
    intel = scan.get("intelligence") or scan.get("omiscore")
    if not isinstance(intel, dict):
        return None
    return {
        "authenticity_score": intel.get("authenticity_score"),
        "risk_level": intel.get("risk_level"),
        "dimensions": [
            {"name": d.get("name"), "score": d.get("score")}
            for d in (intel.get("dimensions") or [])
        ][:8],
        "top_evidence": list(intel.get("top_evidence") or [])[:5],
    }


def _coordination(scan: dict) -> dict[str, Any] | None:
    coord = scan.get("coordination")
    if not isinstance(coord, dict):
        return None
    clusters = []
    methods: list[str] = list(coord.get("methods") or [])
    for cl in coord.get("clusters") or []:
        m = cl.get("method")
        if m and m not in methods:
            methods.append(m)
        clusters.append({
            "method": m,
            "members": cl.get("members") or cl.get("member_count"),
            "score": cl.get("score"),
            "evidence": list(cl.get("evidence") or [])[:4],
        })
    return {
        "coordination_score": coord.get("coordination_score") or coord.get("score"),
        "methods": methods,
        "clusters": clusters,
        "coordination_label": coord.get("coordination_label"),
        "single_axis_capped": bool(coord.get("single_axis_capped", False)),
        "convergence": bool(coord.get("convergence", False)),
    }


# --------------------------------------------------------------------------- #
# Grain bundles
# --------------------------------------------------------------------------- #
def project_account_bundle(
    *, ref: str, platform: str, scan: dict,
    memory: dict | None = None, trend: dict | None = None,
) -> dict[str, Any]:
    bundle: dict[str, Any] = {
        "subject": _subject("account", ref, platform),
        "headline_scores": _headline_scores(scan),
        "signals": _signals(scan),
        "contributions": _contributions(scan),
        "score_breakdown": _score_breakdown(scan),
        "reasons": list(scan.get("reasons") or [])[:8],
        "weak_signals": list(scan.get("weak_signals") or [])[:6],
        "score_adjustments": list(scan.get("score_adjustments") or [])[:6],
    }
    intel = _intelligence(scan)
    if intel:
        bundle["intelligence"] = intel
    coord = _coordination(scan)
    if coord:
        bundle["coordination"] = coord
    if memory:
        bundle["memory"] = {"matched_prior_neighbors": list(memory.get("neighbors") or [])[:5]}
    if trend:
        bundle["trend"] = {
            "direction": trend.get("direction"),
            "summary": (trend.get("summary") or "")[:200],
            "scan_count": trend.get("scan_count"),
        }
    return bundle


def project_campaign_bundle(*, ref: str, platform: str, campaign: dict) -> dict[str, Any]:
    members = campaign.get("members") or []
    member_auth = [m.get("authenticity_score") for m in members if m.get("authenticity_score") is not None]
    bundle: dict[str, Any] = {
        "subject": _subject("campaign", ref, platform),
        "campaign": {
            "coordination_score": float(campaign.get("coordination_score") or 0.0),
            "member_count": campaign.get("member_count") or len(members),
            "methods": list(campaign.get("methods") or []),
            "hashtags": list(campaign.get("hashtags") or [])[:10],
            "coordination_label": campaign.get("coordination_label"),
            "mean_member_authenticity": (
                round(sum(member_auth) / len(member_auth), 3) if member_auth else None
            ),
        },
        "coordination": _coordination(campaign) or {
            "coordination_score": float(campaign.get("coordination_score") or 0.0),
            "methods": list(campaign.get("methods") or []),
            "clusters": [],
            "coordination_label": campaign.get("coordination_label"),
            "single_axis_capped": bool(campaign.get("single_axis_capped", False)),
            "convergence": bool(campaign.get("convergence", False)),
        },
        "score_breakdown": {"single_axis_capped": bool(campaign.get("single_axis_capped", False))},
        "weak_signals": list(campaign.get("weak_signals") or [])[:6],
    }
    return bundle


def project_narrative_bundle(*, ref: str, platform: str, narrative: dict) -> dict[str, Any]:
    return {
        "subject": _subject("narrative", ref, platform),
        "narrative": {
            "label": (narrative.get("label") or "")[:300],
            "member_count": narrative.get("member_count") or 0,
            "distinct_authors": narrative.get("distinct_authors") or 0,
            "spread_ratio": float(narrative.get("spread_ratio") or 0.0),
            "inauthenticity_score": float(narrative.get("inauthenticity_score") or 0.0),
            "coordination_label": narrative.get("coordination_label") or narrative.get("risk_label"),
            "signals": dict(narrative.get("signals") or {}),
            "narrative_corroboration": narrative.get("narrative_corroboration"),
            "sample_texts": [str(t)[:200] for t in (narrative.get("sample_texts") or [])[:6]],
        },
        "score_breakdown": {"single_axis_capped": bool(narrative.get("single_axis_capped", False))},
        "weak_signals": list(narrative.get("weak_signals") or [])[:6],
    }


def project_investigation_bundle(
    *, ref: str, platform: str, scan: dict | None = None,
    components: list[dict] | None = None, cross_links: list[Any] | None = None,
) -> dict[str, Any]:
    """Investigation Summary bundle (grain ``comment_section``) — the scan-level roll-up.

    ``components`` is a compact list of the constituent sub-assessments
    ({grain, ref, verdict, suspicion_tier, suspicion_probability, headline}) so the
    summary can synthesize across the account/campaign/narrative reads.
    """
    scan = scan or {}
    bundle: dict[str, Any] = {
        "subject": _subject("comment_section", ref, platform),
        "headline_scores": _headline_scores(scan) if scan else {
            "overall_probability": 0.0, "tier": "low", "confidence": 0.0, "summary": "",
        },
        "weak_signals": list(scan.get("weak_signals") or [])[:6],
        "components": components or [],
        "cross_links": list(cross_links or [])[:10],
    }
    coord = _coordination(scan) if scan else None
    if coord:
        bundle["coordination"] = coord
    if scan.get("contributions"):
        bundle["contributions"] = _contributions(scan)
    return bundle
