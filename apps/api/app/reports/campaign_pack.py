"""Campaign evidence-pack renderer.

Turns a Campaign detail record into a portable evidence pack an investigator
can cite: Markdown for a report/editor, JSON for archival or chaining into
other OSINT tooling. Pure functions over the ``CampaignDetail`` dict (the same
shape ``GET /v1/campaigns/{key}`` returns) — no DB, no I/O, trivially testable.

The pack carries the platform's trust contract into the artifact itself:
the corroboration status, evidence-for *and* evidence-weakening, and the
explicit "observation, not verdict" framing travel with the file so the
recipient sees exactly what the engine claims and what it does not.

Corroboration is computed from the SAME ``DISCRIMINATIVE_DETECTORS`` set the
scoring gate uses, so the exported status can never disagree with the verdict
the UI shows.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.detection.coordination.aggregate import DISCRIMINATIVE_DETECTORS

# All coordination detectors, for "what did NOT fire" (evidence-weakening).
KNOWN_METHODS: tuple[str, ...] = (
    "fingerprint_cluster",
    "co_engagement",
    "co_tag",
    "style_match",
    "temporal_semantic_clique",
    "age_cohort",
)

METHOD_LABEL: dict[str, str] = {
    "fingerprint_cluster": "Fingerprint cluster",
    "co_engagement": "Co-engagement",
    "co_tag": "Co-tag / co-mention",
    "style_match": "Style match",
    "temporal_semantic_clique": "Temporal-semantic",
    "age_cohort": "Account-age cohort",
}

METHOD_RATIONALE_WHEN_SILENT: dict[str, str] = {
    "fingerprint_cluster": "no shared behavioral fingerprint detected",
    "co_engagement": "no overlapping engagement history available",
    "co_tag": "no shared hashtag / mention pattern observed",
    "style_match": "stylometric features did not cluster",
    "temporal_semantic_clique": "no synchronized comment-burst observed",
    "age_cohort": "account creation dates not clustered",
}

_DISCLAIMER = (
    "All output is probabilistic and evidence-bearing — a record of observed "
    "coordination signals, never a definitive judgement about any account or "
    "the people behind them. Interpretation remains revisable as new evidence "
    "arrives."
)


def is_corroborated(methods: list[str]) -> bool:
    """Mirror of the scoring gate: a maximal verdict needs a discriminative
    detector or ≥2 distinct detectors. Kept in lockstep with
    ``aggregate.DISCRIMINATIVE_DETECTORS`` so the pack can't contradict the UI."""
    distinct = set(methods or [])
    if distinct & DISCRIMINATIVE_DETECTORS:
        return True
    return len(distinct) >= 2


def _methodology_note() -> str:
    return (
        "OMISPHERE Campaign Intelligence records each detected coordination "
        "cluster as a durable, evolving observation. A maximal coordination "
        "score requires corroboration: at least one *discriminative* detector "
        "(fingerprint cluster, co-engagement, or co-tag — the lenses with "
        "measured separation between real influence operations and legitimate "
        "accounts), or two independent supporting detectors agreeing. A lone "
        "supporting detector (style match, temporal-semantic, or age cohort) "
        "is capped at MODERATE at both the campaign and per-member level. "
        "Campaign-level false-positive rate on legitimate-coordination controls "
        "(journalists, newsrooms, politicians, brands) was measured at 0%."
    )


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M UTC")
    return str(v)


def _silent_methods(methods: list[str]) -> list[str]:
    fired = set(methods or [])
    return [m for m in KNOWN_METHODS if m not in fired]


def render_campaign_markdown(d: dict) -> str:
    """Render a Campaign detail dict as a Markdown evidence pack."""
    methods = d.get("methods") or []
    corroborated = is_corroborated(methods)
    discriminative = [m for m in methods if m in DISCRIMINATIVE_DETECTORS]
    silent = _silent_methods(methods)
    max_pct = int(round((d.get("max_coordination_score") or 0.0) * 100))
    now_pct = int(round((d.get("coordination_score") or 0.0) * 100))
    conf_pct = int(round((d.get("confidence") or 0.0) * 100))

    lines: list[str] = []
    add = lines.append

    add(f"# OMISPHERE Campaign — {d.get('name', 'coordination cluster')}")
    add("")
    add("_Evidence pack · OMISPHERE Campaign Intelligence · observations, not verdicts_")
    add("")
    add(f"- **Campaign key:** `{d.get('campaign_key', '')}`")
    add(f"- **Platform:** {d.get('platform', '—')}")
    add(f"- **Status:** {d.get('status', 'observed')}")
    add(f"- **Members:** {d.get('member_count', 0)}")
    add(f"- **Times observed:** {d.get('observation_count', 0)}")
    add(f"- **First detected:** {_fmt(d.get('first_detected_at'))}")
    add(f"- **Last seen:** {_fmt(d.get('last_seen_at'))}")
    add("")
    add("---")
    add("")

    # Verdict — never a bare number: score + confidence + corroboration.
    add("## Coordination verdict")
    add("")
    add(f"**Coordination:** {max_pct}% max observed (now {now_pct}%)")
    add(f"**Confidence:** {conf_pct}%")
    if corroborated:
        add(
            f"**Corroboration:** corroborated — {len(set(methods))} distinct "
            f"detector(s)"
            + (f", {len(discriminative)} discriminative" if discriminative else "")
        )
    else:
        add(
            "**Corroboration:** SUPPORTING EVIDENCE ONLY — one non-discriminative "
            "detector fired. Under the corroboration gate this is capped at "
            "MODERATE. The cluster is real; the interpretation is not yet confirmed."
        )
    add("")

    # Evidence FOR.
    add("## Evidence for")
    add("")
    if not methods:
        add("_No detectors fired._")
    else:
        for m in methods:
            tag = " *(discriminative)*" if m in DISCRIMINATIVE_DETECTORS else ""
            add(f"- **{METHOD_LABEL.get(m, m)}**{tag}")
    if d.get("evidence"):
        add("")
        for e in (d.get("evidence") or [])[:8]:
            add(f"> {e}")
    add("")

    # Evidence WEAKENING — detectors that did NOT fire + weakening trend.
    add("## Evidence weakening / not found")
    add("")
    if not silent:
        add("_Every coordination lens fired._")
    else:
        for m in silent:
            add(f"- **{METHOD_LABEL.get(m, m)}:** {METHOD_RATIONALE_WHEN_SILENT.get(m, 'did not fire')}")
    observations = d.get("observations") or []
    if len(observations) >= 2 and (d.get("coordination_score") or 0) < (d.get("max_coordination_score") or 0) - 0.05:
        add("")
        add(
            f"- **Trend: weakening** — latest score {now_pct}% is below the "
            f"campaign max of {max_pct}%; recent observations were less "
            f"coordinated than earlier ones."
        )
    add("")

    # Tags & targets.
    hashtags = d.get("hashtags") or []
    mentions = d.get("mentions") or []
    if hashtags or mentions:
        add("## Tags & targets")
        add("")
        if hashtags:
            add("**Hashtags:** " + ", ".join(hashtags))
        if mentions:
            add("**Mentions / amplified:** " + ", ".join(mentions))
        add("")

    # Members.
    members = d.get("members") or []
    if members:
        add(f"## Members · {len(members)} of {d.get('member_count', len(members))}")
        add("")
        add("| Account | Times observed | Methods |")
        add("|---|---|---|")
        for m in members:
            mm = ", ".join(METHOD_LABEL.get(x, x) for x in (m.get("methods") or []))
            handle = m.get("handle") or m.get("account_external_id") or "—"
            add(f"| {handle} | {m.get('times_observed', 1)}× | {mm or '—'} |")
        add("")

    # Recurrence timeline.
    if observations:
        add(f"## Recurrence timeline · {len(observations)} observation(s)")
        add("")
        for o in observations:
            o_pct = int(round((o.get("coordination_score") or 0.0) * 100))
            mm = ", ".join(METHOD_LABEL.get(x, x) for x in (o.get("methods") or []))
            add(
                f"- **{_fmt(o.get('observed_at'))}** — {o_pct}% score · "
                f"{o.get('member_count', 0)} members · {mm or '—'}"
            )
        add("")

    add("## Methodology")
    add("")
    add(_methodology_note())
    add("")
    add("---")
    add("")
    add(f"_{_DISCLAIMER}_")
    return "\n".join(lines)


def campaign_pack_dict(d: dict) -> dict:
    """Structured JSON evidence pack — the campaign record plus the computed
    trust annotations (corroboration, discriminative vs silent detectors) and
    the methodology/disclaimer, so a programmatic consumer gets the same
    contract a human reader does."""
    methods = d.get("methods") or []
    return {
        "generator": "OMISPHERE Campaign Intelligence",
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "campaign": d,
        "trust": {
            "corroborated": is_corroborated(methods),
            "discriminative_methods": [m for m in methods if m in DISCRIMINATIVE_DETECTORS],
            "supporting_methods": [m for m in methods if m not in DISCRIMINATIVE_DETECTORS],
            "silent_methods": _silent_methods(methods),
            "gate": (
                "A maximal verdict requires a discriminative detector "
                "(fingerprint_cluster / co_engagement / co_tag) or >=2 distinct "
                "detectors. A lone supporting detector is capped at MODERATE."
            ),
        },
        "methodology": _methodology_note(),
        "disclaimer": _DISCLAIMER,
    }


def render_campaign_json(d: dict) -> str:
    return json.dumps(campaign_pack_dict(d), default=str, indent=2)
