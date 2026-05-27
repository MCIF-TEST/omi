"""`synthesize_commentary` — the public entry point for Phase 7.

Takes a stored ComprehensiveScanResult payload + investigation metadata,
builds a tight structured digest, and asks the active provider for an
analyst-style paragraph.

The function is **idempotent at the storage layer** — callers should
cache the result on the Investigation row and only call this again
when the user explicitly requests a refresh.
"""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.reasoning.providers import LLMProvider, ProviderResult, get_provider


SYSTEM_PROMPT = """You are an authenticity intelligence analyst writing brief, \
evidence-grounded commentary on detection findings produced by an \
automated probabilistic engine called OMISPHERE.

Hard rules — these are non-negotiable:

1. Never claim certainty. Use "consistent with", "patterns suggest", \
"appears to", "may indicate". Never "is a bot" or "this account is fake".
2. Never accuse a real person; describe observed behavioral patterns.
3. Cite specific signals or counts when relevant (e.g. "8 cross-links", \
"engagement-farming patterns across 7 of 10 sampled comments").
4. Output: a single paragraph or two short paragraphs, 120 to 180 words \
total. No bullet points, no headers, no preamble like "Based on the data".
5. End with one sentence acknowledging that the findings are probabilistic.

You are NOT a chatbot. You produce analytic prose only."""


def _build_digest(*, investigation: dict, payload: dict, max_chars: int) -> str:
    """Compact, structured key:value digest for the model.

    Deliberately tight — every additional token costs money. The
    investigation summary itself already encodes most of what we need;
    we just expose a few structured cues so the prose can reference
    them.
    """
    pct = int(round((payload.get("overall_probability") or 0) * 100))
    tier = payload.get("overall_tier") or "low"
    cross_links = payload.get("cross_links") or []
    headline = cross_links[0] if cross_links else None

    video = payload.get("video") or {}
    commenters = video.get("commenters") or []
    flagged = [c for c in commenters if c.get("tier") in ("moderate", "elevated", "high")]
    sample_handles = ", ".join((c.get("handle") or "?") for c in flagged[:3])
    intents = sorted({
        (c.get("intent_label") or "")
        for c in flagged if c.get("intent_label")
    })

    lines = [
        f"label: {investigation.get('label', '?')}",
        f"verdict_pct: {pct}",
        f"tier: {tier}",
        f"summary: {(payload.get('summary') or '').strip()[:600]}",
        f"crosslinks: {len(cross_links)}",
    ]
    if headline:
        lines.append(
            f"headline: {(headline.get('summary') or '').strip()[:280]}"
        )
        if headline.get("evidence"):
            lines.append(f"headline_evidence: {(headline['evidence'][0] or '')[:200]}")
    lines.append(f"flagged: {len(flagged)}")
    if sample_handles:
        lines.append(f"sample_handles: {sample_handles}")
    if intents:
        lines.append(f"intents: {'; '.join(intents)[:200]}")
    lines.append(f"clusters: {len(video.get('clusters') or [])}")

    # Aggregate weak-signal reasons across commenters (first 3 unique)
    weak_set: list[str] = []
    for c in flagged:
        for w in (c.get("weak_signals") or []):
            if w not in weak_set:
                weak_set.append(w)
            if len(weak_set) >= 3:
                break
        if len(weak_set) >= 3:
            break
    if weak_set:
        lines.append(f"weak: {'; '.join(weak_set)[:300]}")

    digest = "\n".join(lines)
    return digest[:max_chars]


def synthesize_commentary(
    *,
    investigation: dict,
    payload: dict,
    settings: Settings | None = None,
    provider: LLMProvider | None = None,
) -> ProviderResult:
    """Generate analyst commentary. Returns the result; caller persists."""
    settings = settings or get_settings()
    provider = provider or get_provider(settings)
    digest = _build_digest(
        investigation=investigation,
        payload=payload,
        max_chars=settings.reasoning_max_input_chars,
    )
    user = (
        "Write a 120–180 word analyst commentary on these OMISPHERE findings:\n\n"
        f"{digest}\n\n"
        "Remember: probabilistic language, cite specific counts where useful, "
        "no headers or bullets, single paragraph or two short paragraphs."
    )
    return provider.synthesize(
        system=SYSTEM_PROMPT,
        user=user,
        max_tokens=settings.reasoning_max_tokens,
    )


ACCOUNT_ANALYSIS_SYSTEM = """You are a digital forensics analyst writing a \
concise behavioural profile of a single social-media account based on \
probabilistic detection signals produced by OMISPHERE.

Hard rules:
1. Never claim certainty. Use "patterns suggest", "consistent with", \
"appears to", "may indicate". Never "is a bot" or "is fake".
2. Describe observed behavioural patterns, not the person behind the account.
3. Reference specific signals and their contribution (e.g. "the temporal \
detector found unusually low posting-interval variation").
4. Structure: two to three short paragraphs. First: overall risk picture. \
Second: most notable signals and what they mean. Third (if warranted): \
caveats, data quality, or mitigating context.
5. Total length 150–220 words. No headers, no bullet points.
6. End with one sentence acknowledging probabilistic limits.

You are NOT a chatbot. You produce analytic prose only."""


def _build_account_digest(
    *,
    handle: str,
    platform: str,
    overall_probability: float,
    tier: str,
    confidence: float,
    summary: str,
    signals: list[dict],
    trend_direction: str,
    trend_summary: str,
    scan_count: int,
    reasons: list[str],
    weak_signals: list[str],
    max_chars: int,
) -> str:
    pct = int(round(overall_probability * 100))
    conf_pct = int(round(confidence * 100))

    lines = [
        f"handle: {handle}",
        f"platform: {platform}",
        f"verdict_pct: {pct}",
        f"tier: {tier}",
        f"confidence_pct: {conf_pct}",
        f"summary: {summary[:400]}",
        f"trend: {trend_direction} — {trend_summary[:200]}",
        f"total_scans: {scan_count}",
    ]

    if reasons:
        lines.append("reasons: " + " | ".join(reasons[:4]))

    # Per-detector breakdown
    sig_lines = []
    for s in signals:
        name = s.get("name", "?")
        prob = int(round((s.get("probability") or 0) * 100))
        conf = int(round((s.get("confidence") or 0) * 100))
        ev = (s.get("evidence") or [""])[0][:120] if s.get("evidence") else ""
        sig_lines.append(f"  {name}: {prob}% prob, {conf}% conf — {ev}")
    if sig_lines:
        lines.append("detector_breakdown:\n" + "\n".join(sig_lines[:8]))

    if weak_signals:
        lines.append("data_quality_caveats: " + " | ".join(weak_signals[:3]))

    return "\n".join(lines)[:max_chars]


def synthesize_account_analysis(
    *,
    handle: str,
    platform: str,
    overall_probability: float,
    tier: str,
    confidence: float,
    summary: str,
    signals: list[dict],
    trend_direction: str,
    trend_summary: str,
    scan_count: int,
    reasons: list[str],
    weak_signals: list[str],
    settings: "Settings | None" = None,
    provider: "LLMProvider | None" = None,
) -> "ProviderResult":
    """Generate a per-account behavioural analysis narrative."""
    from app.core.config import get_settings as _get_settings
    settings = settings or _get_settings()
    provider = provider or get_provider(settings)

    digest = _build_account_digest(
        handle=handle,
        platform=platform,
        overall_probability=overall_probability,
        tier=tier,
        confidence=confidence,
        summary=summary,
        signals=signals,
        trend_direction=trend_direction,
        trend_summary=trend_summary,
        scan_count=scan_count,
        reasons=reasons,
        weak_signals=weak_signals,
        max_chars=settings.reasoning_max_input_chars,
    )
    user = (
        "Write a 150–220 word behavioural profile for this account based on "
        "OMISPHERE detection findings:\n\n"
        f"{digest}\n\n"
        "Structure: overall risk picture, then notable signals explained, "
        "then caveats if needed. Probabilistic language throughout. "
        "No headers or bullets."
    )
    return provider.synthesize(
        system=ACCOUNT_ANALYSIS_SYSTEM,
        user=user,
        max_tokens=min(400, settings.reasoning_max_tokens + 80),
    )
