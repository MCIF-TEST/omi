"""t.co expansion in the Twitter ingestion layer (Phase 5 follow-up).

X wraps every outbound link in a t.co short URL. The provider returns raw tweet
text with those t.co links, and the engagement detector (correctly) treats t.co
as a shortener — so a legitimate X link-sharer measured ~0.72 spam probability.

The fix lives in ingestion (``_map_tweet`` -> ``_expand_tco``), not the detector:
t.co is replaced with its real destination from the tweet's URL entities, so the
detector judges the actual domain. This preserves affiliate-spam detection (a
spammer's t.co expands back to bit.ly/linktr.ee) while clearing the false
positive. The detector-level characterization test
(``test_link_overflag_measurement``) is intentionally left untouched and still
documents raw-t.co behaviour in isolation.

Measured (this commit), end-to-end through ``_map_tweet`` + ``analyze_engagement``:
  legit X link-sharer (entities): 0.72 -> 0.00
  affiliate spam on X (entities):       0.72 (preserved)
  legit X link-sharer (no entities):    0.00 (t.co stripped, no shortener FP)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.detection.engagement import analyze_engagement
from app.integrations.twitter import _map_tweet

_BASE = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _tweet(text: str, i: int, urls: list[dict] | None = None) -> dict:
    tw: dict = {
        "text": text,
        "createdAt": (_BASE + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "author": {"userName": "u"},
    }
    if urls is not None:
        tw["entities"] = {"urls": urls}
    return tw


def _engagement(tweets: list[dict]):
    posts = [p for p in (_map_tweet(t, "u") for t in tweets) if p]
    return analyze_engagement(posts), posts


def test_tco_is_expanded_to_real_destination():
    tw = _tweet(
        "Important thread on the data https://t.co/abc1", 0,
        [{"url": "https://t.co/abc1", "expanded_url": "https://www.reuters.com/world/x"}],
    )
    post = _map_tweet(tw, "u")
    assert post is not None
    assert "t.co" not in post.text
    assert "reuters.com/world/x" in post.text


def test_legit_x_link_sharer_not_overflagged_after_expansion():
    """The headline fix: t.co-wrapped legit news links no longer read as spam."""
    legit = [
        _tweet("Important thread on the data https://t.co/a1", 0,
               [{"url": "https://t.co/a1", "expanded_url": "https://www.reuters.com/world/x"}]),
        _tweet("New report worth a read https://t.co/a2", 1,
               [{"url": "https://t.co/a2", "expanded_url": "https://www.bbc.com/news/y"}]),
        _tweet("Source for the claim https://t.co/a3", 2,
               [{"url": "https://t.co/a3", "expanded_url": "https://github.com/org/repo"}]),
        _tweet("Good analysis here https://t.co/a4", 3,
               [{"url": "https://t.co/a4", "expanded_url": "https://www.nature.com/articles/z"}]),
        _tweet("Filed my piece on this https://t.co/a5", 4,
               [{"url": "https://t.co/a5", "expanded_url": "https://www.gov.uk/publications/p"}]),
        _tweet("Context in the replies https://t.co/a6", 5,
               [{"url": "https://t.co/a6", "expanded_url": "https://apnews.com/article"}]),
    ] * 3
    sig, _ = _engagement(legit)
    assert sig.sub_signals["url_inclusion_rate"] == 0.0, sig.sub_signals
    assert sig.probability < 0.25, f"legit X link-sharer still over-flagged: {sig.probability:.3f}"


def test_affiliate_spam_on_x_still_flagged_after_expansion():
    """Recall preserved: a spammer's t.co expands back to its shortener target."""
    spam = [
        _tweet("Use my promo code SAVE20! https://t.co/s1", 0,
               [{"url": "https://t.co/s1", "expanded_url": "https://bit.ly/deal"}]),
        _tweet("Free shipping, limited time only! https://t.co/s2", 1,
               [{"url": "https://t.co/s2", "expanded_url": "https://linktr.ee/me"}]),
        _tweet("Click the link in bio now! https://t.co/s3", 2,
               [{"url": "https://t.co/s3", "expanded_url": "https://cutt.ly/x"}]),
    ] * 6
    sig, _ = _engagement(spam)
    assert sig.probability > 0.6, f"affiliate spam under-flagged after fix: {sig.probability:.3f}"


def test_tco_without_entities_is_neutralized():
    """No expansion data -> drop the bare t.co; it must not read as a shortener."""
    legit = [
        _tweet("Important thread on the data https://t.co/a1", 0),
        _tweet("New report worth a read https://t.co/a2", 1),
        _tweet("Source for the earlier claim https://t.co/a3", 2),
    ] * 6
    sig, posts = _engagement(legit)
    assert "t.co" not in posts[0].text
    assert sig.probability < 0.25, f"bare t.co still over-flagged: {sig.probability:.3f}"
