"""The planet-scale layer: accumulation across posts, rotation survival, cross-platform rules.

The two properties worth stating plainly, because they are what the whole layer is for:

* An operation seen on two unrelated posts is more certain than one seen once, and the arithmetic
  reflects that. This is the only reason tracking globally improves accuracy rather than just
  filling a database.
* An operation that burns every account and comes back is recognised anyway. Member overlap cannot
  do this, and rotating accounts is exactly what a competent operation does.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.campaigns.tracking import crossplatform as xp
from app.campaigns.tracking import operations as ops
from app.campaigns.tracking import signature as sig
from app.storage.db import get_session
from app.storage.models import Campaign

T0 = datetime(2026, 3, 1, tzinfo=timezone.utc)
SCRIPT = "the presale closes in six hours and the allocation is nearly gone already friends"
OTHER = "genuinely the best documentary i have watched in years and everyone should see it now"


def op_tokens(script: str, handles: list[str], bucket: str, client: str, domain: str):
    return sig.behavioural_tokens(
        scripts=[script], handles=handles, creation_buckets=[bucket],
        clients=[client], link_domains=[domain],
    )


# ==================================================================================================
# Signatures: behaviour, not identity
# ==================================================================================================
def test_a_signature_reveals_nothing_about_who_was_scanned():
    """A sketch is compared across investigations and across customers. If it contained account ids
    it would leak one customer's scan membership into a match against another's."""
    handles = ["alpha_calls_01", "alpha_calls_02", "alpha_calls_03"]
    tokens = op_tokens(SCRIPT, handles, "2026-01", "MassTweet", "bit.ly")
    joined = " ".join(tokens)
    for handle in handles:
        assert handle not in joined
    # Only namespaced behavioural tokens, no free-form identifiers.
    assert all(t[:2] in ("q:", "h:", "c:", "t:", "d:") for t in tokens)


def test_the_same_operation_matches_itself_with_zero_shared_accounts():
    """The case member overlap is blind to, and the case that matters most."""
    run_one = op_tokens(SCRIPT, ["alpha_calls_01", "alpha_calls_02"], "2026-01", "MassTweet", "bit.ly")
    run_two = op_tokens(SCRIPT, ["alpha_calls_77", "alpha_calls_88"], "2026-01", "MassTweet", "bit.ly")
    a, keys_a = sig.build_signature(run_one)
    b, keys_b = sig.build_signature(run_two)

    assert sig.signature_similarity(a, b) >= sig.SIGNATURE_MATCH_THRESHOLD
    assert sum(1 for x, y in zip(keys_a, keys_b) if x == y) > 0, "no band collided, so no lookup"


def test_a_different_operation_does_not_match():
    mine = op_tokens(SCRIPT, ["alpha_calls_01"], "2026-01", "MassTweet", "bit.ly")
    theirs = op_tokens(OTHER, ["film_nerd_kate"], "2019-07", "Twitter for iPhone", "letterboxd.com")
    a, keys_a = sig.build_signature(mine)
    b, keys_b = sig.build_signature(theirs)

    assert sig.signature_similarity(a, b) < sig.SIGNATURE_MATCH_THRESHOLD
    assert sum(1 for x, y in zip(keys_a, keys_b) if x == y) == 0


def test_an_operation_that_has_shown_too_little_gets_no_signature():
    """A sketch over three tokens collides with everything, and a match rule that fires on
    everything is worse than none. Such an operation can still be matched by member overlap."""
    assert sig.build_signature(sig.behavioural_tokens(handles=["a_b_1"])) is None
    assert sig.build_signature(frozenset()) is None


def test_the_hash_family_is_deterministic_across_processes():
    """``hash()`` is randomised per process, so a sketch built on one worker would not match the
    same operation sketched on another. These are published claims; they cannot depend on which
    process happened to serve the request."""
    tokens = op_tokens(SCRIPT, ["alpha_calls_01"], "2026-01", "MassTweet", "bit.ly")
    first, _ = sig.build_signature(tokens)
    second, _ = sig.build_signature(tokens)
    assert first == second
    assert sig.signature_similarity(first, second) == 1.0


# ==================================================================================================
# Cross-platform
# ==================================================================================================
def test_platform_specific_families_may_not_cross_platforms():
    """`client_signature` reads an X-only field YouTube does not expose, and handle conventions
    differ per platform, so a shared skeleton across two platforms is evidence about the platforms
    rather than about the accounts."""
    assert not xp.may_link("x", "youtube", "infrastructure")
    assert not xp.may_link("x", "youtube", "identity")


def test_platform_neutral_families_may_cross_platforms():
    """The same script, the same referral link and the same arrival minute mean the same thing
    wherever they happen."""
    for family in ("text", "network", "timing"):
        assert xp.may_link("x", "youtube", family), family


def test_every_family_is_allowed_within_one_platform():
    for family in ("text", "network", "timing", "infrastructure", "identity"):
        assert xp.may_link("x", "x", family), family


def test_global_keys_are_namespaced_by_platform():
    """``UC123`` on YouTube and ``UC123`` on X are different accounts. Collapsing them would merge
    two strangers into one operation."""
    assert xp.global_key("x", "UC123") != xp.global_key("youtube", "UC123")
    assert xp.split_key(xp.global_key("youtube", "UC123")) == ("youtube", "UC123")


def test_an_unnamespaced_key_reads_as_unknown_rather_than_raising():
    assert xp.split_key("bare_id") == ("unknown", "bare_id")


# ==================================================================================================
# Lifecycle
# ==================================================================================================
def test_an_operation_returning_after_dormancy_is_marked_resurfaced():
    """That an operation went quiet for four months and came back is itself a finding, so it is
    recorded rather than smoothed over by just bumping last_seen_at."""
    campaign = Campaign(
        campaign_key="k", name="n", platform="x",
        coordination_score=0.9, max_coordination_score=0.9, confidence=0.5,
        member_count=4, observation_count=1,
        last_seen_at=T0 - timedelta(days=ops.DORMANCY_DAYS + 10),
        resurfaced_count=0,
    )
    assert ops.mark_lifecycle(campaign, now=T0) == "resurfaced"
    assert campaign.resurfaced_count == 1
    assert campaign.dormant_since is None


def test_an_operation_seen_again_soon_is_just_observed():
    campaign = Campaign(
        campaign_key="k", name="n", platform="x",
        coordination_score=0.9, max_coordination_score=0.9, confidence=0.5,
        member_count=4, observation_count=1,
        last_seen_at=T0 - timedelta(days=3), resurfaced_count=0,
    )
    assert ops.mark_lifecycle(campaign, now=T0) == "observed"
    assert campaign.resurfaced_count == 0


# ==================================================================================================
# Match order, against a real database
# ==================================================================================================
def test_a_large_campaign_does_not_swallow_every_new_cluster():
    """`jaccard >= 0.30 OR shared >= 3` is fine while campaigns are small and absurd once one is
    large: three shared accounts would link a 5-account cluster to a 500-account campaign at
    j = 0.006, and from then on every cluster would fall into the same one."""
    from app.campaigns.service import CampaignService, _Component

    with get_session() as session:
        big = Campaign(
            campaign_key="big", name="big", platform="x",
            coordination_score=0.9, max_coordination_score=0.9, confidence=0.5,
            member_count=500, observation_count=10,
        )
        session.add(big)
        session.flush()
        from app.storage.models import CampaignMember
        for i in range(5):
            session.add(CampaignMember(
                campaign_id=big.id, platform="x", account_external_id=f"big{i}",
            ))
        session.flush()

        service = CampaignService(session)
        # Three shared accounts out of a five-account cluster: j is about 0.006.
        comp = _Component(members={"big0", "big1", "big2", "new1", "new2"}, methods={"verbatim_echo"})
        matched = service._match_or_create(
            "x", comp, 0.9, 0.5, {"hashtags": [], "mentions": []},
        )
        assert matched.campaign_key != "big", "a huge campaign absorbed an unrelated cluster"


def test_seeding_a_known_operation_stores_a_signature_and_no_members():
    """A seed's accounts were suspended years ago and will never appear in a scan. Carrying them as
    members would match on accounts that no longer exist while implying we observed them."""
    from app.campaigns.tracking import seeds
    from app.storage.models import CampaignMember, OperationSignatureBand

    with get_session() as session:
        campaign = seeds.ingest_seed(session, {
            "name": "Test disclosure operation",
            "platform": "x",
            "scripts": [SCRIPT],
            "handles": ["alpha_calls_01", "alpha_calls_02"],
            "creation_buckets": ["2026-01"],
            "clients": ["MassTweet"],
            "link_domains": ["bit.ly"],
        })
        session.flush()
        assert campaign is not None
        assert campaign.origin == seeds.ORIGIN_DISCLOSURE
        assert campaign.signature_json
        assert campaign.share_token is None, "a seed is never published"
        assert session.query(CampaignMember).filter_by(campaign_id=campaign.id).count() == 0
        assert session.query(OperationSignatureBand).filter_by(campaign_id=campaign.id).count() > 0


def test_a_seed_too_thin_to_sketch_is_skipped_not_stored():
    from app.campaigns.tracking import seeds

    with get_session() as session:
        assert seeds.ingest_seed(session, {"name": "Thin", "handles": ["a_b_1"]}) is None
