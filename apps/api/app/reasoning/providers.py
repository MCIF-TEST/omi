"""LLM provider abstraction for investigation COMMENTARY (analyst-style prose).

``TemplateProvider`` — deterministic, no API calls, never fails — is the sole production provider.

Phase P3.4 (canonical reasoning unification) RETIRED the Anthropic (Claude Haiku) provider that used to
back commentary. It was a SECOND production AI reasoning engine: a different model, reached with prompt
text embedded in ``commentary.py`` and WITHOUT the Package Loader, the Evidence Bundle, the Governor, or
the deterministic Floor. Omi now has exactly ONE production AI reasoning architecture — the canonical
stage pipeline (Evidence Bundle → canonical Prompt Builder → AI Investigation Runtime → Mistral →
Governor). Commentary is a DETERMINISTIC PRESENTATION projection of the engine's evidence, not an
independent reasoning engine. Tests can still inject a provider via ``set_provider_for_tests``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings


@dataclass
class ProviderResult:
    text: str
    provider: str        # e.g. "template", "anthropic-claude-haiku-4-5-20251001"
    tokens_used: int     # 0 for template provider


class LLMProvider(Protocol):
    name: str

    def synthesize(self, *, system: str, user: str, max_tokens: int) -> ProviderResult: ...


# ---------------------------------------------------------------------------
# Template provider — always available, zero cost
# ---------------------------------------------------------------------------


class TemplateProvider:
    """Deterministic rules-based prose generator.

    Reads structured cues out of the user message (which is a digest of
    the investigation findings, not raw text) and assembles a paragraph.
    Never fails. Never spends tokens.
    """

    name = "template"

    def synthesize(self, *, system: str, user: str, max_tokens: int) -> ProviderResult:
        text = _template_paragraph(user)
        return ProviderResult(text=text, provider=self.name, tokens_used=0)


def _template_paragraph(digest: str) -> str:
    """Render a competent paragraph from the structured digest.

    The digest is a key:value text block; we parse it lightly to phrase
    the same facts into prose.
    """
    fields = _parse_digest(digest)
    pct = fields.get("verdict_pct", "—")
    tier = fields.get("tier", "low")
    n_cl = fields.get("crosslinks", "0")
    n_flagged = fields.get("flagged", "0")
    headline = fields.get("headline", "")
    intents = fields.get("intents", "")
    clusters = fields.get("clusters", "0")
    weak = fields.get("weak", "")

    tier_phrase = {
        "low": "low overall suspicion, with patterns broadly consistent with organic activity",
        "moderate": "moderate suspicion, with patterns that warrant a closer look but no single signal carrying the verdict",
        "elevated": "elevated suspicion across multiple independent detectors",
        "high": "strong indicators across several independent detectors",
    }.get(tier, tier)

    sentences = [
        f"The investigation finished at {pct} probability — {tier_phrase}.",
    ]
    try:
        if int(n_cl) > 0:
            sentences.append(
                f"OMISPHERE found {n_cl} cross-link{'' if n_cl == '1' else 's'} between the inputs, "
                f"meaning independent signals converged on the same entity from different angles."
            )
    except ValueError:
        pass
    if headline:
        sentences.append(f"The headline finding is consistent with {headline.lower()}.")
    try:
        if int(n_flagged) > 0:
            sentences.append(
                f"{n_flagged} commenter{'' if n_flagged == '1' else 's'} were "
                f"individually flagged at moderate-or-higher suspicion."
            )
    except ValueError:
        pass
    if intents:
        sentences.append(f"Suspected activity categories include: {intents}.")
    try:
        if int(clusters) > 0:
            sentences.append(
                f"{clusters} cross-account coordination cluster"
                f"{'' if clusters == '1' else 's'} were detected."
            )
    except ValueError:
        pass
    if weak:
        sentences.append(
            f"Note: confidence is constrained by data-quality factors ({weak})."
        )
    sentences.append(
        "All findings are probabilistic and evidence-bearing; OMISPHERE never claims a definitive judgement about an account or the person behind it."
    )
    return " ".join(sentences)


def _parse_digest(digest: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in digest.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip().lower().replace(" ", "_").lstrip("-").strip()
        out[k] = v.strip()
    return out


# ---------------------------------------------------------------------------
# Selector
# ---------------------------------------------------------------------------
# Phase P3.4 retired the Anthropic (Claude Haiku) provider — the second production AI reasoning engine.
# The deterministic ``TemplateProvider`` is the sole production commentary provider, so commentary is a
# deterministic PRESENTATION projection and the canonical Mistral stage pipeline is the ONE production
# AI reasoning architecture. The ``settings.anthropic_*`` config fields are inert (retained only for
# backward-compatible env parsing).

_provider_override: LLMProvider | None = None


def get_provider(settings: Settings | None = None) -> LLMProvider:
    """Return the active commentary provider. The deterministic ``TemplateProvider`` is the sole
    production provider (Phase P3.4 retired the Anthropic 2nd reasoning engine). Tests can inject a
    fake via ``set_provider_for_tests()``. ``settings`` is accepted for signature compatibility."""
    if _provider_override is not None:
        return _provider_override
    return TemplateProvider()


def set_provider_for_tests(p: LLMProvider | None) -> None:
    global _provider_override
    _provider_override = p
