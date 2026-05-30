"""End-to-end tests for the OmniDetect detectors + scorer.

Fixtures are synthetic and intentionally exaggerated: a "mechanical" account
should score noticeably higher than a "human-like" one on the relevant
signals. Tests do not assert specific probabilities — they assert ordering
and tier behavior, which is what we actually care about.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest

from app.detection.ai_writing import analyze_ai_writing
from app.detection.engine import analyze_account, analyze_comments
from app.detection.profile import analyze_profile
from app.detection.scoring import aggregate
from app.detection.semantic import analyze_semantic
from app.detection.temporal import analyze_temporal
from app.schemas import Post, Profile, SignalResult, Tier


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _post(i: int, text: str, ts: datetime, handle: str = "x") -> Post:
    return Post(id=str(i), author_handle=handle, text=text, created_at=ts)


def make_mechanical_posts(n: int = 192, interval_min: int = 15) -> list[Post]:
    """Identical-content posts on a fixed schedule (default 192 over 48 hours)."""
    base = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    template = (
        "Big news today — the establishment doesn't want you to see this. "
        "Share to spread the truth. Follow for more."
    )
    return [
        _post(i, template, base + timedelta(minutes=interval_min * i))
        for i in range(n)
    ]


def make_human_posts(n: int = 60) -> list[Post]:
    """Diverse content, irregular timing, ~7h sleep gap."""
    rng = random.Random(42)
    base = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)
    texts = [
        "finally got around to fixing the bathroom faucet, what a saga",
        "anyone else feel like jan is dragging? coffee not helping",
        "this dog. THIS DOG. I love her so much",
        "saw a hawk just take a pigeon off a streetlamp downtown. nature is metal",
        "in case anyone needs to hear it today: it's okay to log off",
        "rewatching the wire and somehow it's STILL good",
        "lunch was a disaster lol pretending it didn't happen",
        "ok which one of you put the milk back empty",
        "trying to learn rust. send help and/or memes",
        "the new album is fine. just fine. that's the review.",
        "small win: inbox under 50 for the first time this year",
        "wait when did taxes become due THIS soon",
    ]
    posts: list[Post] = []
    t = base
    for i in range(n):
        # Random gap 5..240 minutes, but skip overnight hours.
        gap = rng.randint(5, 240)
        t = t + timedelta(minutes=gap)
        if t.hour < 7:  # simulate sleep
            t = t.replace(hour=8, minute=rng.randint(0, 59))
        posts.append(_post(i, rng.choice(texts) + f" #{rng.randint(1, 9999)}", t))
    return posts


def make_ai_text_corpus() -> list[Post]:
    base = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    paragraphs = [
        # Heavy AI-tells: em-dashes, hedges, uniform sentence structure.
        "It's worth noting that artificial intelligence — once a niche field — has "
        "become a multifaceted tapestry of disciplines. Moreover, in today's "
        "fast-paced landscape, it is important to delve into its implications. "
        "Furthermore, navigating the realm of machine learning underscores the "
        "need for thoughtful governance.",
        "In the realm of social media, it's worth noting that algorithms shape "
        "perception — often in ways we don't fully appreciate. Moreover, the "
        "ever-evolving nature of these systems shed light on broader concerns. "
        "Additionally, in conclusion, vigilance remains essential.",
        "Let's explore the multifaceted dynamics at play. It is important to "
        "understand that — at its core — the issue underscores the tension "
        "between scale and accountability. Furthermore, navigating the regulatory "
        "tapestry requires nuance.",
        "Moreover, in today's fast-paced world — where attention is currency — "
        "it's worth noting that misinformation underscores the fragility of "
        "discourse. Additionally, let's dive into the structural drivers.",
    ]
    return [_post(i, p, base + timedelta(hours=i)) for i, p in enumerate(paragraphs * 4)]


def make_human_text_corpus() -> list[Post]:
    base = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    paragraphs = [
        "ok i don't normally rant but the bus driver this morning literally drove past me. "
        "i made eye contact. he chose violence. anyway gonna be late.",
        "weird realization at 2am: i can't remember the last time i was bored. like, "
        "really bored. that's probably bad? i feel like my brain hasn't had a moment.",
        "the cat brought me a leaf today. proud of her. terrible hunter, great vibes.",
        "trying a new dough recipe. it looks like a science experiment that's "
        "achieved sentience and resents me.",
        "kind of obsessed with how the river looks at dusk in winter. like steel.",
        "i don't think i'm supposed to be moved by the spreadsheet but here we are.",
    ]
    return [_post(i, p, base + timedelta(hours=i)) for i, p in enumerate(paragraphs * 3)]


# ---------------------------------------------------------------------------
# Temporal
# ---------------------------------------------------------------------------


def test_temporal_flags_mechanical_cadence():
    sig = analyze_temporal(make_mechanical_posts())
    assert sig.confidence > 0
    assert sig.probability > 0.7, f"expected high, got {sig.probability:.3f}"


def test_temporal_does_not_flag_human_cadence():
    sig = analyze_temporal(make_human_posts())
    assert sig.probability < 0.6, f"expected low, got {sig.probability:.3f}"


def test_temporal_returns_neutral_on_sparse_data():
    posts = make_mechanical_posts(n=3)
    sig = analyze_temporal(posts)
    assert sig.confidence == 0
    assert sig.probability == 0.5


# ---------------------------------------------------------------------------
# Semantic
# ---------------------------------------------------------------------------


def test_semantic_flags_identical_posts():
    posts = make_mechanical_posts()
    sig = analyze_semantic(posts)
    assert sig.probability > 0.7


def test_semantic_does_not_flag_diverse_posts():
    posts = make_human_posts()
    sig = analyze_semantic(posts)
    assert sig.probability < 0.55, f"expected low, got {sig.probability:.3f}"


# ---------------------------------------------------------------------------
# AI writing
# ---------------------------------------------------------------------------


def test_ai_writing_flags_heavy_boilerplate():
    sig = analyze_ai_writing(make_ai_text_corpus())
    assert sig.confidence > 0
    assert sig.probability > 0.6, f"expected elevated, got {sig.probability:.3f}"


def test_ai_writing_does_not_flag_human_voice():
    sig = analyze_ai_writing(make_human_text_corpus())
    assert sig.probability < 0.55, f"expected low, got {sig.probability:.3f}"


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


def test_profile_flags_random_handle_new_account_high_activity():
    profile = Profile(
        platform="x",
        handle="qk7m2x_91827463",
        bio="",
        follower_count=2,
        following_count=4800,
        created_at=datetime.now(timezone.utc) - timedelta(days=14),
    )
    sig = analyze_profile(profile, post_count=900)
    assert sig.probability > 0.6


def test_profile_does_not_flag_normal_account():
    profile = Profile(
        platform="x",
        handle="hannah_writes",
        bio="science journalist. dog person. recovering academic.",
        follower_count=2_400,
        following_count=900,
        created_at=datetime(2017, 3, 1, tzinfo=timezone.utc),
        verified=False,
    )
    sig = analyze_profile(profile, post_count=4_800)
    assert sig.probability < 0.55


# ---------------------------------------------------------------------------
# End-to-end engine
# ---------------------------------------------------------------------------


def test_engine_bot_like_scores_higher_than_human_like():
    bot_profile = Profile(
        platform="x",
        handle="zk8n3q_44882017",
        bio="🚀 100x gains 🚀 join my t.me/airdrop_official",
        follower_count=2,
        following_count=4900,
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    bot_result = analyze_account(bot_profile, make_mechanical_posts())

    human_profile = Profile(
        platform="x",
        handle="hannah_writes",
        bio="science journalist. dog person.",
        follower_count=2_400,
        following_count=900,
        created_at=datetime(2017, 3, 1, tzinfo=timezone.utc),
    )
    human_result = analyze_account(human_profile, make_human_posts())

    assert bot_result.overall_probability > human_result.overall_probability + 0.2
    assert bot_result.tier in {Tier.ELEVATED, Tier.HIGH}
    assert human_result.tier in {Tier.LOW, Tier.MODERATE}
    assert bot_result.summary
    assert "probabilistic" in bot_result.summary.lower()
    # Every result must carry evidence.
    for sig in bot_result.signals:
        assert sig.evidence


def test_ai_writing_is_supplemental_and_does_not_drive_comment_suspicion():
    """GAP-03: AI-writing tells must not raise suspicion on their own.

    The ai_writing detector still runs and detects the heavy AI tells in this
    corpus, but it is supplemental — the comment-scan aggregate is driven purely
    by the *scored* detectors (here, semantic). Demoting ai_writing must leave
    the composite identical to a semantic-only aggregate.
    """
    comments = make_ai_text_corpus()
    result = analyze_comments(comments)

    ai_sig = next(s for s in result.signals if s.name == "ai_writing")
    assert ai_sig.supplemental is True
    # The detector itself still works — it sees the burstiness / hedging tells.
    assert ai_sig.probability > 0.6
    # …but it contributes nothing to suspicion: the aggregate equals what the
    # scored detectors alone produce.
    semantic_only = aggregate([analyze_semantic(comments)])
    assert result.overall_probability == pytest.approx(semantic_only.overall_probability)


def test_ai_tells_alone_do_not_elevate_an_account():
    """An account whose only 'signal' is AI-style writing (e.g. an ESL writer or
    a Grammarly user) must not be elevated above LOW by that fact alone."""
    signals = [
        analyze_ai_writing(make_ai_text_corpus()),  # high AI-tell probability
        # No other detector has data.
        SignalResult(name="temporal", probability=0.5, confidence=0.0, evidence=[]),
        SignalResult(name="semantic", probability=0.2, confidence=0.6, evidence=[]),
        SignalResult(name="profile", probability=0.2, confidence=0.5, evidence=[]),
    ]
    result = aggregate(signals)
    assert result.tier == Tier.LOW, (
        f"AI-writing tells alone should not elevate; got {result.tier} "
        f"at prob {result.overall_probability:.3f}"
    )
    assert result.suspected_intent is None  # no intent inferred at LOW


def test_scoring_with_no_confident_signals_falls_back_to_prior():
    from app.schemas import SignalResult

    signals = [
        SignalResult(name="temporal", probability=0.9, confidence=0.0, evidence=[]),
        SignalResult(name="semantic", probability=0.9, confidence=0.0, evidence=[]),
    ]
    result = aggregate(signals)
    assert result.confidence == 0.0
    assert result.tier == Tier.LOW
    assert result.overall_probability < 0.2


@pytest.mark.parametrize(
    "prob,expected",
    [
        (0.1, Tier.LOW),
        (0.3, Tier.MODERATE),
        (0.6, Tier.ELEVATED),
        (0.9, Tier.HIGH),
    ],
)
def test_tier_thresholds(prob, expected):
    from app.detection.scoring import _tier_for

    assert _tier_for(prob) == expected


# ---------------------------------------------------------------------------
# Engagement / spam-pattern detector
# ---------------------------------------------------------------------------


def test_engagement_flags_promo_spam():
    from app.detection.engagement import analyze_engagement
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    promo_texts = [
        "🚀🚀🚀 Drop a like if you agree! Subscribe for more daily content!! Link in bio https://promo.example.com",
        "🔥🔥🔥 SMASH that subscribe button! Use my promo code BOT20 at checkout www.example.com/save",
        "Comment below if you watched till the end! Hit subscribe and ring the bell! 🔔🔔🔔",
        "Free shipping with my code! Link in description, check my bio! 💰💰💰 https://shop.example.io",
        "Let me know in the comments below! Follow for more 🚀 Tag a friend! https://example.gg/here",
        "🔥 New giveaway! Click the link to enter, limited time! 🎁🎁🎁 example.store/win",
    ]
    posts = [_post(i, t, base + timedelta(hours=i)) for i, t in enumerate(promo_texts * 3)]
    sig = analyze_engagement(posts)
    assert sig.confidence > 0
    assert sig.probability > 0.6, f"expected elevated, got {sig.probability:.3f}"


def test_engagement_neutral_on_organic_comments():
    from app.detection.engagement import analyze_engagement
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    organic = [
        "great editing in this one, what software did you use",
        "the dog at the end is a vibe honestly",
        "wait, what was the song at 4:32? been trying to find it for weeks",
        "i don't normally comment but this hit different. respect.",
        "this is the first video of yours i've seen, definitely subscribing",
        "first time hearing about this topic, going to look up the references",
        "the audio mix is so much better in this one, who's mixing for you now",
    ]
    posts = [_post(i, t, base + timedelta(hours=i)) for i, t in enumerate(organic * 3)]
    sig = analyze_engagement(posts)
    assert sig.probability < 0.5, f"expected low, got {sig.probability:.3f}"


# ---------------------------------------------------------------------------
# Engagement detector — GAP-03 remaining-risk hardening
#
# The engagement detector is the legitimate, behavior-based way to catch the
# promo / follow-bait / spam accounts that GAP-03 stopped catching via the
# (harmful) ai_writing signal. These pin the new coverage and — just as
# importantly — the false-positive guards that keep legitimate link-sharers and
# topic enthusiasts OUT of the suspicion bucket.
# ---------------------------------------------------------------------------


def _engagement(texts: list[str]):
    from app.detection.engagement import analyze_engagement
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    posts = [_post(i, t, base + timedelta(hours=i)) for i, t in enumerate(texts)]
    return analyze_engagement(posts)


def test_engagement_single_link_axis_carries_the_score():
    """100%-link affiliate posting must register as clearly suspicious even with
    no emoji or bait — the disjunctive combiner lets one blatant axis carry,
    where the old weighted-average capped it around 0.3."""
    texts = [
        f"Found an even better deal here: https://amzn.to/d{i} — limited time, link in my bio for more"
        for i in range(8)
    ]
    sig = _engagement(texts)
    assert sig.probability > 0.6, f"link spam under-detected: {sig.probability:.3f}"


def test_engagement_catches_follow_bait_without_links_or_emoji():
    """Follow-bait / DM-bait self-promo with no URLs and no emoji must still be
    caught — this is the 'promo/follow_bait mixed' family that regressed."""
    texts = [
        "Follow me if you want daily tips on what actually works right now",
        "Comment 'HOOK' below and I'll DM you my 50 proven templates for free",
        "Subscribe for daily growth tips — I post every single day",
        "I cover this in depth on my channel, worth checking out",
        "Drop a like if this helped and follow for more no-fluff advice",
        "Want the full breakdown? It's on my channel — link in my bio",
    ]
    sig = _engagement(texts)
    assert sig.probability > 0.5, f"follow-bait under-detected: {sig.probability:.3f}"


def test_engagement_does_not_flag_journalist_citing_sources():
    """A journalist linking to news sites and public documents — no shorteners,
    no promo CTA — must NOT be scored as a link spammer. This is the false
    positive the link-precision rule exists to prevent."""
    texts = [
        "I covered this last month — here's the piece I filed: https://reuters.com/technology/story-x",
        "my sources say the timeline accelerated after the Q4 miss. story still developing.",
        "the regulatory docs are public — pulled them last night: https://eu-regulator.example/case-4421",
        "going to push back here — three of those reports were industry-funded. footnote matters.",
        "my follow-up ran this morning: https://reuters.com/technology/followup-y",
        "correction to my earlier note — the deal closed on the 12th, not the 14th.",
    ]
    sig = _engagement(texts)
    assert sig.probability < 0.4, f"journalist false-positive: {sig.probability:.3f}"


def test_engagement_does_not_flag_genuine_crypto_discussion():
    """Genuine markets/crypto *discussion* (no cashtag, no pump phrases — even if
    it mentions '10x' in passing) must not trip the shill axis."""
    texts = [
        "been through three cycles now and the pattern is always the same",
        "if you're buying for the tech you'll make it through the dips, if you're buying for 10x you won't",
        "the regulatory environment has genuinely shifted, this time feels structurally different",
        "honestly most of the alt narratives don't survive a real bear market",
        "i think self-custody matters more than people admit after the exchange blowups",
        "fees on the L2s have made a real difference to actually using this stuff",
    ]
    sig = _engagement(texts)
    assert sig.probability < 0.4, f"crypto-discussion false-positive: {sig.probability:.3f}"


def test_engagement_two_axes_reach_high_one_axis_stays_elevated():
    """One spam axis = elevated; two independent axes (promo CTA + emoji-bombing)
    escalate to high. This is the calibrated spread the group-ceiling produces."""
    one_axis = _engagement([
        f"Follow me and subscribe for daily tips — link in my bio for the full guide {i}"
        for i in range(8)
    ])
    two_axis = _engagement([
        f"🔥🔥🔥 SMASH that like!! 🚀🚀🚀 Subscribe NOW!! link in bio 🔗 https://bit.ly/x{i} 💥💥💥"
        for i in range(8)
    ])
    assert one_axis.probability < two_axis.probability
    assert two_axis.probability > 0.75, f"multi-axis spam should be high: {two_axis.probability:.3f}"


def test_engagement_strength_aware_confidence_on_blatant_spam():
    """Blatant, consistent spam across only a handful of posts is a CONFIDENT
    call — confidence must not be gated purely on post volume."""
    sig = _engagement([
        f"🔥 DEAL ALERT 🚀 50% OFF link in bio 🔗 https://amzn.to/d{i} don't miss out!!"
        for i in range(6)
    ])
    assert sig.confidence > 0.5, f"blatant spam should be confident: {sig.confidence:.3f}"


def test_semantic_catches_fill_in_the_blank_templates():
    """Template spam that varies one or two words per post ('did an
    [amazing/fantastic] job') must be caught by the 3-gram skeleton supplement
    even on the fallback embedder."""
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    adjectives = ["amazing", "incredible", "fantastic", "brilliant", "outstanding",
                  "wonderful", "superb", "excellent", "great", "stellar"]
    texts = [f"Loved this video! The creator did an {a} job. 10/10 would recommend." for a in adjectives]
    posts = [_post(i, t, base + timedelta(hours=i)) for i, t in enumerate(texts)]
    sig = analyze_semantic(posts)
    assert sig.probability > 0.6, f"template spam under-detected: {sig.probability:.3f}"
    assert sig.confidence > 0.5, f"obvious templating should be confident: {sig.confidence:.3f}"


# ---------------------------------------------------------------------------
# Scoring: convergence bonus + single-signal cap
# ---------------------------------------------------------------------------


def test_scoring_single_signal_cannot_trigger_high():
    """A single noisy detector firing at p=0.99 with high confidence should
    NOT push the overall verdict to HIGH on its own."""
    from app.schemas import SignalResult
    signals = [
        SignalResult(name="semantic", probability=0.99, confidence=1.0,
                     evidence=["lonely strong signal"]),
        # Everything else: zero confidence (no real data)
        SignalResult(name="temporal", probability=0.5, confidence=0.0, evidence=[]),
        SignalResult(name="ai_writing", probability=0.5, confidence=0.0, evidence=[]),
        SignalResult(name="profile", probability=0.5, confidence=0.0, evidence=[]),
    ]
    result = aggregate(signals)
    assert result.tier != Tier.HIGH, (
        f"single signal should not trigger HIGH; got {result.tier} at "
        f"prob {result.overall_probability:.3f}"
    )


def test_scoring_convergence_bonus_lifts_agreed_signals():
    """Multiple detectors agreeing at high probability should produce a
    stronger verdict than just averaging their log-odds."""
    from app.schemas import SignalResult

    # Two scans with the same number of confident-and-high signals (3),
    # vs one scan with just one super-high signal. The convergent set
    # should beat the lonely strong signal.
    converged = [
        SignalResult(name="temporal",   probability=0.7, confidence=0.7, evidence=[]),
        SignalResult(name="semantic",   probability=0.75, confidence=0.7, evidence=[]),
        SignalResult(name="ai_writing", probability=0.7, confidence=0.7, evidence=[]),
        SignalResult(name="profile",    probability=0.5, confidence=0.0, evidence=[]),
    ]
    isolated = [
        SignalResult(name="semantic", probability=0.99, confidence=1.0, evidence=[]),
        SignalResult(name="temporal", probability=0.5, confidence=0.0, evidence=[]),
        SignalResult(name="ai_writing", probability=0.5, confidence=0.0, evidence=[]),
        SignalResult(name="profile", probability=0.5, confidence=0.0, evidence=[]),
    ]
    a = aggregate(converged)
    b = aggregate(isolated)
    # The convergent verdict should be at least as strong (despite no individual
    # signal screaming as loud), AND it should be allowed to reach HIGH.
    assert a.overall_probability >= b.overall_probability - 0.05
    assert a.tier in {Tier.ELEVATED, Tier.HIGH}
