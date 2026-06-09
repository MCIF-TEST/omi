"""Tests for the campaign evidence-pack export.

The investigator's deliverable: a portable, citable artifact that carries the
trust contract (corroboration status, evidence-for/against, methodology,
disclaimer) out of the app and into the file. Covers the pure renderers and
the GET /v1/campaigns/{key}/export endpoint (both formats + 404).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.campaigns.service import CampaignService
from app.detection.coordination._types import CoordinationCluster
from app.main import app
from app.reports.campaign_pack import (
    campaign_pack_dict,
    is_corroborated,
    render_campaign_markdown,
)
from app.storage.db import get_session, reset_db_for_tests


@pytest.fixture(autouse=True)
def _fresh_db():
    reset_db_for_tests()
    yield


def _cluster(method: str, members: list[str], score: float = 0.9, evidence=None):
    return CoordinationCluster(
        method=method, members=list(members), score=score,
        evidence=evidence or [f"{method} fired across {len(members)} accounts"],
    )


def _seed(clusters, *, platform="x", context="vid1", score=0.9, texts=None) -> str:
    with get_session() as s:
        camps = CampaignService(s).record_clusters(
            platform=platform, context_id=context, clusters=clusters,
            coordination_score=score, texts_by_account=texts or {},
        )
        return camps[0].campaign_key


# --- pure renderer ----------------------------------------------------------

def test_is_corroborated_matches_the_gate():
    assert is_corroborated(["fingerprint_cluster"]) is True       # discriminative alone
    assert is_corroborated(["co_tag"]) is True
    assert is_corroborated(["style_match"]) is False              # lone supporting
    assert is_corroborated(["style_match", "age_cohort"]) is True  # 2 distinct supporting
    assert is_corroborated([]) is False


def test_markdown_pack_carries_the_trust_contract():
    d = {
        "campaign_key": "abc123", "name": "x coordination · #drill · 4 accounts",
        "platform": "x", "coordination_score": 0.84, "max_coordination_score": 0.91,
        "confidence": 0.8, "member_count": 4, "observation_count": 2,
        "methods": ["fingerprint_cluster", "co_tag"], "hashtags": ["#drill"],
        "mentions": ["@leader"], "status": "recurring",
        "first_detected_at": "2026-05-01T00:00:00Z", "last_seen_at": "2026-06-01T00:00:00Z",
        "evidence": ["4 accounts push the same hashtags"], "theme": None,
        "members": [
            {"account_external_id": "a", "handle": "@a", "times_observed": 2,
             "methods": ["fingerprint_cluster", "co_tag"]},
        ],
        "observations": [
            {"observed_at": "2026-06-01T00:00:00Z", "context_id": "v2",
             "coordination_score": 0.84, "member_count": 4,
             "methods": ["fingerprint_cluster", "co_tag"], "evidence": []},
            {"observed_at": "2026-05-01T00:00:00Z", "context_id": "v1",
             "coordination_score": 0.91, "member_count": 3,
             "methods": ["fingerprint_cluster"], "evidence": []},
        ],
    }
    md = render_campaign_markdown(d)
    # Verdict is never a bare number — score, confidence, corroboration all present.
    assert "91% max observed" in md
    assert "Confidence:** 80%" in md
    assert "corroborated" in md.lower()
    # Evidence FOR labels the discriminative detectors.
    assert "Fingerprint cluster" in md and "discriminative" in md
    # Evidence WEAKENING lists detectors that did NOT fire.
    assert "Evidence weakening" in md
    assert "Style match" in md  # silent here
    # Members + tags + recurrence + methodology + disclaimer.
    assert "@a" in md and "#drill" in md
    assert "Recurrence timeline" in md
    assert "corroboration" in md.lower()
    assert "never a definitive judgement" in md


def test_markdown_pack_flags_uncorroborated_as_supporting_only():
    d = {
        "campaign_key": "k", "name": "lone style cluster", "platform": "x",
        "coordination_score": 0.49, "max_coordination_score": 0.49, "confidence": 0.5,
        "member_count": 3, "observation_count": 1, "methods": ["style_match"],
        "hashtags": [], "mentions": [], "status": "observed",
        "first_detected_at": None, "last_seen_at": None,
        "evidence": [], "theme": None, "members": [], "observations": [],
    }
    md = render_campaign_markdown(d)
    assert "SUPPORTING EVIDENCE ONLY" in md
    assert "capped at MODERATE" in md.lower() or "MODERATE" in md


def test_json_pack_is_valid_and_annotated():
    d = {
        "campaign_key": "k", "name": "c", "platform": "x",
        "coordination_score": 0.9, "max_coordination_score": 0.9, "confidence": 0.8,
        "member_count": 3, "observation_count": 1,
        "methods": ["fingerprint_cluster"], "hashtags": [], "mentions": [],
        "status": "observed", "first_detected_at": None, "last_seen_at": None,
        "evidence": [], "theme": None, "members": [], "observations": [],
    }
    pack = campaign_pack_dict(d)
    assert pack["trust"]["corroborated"] is True
    assert pack["trust"]["discriminative_methods"] == ["fingerprint_cluster"]
    assert "style_match" in pack["trust"]["silent_methods"]
    assert pack["disclaimer"] and pack["methodology"]
    assert pack["campaign"]["campaign_key"] == "k"


# --- endpoint ---------------------------------------------------------------

def test_export_markdown_endpoint_downloads_a_pack():
    key = _seed(
        [_cluster("fingerprint_cluster", ["a", "b", "c"]), _cluster("co_tag", ["a", "b", "c"])],
        texts={"a": ["love #drill @leader"], "b": ["#drill now @leader"]},
    )
    with TestClient(app) as tc:
        r = tc.get(f"/v1/campaigns/{key}/export?format=markdown")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/markdown")
        assert f'campaign-{key}.md' in r.headers.get("content-disposition", "")
        body = r.text
        assert "OMISPHERE Campaign" in body
        assert "Evidence for" in body and "Evidence weakening" in body
        assert "never a definitive judgement" in body


def test_export_json_endpoint_downloads_structured_pack():
    key = _seed([_cluster("fingerprint_cluster", ["a", "b", "c"])])
    with TestClient(app) as tc:
        r = tc.get(f"/v1/campaigns/{key}/export?format=json")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/json")
        assert f'campaign-{key}.json' in r.headers.get("content-disposition", "")
        pack = json.loads(r.text)
        assert pack["campaign"]["campaign_key"] == key
        assert pack["trust"]["corroborated"] is True
        assert "disclaimer" in pack


def test_export_defaults_to_markdown():
    key = _seed([_cluster("fingerprint_cluster", ["a", "b", "c"])])
    with TestClient(app) as tc:
        r = tc.get(f"/v1/campaigns/{key}/export")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/markdown")


def test_export_unknown_campaign_is_404():
    with TestClient(app) as tc:
        r = tc.get("/v1/campaigns/does_not_exist/export?format=markdown")
        assert r.status_code == 404
