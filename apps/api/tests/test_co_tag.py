"""Phase 3 — the co_tag IO-native network detector."""

from __future__ import annotations

from app.detection.coordination.co_tag import CoTagEntry, detect_co_tag, extract_tags


def test_extract_tags_hashtags_and_mentions():
    tags = extract_tags(["love #FreeTheWorld and RT @LeaderX now", "#freetheworld AGAIN"])
    assert tags == {"#freetheworld", "@leaderx"}  # lower-cased, deduped, incl. RT target


def test_co_tag_clusters_shared_campaign_targets():
    shared = ["#FreeOurNation @GreatLeader #VoteNow rise up patriots",
              "@GreatLeader #VoteNow #FreeOurNation stand together today"]
    entries = [CoTagEntry(f"b{i}", f"b{i}", extract_tags(shared)) for i in range(4)]
    f = detect_co_tag(entries)
    assert f.method == "co_tag"
    assert f.clusters and len(f.clusters[0].members) >= 3
    assert f.overall_score > 0.5 and f.confidence > 0.0


def test_co_tag_silent_on_diverse_accounts():
    texts = [["#cooking pasta tonight with @foodie tips"],
             ["#python debugging a race condition @devtips"],
             ["#garden tomatoes finally ripe @plantlife"],
             ["#cinema noir double feature @filmclub"]]
    entries = [CoTagEntry(f"h{i}", f"h{i}", extract_tags(texts[i])) for i in range(4)]
    f = detect_co_tag(entries)
    assert not f.clusters  # no shared targets → no coordination


def test_co_tag_abstains_without_tags():
    entries = [CoTagEntry(f"x{i}", f"x{i}", set()) for i in range(4)]
    f = detect_co_tag(entries)
    assert f.confidence == 0.0 and not f.clusters
