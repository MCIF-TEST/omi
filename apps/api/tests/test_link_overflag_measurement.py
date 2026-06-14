"""Measurement: does the engagement/spam-link axis over-flag legitimate users?

Phase 5 reassessment item 5 is MEASURE-ONLY — quantify whether the
"spam/affiliate-link detection over-flags legitimate users" concern is real or
perceived, with NO detector change. These tests run the real
``analyze_engagement`` over representative cohorts and pin the measured
behaviour so a future change is visible.

Measured outcome (2026-06, this commit):

* Legit link-sharers (journalists / OSINT researchers citing news, primary
  sources, datasets, papers) score **0.000** on engagement — the existing
  guard (a bare URL only counts toward the spam axis when it is a known
  shortener/affiliate domain OR sits alongside promo/bait framing) holds. The
  general concern is **perceived, not real**.
* One genuine exception, X-specific: tweet text from the provider arrives with
  every URL ``t.co``-wrapped and unexpanded, and ``t.co`` is (correctly) a
  shortener — so a legitimate X user who frequently shares links scores
  **ELEVATED (~0.72)**. This is a real, measured false positive. It is recorded
  here as a characterization test; the fix (expand t.co, or treat t.co as
  neutral on X) is OUT OF THIS SCOPE (measure only) and tracked for follow-up.
* Real affiliate spam still scores HIGH (~0.75) — true positives intact.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.detection.engagement import analyze_engagement
from app.schemas import Post

_BASE = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _posts(texts: list[str]) -> list[Post]:
    return [
        Post(id=str(i), author_handle="u", text=t, created_at=_BASE + timedelta(hours=i))
        for i, t in enumerate(texts)
    ]


def test_legit_source_sharers_are_not_overflagged():
    """Journalists/researchers citing news + primary sources score ~0 — the
    FP guard for bare, non-shortener links works. (The headline finding.)"""
    legit = [
        "Solid reporting, full piece: https://www.reuters.com/world/europe/article",
        "Primary source: https://www.gov.uk/government/publications/report",
        "Dataset is public: https://github.com/bellingcat/investigations",
        "Worth reading the study https://www.nature.com/articles/s41586",
        "Background: https://www.bbc.com/news/world-12345",
        "Archived copy https://web.archive.org/web/2024/example",
    ] * 3
    sig = analyze_engagement(_posts(legit))
    assert sig.sub_signals["url_inclusion_rate"] == 0.0, sig.sub_signals
    assert sig.probability < 0.25, f"legit source-sharer over-flagged: {sig.probability:.3f}"


def test_news_domains_ending_in_tcom_are_not_false_matched():
    """nyt.com / nypost.com end in 't.com' but must NOT match the t.co
    shortener — confirms the shortener pattern isn't an over-broad substring."""
    legit = [
        "See the NYT writeup https://www.nyt.com/2024/story",
        "Also covered by https://nypost.com/2024/article",
        "Latest updates https://nyt.com/live/updates",
    ] * 6
    sig = analyze_engagement(_posts(legit))
    assert sig.sub_signals["url_inclusion_rate"] == 0.0
    assert sig.probability < 0.25, f"news-domain false match: {sig.probability:.3f}"


def test_affiliate_spam_still_flagged():
    """True positives intact: shortener + promo/bait reads HIGH."""
    spam = [
        "🚀 Use my promo code BOT20! Link in bio https://bit.ly/save",
        "🔥 SMASH subscribe! Free shipping with my code bit.ly/deal",
        "Click the link, limited time! 💰 linktr.ee/me",
    ] * 6
    sig = analyze_engagement(_posts(spam))
    assert sig.probability > 0.6, f"affiliate spam under-flagged: {sig.probability:.3f}"


def test_x_tco_wrapped_links_overflag_is_measured_and_known():
    """CHARACTERIZATION of a REAL, measured false positive (NOT an endorsement).

    On X every URL is t.co-wrapped and stored unexpanded, so a legitimate
    link-sharer trips the shortener guard and reads ELEVATED. This asserts the
    *current* behaviour so the eventual fix (expand t.co / neutralise t.co on X)
    fails this test loudly and updates it. Out of the measure-only scope to fix.
    """
    legit_x = [
        "Important thread on the election data https://t.co/abc123",
        "New report out today, worth a read https://t.co/def456",
        "Source for the earlier claim https://t.co/ghi789",
        "Good analysis here https://t.co/jkl012",
        "Filed my piece on this https://t.co/mno345",
        "Context in the replies https://t.co/pqr678",
    ] * 3
    sig = analyze_engagement(_posts(legit_x))
    # Documented over-flag: t.co counts every legit X link as promotional.
    assert sig.sub_signals["url_inclusion_rate"] > 0.5
    assert sig.probability >= 0.5, (
        "t.co over-flag changed — if a fix expanded t.co or neutralised it on X, "
        f"update this characterization test. measured={sig.probability:.3f}"
    )
