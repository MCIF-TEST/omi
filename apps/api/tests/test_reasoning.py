"""Tests for the Phase 7 LLM enhancement layer."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.reasoning import synthesize_commentary
from app.reasoning.providers import (
    LLMProvider, ProviderResult, TemplateProvider,
    get_provider, set_provider_for_tests,
)
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import Investigation, User


@pytest.fixture(autouse=True)
def _fresh_db():
    reset_db_for_tests()
    yield
    set_provider_for_tests(None)


def _seed_inv(slug: str = "inv_phase7", with_payload: dict | None = None) -> None:
    with get_session() as session:
        u = User(email="r7@x.com", password_hash="x", credits_remaining=3)
        session.add(u); session.flush()
        session.add(Investigation(
            user_id=u.id,
            slug=slug,
            label="Video xyz",
            input_url="https://youtube.com/watch?v=xyz",
            kind="video",
            overall_probability=0.72,
            overall_tier="elevated",
            summary="Elevated suspicion across multiple signals.",
            quota_used=42,
            payload_json=with_payload or {
                "overall_probability": 0.72,
                "overall_tier": "elevated",
                "summary": "Elevated suspicion across multiple signals.",
                "cross_links": [{
                    "kind": "focus_in_cluster", "severity": "elevated",
                    "summary": "Focus in cluster", "evidence": ["3 tight members"],
                }],
                "video": {
                    "commenters": [
                        {"handle": "@bot", "tier": "high",
                         "overall_probability": 0.91, "intent_label": "Engagement farming",
                         "weak_signals": [], "summary": "Spam"},
                    ],
                    "clusters": [{"method": "co_engagement", "members": ["A", "B"]}],
                },
            },
        ))


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------


def test_get_provider_returns_template_without_key():
    p = get_provider()
    assert p.name == "template"


def test_template_provider_never_fails_on_empty_input():
    p = TemplateProvider()
    r = p.synthesize(system="x", user="", max_tokens=320)
    assert isinstance(r.text, str)
    assert len(r.text) > 0
    assert r.tokens_used == 0


def test_template_provider_references_facts():
    p = TemplateProvider()
    digest = (
        "label: Test\n"
        "verdict_pct: 72\n"
        "tier: elevated\n"
        "crosslinks: 3\n"
        "flagged: 5\n"
        "intents: Engagement farming; Spam promotion\n"
        "clusters: 2\n"
    )
    r = p.synthesize(system="x", user=digest, max_tokens=320)
    # Output mentions the headline numbers
    assert "72" in r.text
    assert "elevated" in r.text.lower() or "elevated" in r.text
    assert "probabilistic" in r.text.lower()
    assert "3 cross-link" in r.text or "3 cross-links" in r.text


# ---------------------------------------------------------------------------
# synthesize_commentary
# ---------------------------------------------------------------------------


def test_synthesize_commentary_with_template_provider():
    investigation = {"label": "Test", "input_url": "u", "kind": "video", "slug": "s"}
    payload = {
        "overall_probability": 0.5,
        "overall_tier": "moderate",
        "summary": "A moderate scan.",
        "cross_links": [],
        "video": {"commenters": []},
    }
    r = synthesize_commentary(investigation=investigation, payload=payload)
    assert r.provider == "template"
    assert "probabilistic" in r.text.lower()
    assert r.tokens_used == 0


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


def test_commentary_endpoint_generates_and_caches():
    _seed_inv()
    with TestClient(app) as tc:
        r1 = tc.post("/v1/investigations/inv_phase7/commentary")
        assert r1.status_code == 200, r1.text
        b1 = r1.json()
        assert b1["cached"] is False
        assert b1["provider"] == "template"
        assert len(b1["text"]) > 50

        # Second call → cached, same text
        r2 = tc.post("/v1/investigations/inv_phase7/commentary")
        assert r2.status_code == 200
        b2 = r2.json()
        assert b2["cached"] is True
        assert b2["text"] == b1["text"]


def test_commentary_refresh_regenerates():
    """Refresh=true bypasses cache. With template provider the text is
    deterministic, so we assert it returns cached=False even though the
    text happens to match."""
    _seed_inv()
    with TestClient(app) as tc:
        tc.post("/v1/investigations/inv_phase7/commentary")
        r = tc.post("/v1/investigations/inv_phase7/commentary?refresh=true")
        assert r.status_code == 200
        assert r.json()["cached"] is False


def test_commentary_unknown_slug_404():
    with TestClient(app) as tc:
        r = tc.post("/v1/investigations/inv_nope/commentary")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Fake provider injection
# ---------------------------------------------------------------------------


class _FakeProvider:
    name = "fake-llm-v1"

    def synthesize(self, *, system: str, user: str, max_tokens: int) -> ProviderResult:
        # Echo a known sentinel so the test can verify wiring
        return ProviderResult(
            text="FAKE COMMENTARY OK · probabilistic.",
            provider=self.name,
            tokens_used=42,
        )


def test_injected_provider_is_used():
    _seed_inv()
    set_provider_for_tests(_FakeProvider())
    with TestClient(app) as tc:
        r = tc.post("/v1/investigations/inv_phase7/commentary")
        assert r.status_code == 200
        body = r.json()
        assert body["text"].startswith("FAKE COMMENTARY OK")
        assert body["provider"] == "fake-llm-v1"
        assert body["tokens_used"] == 42


# ---------------------------------------------------------------------------
# GAP-06: faithful attribution reaches the account-analysis prompt
# ---------------------------------------------------------------------------


class _CapturingProvider:
    """Records the user prompt it was handed so we can assert what the digest
    told the model."""

    name = "capture-v1"

    def __init__(self) -> None:
        self.last_user = ""

    def synthesize(self, *, system: str, user: str, max_tokens: int) -> ProviderResult:
        self.last_user = user
        return ProviderResult(text="ok", provider=self.name, tokens_used=0)


def test_account_digest_surfaces_exculpatory_contributions():
    """When contributions include a 'lowers' entry (e.g. community anchor), the
    digest must tell the model about the exculpatory side, not just the
    suspicious signals."""
    from app.reasoning.commentary import synthesize_account_analysis

    cap = _CapturingProvider()
    contributions = [
        {"name": "semantic", "direction": "raises", "impact": 0.6},
        {"name": "community", "direction": "lowers", "impact": 0.3},
    ]
    synthesize_account_analysis(
        handle="@acct", platform="youtube", overall_probability=0.45, tier="moderate",
        confidence=0.6, summary="Mixed signals.", signals=[],
        trend_direction="flat", trend_summary="stable", scan_count=3,
        reasons=[], weak_signals=[], contributions=contributions, provider=cap,
    )
    assert "raised_suspicion:" in cap.last_user
    assert "lowered_suspicion:" in cap.last_user
    assert "community" in cap.last_user
    assert "exculpatory" in cap.last_user


def test_account_digest_omits_attribution_when_absent():
    """Backward compatibility: callers that don't pass contributions get the
    original digest shape (no attribution block)."""
    from app.reasoning.commentary import synthesize_account_analysis

    cap = _CapturingProvider()
    synthesize_account_analysis(
        handle="@acct", platform="youtube", overall_probability=0.2, tier="low",
        confidence=0.5, summary="Clean.", signals=[],
        trend_direction="flat", trend_summary="stable", scan_count=1,
        reasons=[], weak_signals=[], provider=cap,
    )
    assert "raised_suspicion:" not in cap.last_user
    assert "lowered_suspicion:" not in cap.last_user
