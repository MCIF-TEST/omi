"""Step 8 — measured token budgeting: the model-facing evidence fits the Mistral-7B window.

Measures the model-facing evidence for small / medium / worst-case investigations and proves the frozen
token contract holds: budgeting (lossless normalization + coverage selection) keeps the model-facing
evidence — plus a system-prompt allowance — comfortably inside the model's 32,768-token context window,
even for a worst-case investigation that would overflow it un-budgeted; large investigations are reduced
substantially versus the naive complete rendering; and any upstream truncation is DISCLOSED (never
silent). Token figures are the deterministic BPE-approximating estimate (no tokenizer library present).
"""
from __future__ import annotations

from app.reasoning.evidence_repository import EvidenceRepository
from app.reasoning.investigation_composer import InvestigationComposer
from app.reasoning.investigation_render import render_investigation_evidence
from app.reasoning.investigation_render.tokens import estimate_json_tokens

MISTRAL_7B_WINDOW = 32768
# base system (system + constitution + framework + knowledge) measured ~6.4k; leave headroom for the
# comprehensive stage task block + output contract + completion.
SYSTEM_ALLOWANCE = 9000
COMPLETION_RESERVE = 3000


def _payload(n_accounts: int, n_clusters: int, dup_repeats: int) -> dict:
    commenters = []
    for i in range(n_accounts):
        commenters.append({
            "external_id": f"acct{i}", "handle": f"@account_number_{i}",
            "overall_probability": 0.5 + (i % 5) * 0.08, "tier": "elevated", "confidence": 0.5,
            "matched_prior_neighbors": i % 3, "from_cache": bool(i % 2),
            "recent_activity": [{"text": ("coordinated talking point " * dup_repeats).strip(),
                                 "created_at": f"2026-01-01T00:{i % 60:02d}:00Z"}],
            "signals": [{"name": "temporal", "probability": 0.7, "confidence": 0.6,
                         "evidence": ["low posting-interval variance detected across the window"]},
                        {"name": "fingerprint", "probability": 0.3, "confidence": 0.6,
                         "evidence": ["device fingerprint overlaps with two other accounts"]}],
            "contributions": [{"name": "temporal", "impact": 0.4, "direction": "raises",
                               "logit_delta": 0.8, "decorrelation_factor": 0.7,
                               "evidence": "burst window 4s across cohort"}]})
    clusters = []
    per = max(2, n_accounts // max(1, n_clusters))
    for k in range(n_clusters):
        members = [f"acct{j}" for j in range(k * per, min(n_accounts, (k + 1) * per + 2))]  # overlaps
        clusters.append({"method": "co_engagement" if k % 2 else "fingerprint_cluster",
                         "members": members, "score": 0.7, "evidence": ["tight co-engagement ring"]})
    return {"overall_probability": 0.8, "overall_tier": "high", "inputs_provided": ["video"],
            "video_id": "v1",
            "video": {"video_id": "v1", "coordination_score": 0.75, "coordination_tier": "high",
                      "clusters": clusters, "thread_scan": {"overall_probability": 0.6, "tier": "elevated"},
                      "commenters": commenters}}


def _render(payload):
    snap = EvidenceRepository().snapshot(payload, ref="inv", platform="youtube")
    pkg = InvestigationComposer().compose(snap)
    naive = estimate_json_tokens(pkg.bundles.to_dict())
    rv = render_investigation_evidence(pkg)
    return pkg, naive, rv


def test_small_medium_worst_all_fit_the_model_window():
    cases = {"small": _payload(3, 1, 1), "medium": _payload(60, 4, 3), "worst": _payload(800, 20, 12)}
    for label, p in cases.items():
        _pkg, naive, rv = _render(p)
        model_facing_total = SYSTEM_ALLOWANCE + rv.tokens
        assert model_facing_total + COMPLETION_RESERVE < MISTRAL_7B_WINDOW, (
            f"{label}: model-facing {model_facing_total} + reserve overflows the 32k window "
            f"(evidence={rv.tokens}, naive={naive})")


def test_budgeting_substantially_reduces_large_investigations():
    _pkg, naive, rv = _render(_payload(800, 20, 12))
    assert rv.coverage["mode"] == "large_investigation"
    # the naive complete rendering would be far larger; budgeting cuts it by a wide margin
    assert rv.tokens < naive * 0.6, f"expected major reduction; got budgeted={rv.tokens} naive={naive}"


def test_worst_case_would_overflow_unbudgeted():
    """Proves budgeting is NECESSARY, not cosmetic: the naive complete evidence + system prompt would
    itself overflow the window, so the deterministic budgeter is a hard requirement."""
    _pkg, naive, _rv = _render(_payload(800, 20, 12))
    assert SYSTEM_ALLOWANCE + naive > MISTRAL_7B_WINDOW - COMPLETION_RESERVE


def test_upstream_truncation_is_disclosed_not_silent():
    """A very large investigation trips the Evidence layer's per-section cap; the coverage manifest must
    DISCLOSE observed>carried (sampling), never truncate silently."""
    pkg, _naive, rv = _render(_payload(800, 20, 12))
    sampling = rv.coverage["sampling"]
    assert sampling["truncated_upstream"] is True
    assert sampling["domains"]["accounts"]["observed"] == 800
    assert sampling["domains"]["accounts"]["carried"] < 800
    # and the overall mode reflects the omission
    assert rv.coverage["mode"] == "large_investigation"


def test_small_investigation_not_truncated():
    pkg, _naive, rv = _render(_payload(3, 1, 1))
    assert rv.coverage["sampling"]["truncated_upstream"] is False
    assert rv.coverage["mode"] == "complete"
