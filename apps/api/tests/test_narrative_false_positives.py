"""Narrative false-positive regression — the corroboration gate.

Verified defect: a narrative could be labeled "suspicious"/"coordinated" from
account-level suspicion alone (the inauthenticity_fraction shortcut), with no
corroborating narrative-level coordination. The fix requires
``narrative_corroboration >= 2`` (>=2 narrative-level signals firing, EXCLUDING
account-level inauthenticity) for any "suspicious"+ label or moderate+ risk.

The four cases below map 1:1 to the authorized acceptance criteria.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.narrative.coordination import MembershipRecord, score_narrative, text_fingerprint

_BASE = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
_SUSPICIOUS = {"suspicious", "coordinated", "manipulation_network"}


def _t(hours: float) -> datetime:
    return _BASE + timedelta(hours=hours)


def _score(members):
    times = [m.observed_at for m in members]
    return score_narrative(members=members, first_seen_at=min(times), last_seen_at=max(times))


# Case 1 — organic reply cluster + HIGH account suspicion + WEAK narrative
# evidence → must NOT be labeled suspicious.
def test_case1_high_account_suspicion_weak_narrative_not_suspicious():
    members = [
        MembershipRecord(
            account_external_id=f"sus_{i}",      # 10 DISTINCT moderate+ accounts
            platform="youtube",
            parent_id="video_single",            # one shared parent → no cross-target
            observed_at=_t(i * 3),               # diffuse over 30h → no burst/entropy
            text_hash=text_fingerprint(f"unique organic reply number {i}"),  # no reposts
            tier="moderate",
        )
        for i in range(10)
    ]
    s = _score(members)
    assert s.inauthenticity_fraction == 1.0          # account suspicion is maxed
    assert s.narrative_corroboration < 2             # but no corroborating coordination
    assert s.coordination_label not in _SUSPICIOUS   # → not a coordination verdict
    assert s.coordination_label == "mixed"           # honestly surfaced as "mixed"
    assert s.risk_tier == "low"


# Case 2 — strong narrative-level evidence + multiple corroborating signals →
# suspicious label still produced (the gate must not suppress real coordination).
def test_case2_corroborated_narrative_still_labeled_suspicious():
    members = []
    shared = text_fingerprint("Buy now at this amazing link, limited time only")
    for i in range(6):                                # 6 moderate authors
        for p in ("video_a", "video_b"):              # each on 2 parents → cross-target fires
            members.append(MembershipRecord(
                account_external_id=f"acct_{i}", platform="youtube",
                parent_id=p, observed_at=_t(i * 0.05),
                text_hash=shared,                      # identical text → repost fires
                tier="moderate",
            ))
    s = _score(members)
    assert s.narrative_corroboration >= 2
    assert s.coordination_label in _SUSPICIOUS
    assert s.risk_tier in {"moderate", "high", "extreme"}


# Case 3 — reply-thread artifacts ALONE (organic, low-tier authors sharing a
# parent + identical boilerplate) → cannot create a suspicious classification.
def test_case3_reply_artifacts_alone_cannot_be_suspicious():
    boiler = text_fingerprint("@creator great video thanks")
    members = [
        MembershipRecord(
            account_external_id=f"viewer_{i}", platform="youtube",
            parent_id="video_thread", observed_at=_t(i * 0.1),
            text_hash=boiler,                          # identical reply boilerplate
            tier="low",                                # ordinary organic accounts
        )
        for i in range(12)
    ]
    s = _score(members)
    assert s.qualifying_member_count == 0
    assert s.coordination_label == "organic"
    assert s.risk_tier == "low"


# Case 4 — legitimate coordinated narrative (strong, multi-signal) → high-end
# detection remains intact (the gate doesn't dampen genuine campaigns).
def test_case4_genuine_coordination_detection_intact():
    members = []
    shared = text_fingerprint("Share this everywhere — the truth they hide")
    for i in range(8):                                 # 8 elevated authors
        for p in ("v1", "v2", "v3"):                   # cross-target spread
            members.append(MembershipRecord(
                account_external_id=f"cell_{i}", platform="x",
                parent_id=p, observed_at=_t(i * 0.02),
                text_hash=shared,                      # identical messaging
                tier="elevated",
            ))
    s = _score(members)
    assert s.narrative_corroboration >= 2
    # Strong coordination must still reach at least "coordinated".
    assert s.coordination_label in {"coordinated", "manipulation_network"}
    assert s.risk_tier in {"high", "extreme"}


# Guard: the corroboration count must EXCLUDE account-level inauthenticity, so
# inauthenticity_fraction alone can never satisfy the gate.
def test_inauthenticity_excluded_from_corroboration():
    members = [
        MembershipRecord(
            account_external_id=f"a_{i}", platform="youtube",
            parent_id="p", observed_at=_t(i * 4),
            text_hash=text_fingerprint(f"distinct text {i}"), tier="high",
        )
        for i in range(8)
    ]
    s = _score(members)
    assert s.inauthenticity_fraction == 1.0
    assert s.narrative_corroboration == 0   # inauthenticity does not count
    assert s.coordination_label not in _SUSPICIOUS
