"""LLM provider abstraction.

Two implementations:

* ``TemplateProvider`` — deterministic, no API calls. Ships with every
  install; never fails. Output is competent if not poetic.
* ``AnthropicProvider`` — calls Claude Haiku. Activated by setting
  ``OMI_ANTHROPIC_API_KEY``. Uses prompt caching on the system
  message so repeated calls are cheap.

Selection is automatic: if the key is set AND the ``anthropic`` SDK
is importable, use Anthropic; else fall back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings, get_settings


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
# Anthropic provider
# ---------------------------------------------------------------------------


class AnthropicProvider:
    """Calls Claude Haiku via the Anthropic SDK with prompt caching on
    the system message (~80% input-token reduction at scale)."""

    name: str

    def __init__(self, api_key: str, model: str):
        self._api_key = api_key
        self._model = model
        self.name = f"anthropic-{model}"

    def synthesize(self, *, system: str, user: str, max_tokens: int) -> ProviderResult:
        try:
            from anthropic import Anthropic  # type: ignore
        except ImportError:
            # SDK not installed — fall back to template gracefully.
            return TemplateProvider().synthesize(
                system=system, user=user, max_tokens=max_tokens,
            )

        try:
            client = Anthropic(api_key=self._api_key)
            resp = client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                # Cache the system message — identical across all calls,
                # so after the first generation we pay ~10% of the input
                # cost for the system portion.
                system=[
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user}],
            )
            blocks = getattr(resp, "content", []) or []
            text_parts: list[str] = []
            for b in blocks:
                t = getattr(b, "text", None)
                if isinstance(t, str):
                    text_parts.append(t)
            text = "".join(text_parts).strip()
            usage = getattr(resp, "usage", None)
            tokens = 0
            if usage is not None:
                tokens = int(getattr(usage, "input_tokens", 0)) + int(getattr(usage, "output_tokens", 0))
            return ProviderResult(text=text or "(empty response)", provider=self.name, tokens_used=tokens)
        except Exception:  # noqa: BLE001 — network/API error → fall back gracefully
            return TemplateProvider().synthesize(
                system=system, user=user, max_tokens=max_tokens,
            )


# ---------------------------------------------------------------------------
# Selector
# ---------------------------------------------------------------------------

_provider_override: LLMProvider | None = None


def get_provider(settings: Settings | None = None) -> LLMProvider:
    """Return the active provider. Anthropic when configured; template otherwise.

    Tests can inject a fake via ``set_provider_for_tests()``.
    """
    if _provider_override is not None:
        return _provider_override
    settings = settings or get_settings()
    key = (settings.anthropic_api_key or "").strip()
    if not key:
        return TemplateProvider()
    return AnthropicProvider(api_key=key, model=settings.anthropic_model)


def set_provider_for_tests(p: LLMProvider | None) -> None:
    global _provider_override
    _provider_override = p
