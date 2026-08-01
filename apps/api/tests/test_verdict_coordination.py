"""Coordinated-campaign detection from omi scores and verdict text alone.

The behaviours pinned here are the ones that separate a real coordination detector from something
that just re-reports the score column. Three of them cost a correct answer during development and
are regression tests, not aspirations:

* a stratified permutation test degenerates when the cluster fills its own score band;
* a density-based "cohort" larger than the batch's own majority is the batch, not a cohort;
* a naive text similarity over verdicts written by ONE model measures the model, not the accounts.
"""
from __future__ import annotations

from app.campaigns.verdict_coordination import (
    MAX_COHORT_SHARE,
    ProfileResult,
    analyze,
    campaign_signature,
    combine_coordination,
    extract_features,
    handle_skeleton,
    label_cluster,
    signature_similarity,
)


# --------------------------------------------------------------------------------------------- #
# The worked example: an operation, a fan community, ordinary people, and a lone wolf.
# --------------------------------------------------------------------------------------------- #
def _script(handle: str, day: str, age: int, posts: int, ratio: float, quote: str) -> str:
    return (
        f"Account created 2024-03-{day}, {age} days old, with {posts} posts and a "
        f"following-to-followers ratio of {ratio}. Nearly every post is a variation of "
        f'"{quote}". No bio, unverified. The repetition and the promotional framing are the '
        f"basis for the score. Overturned by evidence of unscripted conversation."
    )


_QUOTE = "Best signal group on TG, DM for entry, 400% last week"

WORKED_EXAMPLE = [
    ProfileResult("u1", 78, _script("cryptoalex8837", "04", 141, 9, 21.5, _QUOTE),
                  handle="cryptoalex8837"),
    ProfileResult("u2", 81, _script("cryptomaria9014", "09", 136, 11, 19.8, _QUOTE),
                  handle="cryptomaria9014"),
    ProfileResult("u3", 74, _script("cryptojonas7261", "11", 134, 8, 24.0,
                                    "Best signal group on TG - DM for entry, 400% last week"),
                  handle="cryptojonas7261"),
    ProfileResult("u4", 79, _script("cryptolena6620", "06", 139, 10, 20.9, _QUOTE),
                  handle="cryptolena6620"),
    ProfileResult("u5", 24, (
        'Account created March 2019, about 5.4 years old, 3,180 posts, following-to-followers '
        'ratio of 0.8. A fan account: enthusiastic and repetitive about one director, writes '
        '"I have seen this six times and I am going again". Fan accounts are repetitive by '
        'nature, which is the innocent explanation here and it holds.'
    ), handle="LauraWatchesFilm"),
    ProfileResult("u6", 31, (
        'Created June 2018, roughly 6.1 years old, 2,410 posts, ratio of 1.1. Fan account, posts '
        'about the same director constantly, writes "the practical effects still hold up". '
        'Enthusiasm and repetition are ordinary for a hobby account.'
    ), handle="mattfilmnerd"),
    ProfileResult("u7", 28, (
        'Created November 2017, about 6.7 years old, 4,902 posts, ratio of 0.6. Hobby account for '
        'film discussion, writes "genuinely one of the best openings ever shot". Repetitive '
        'subject matter is expected and is not evidence of automation.'
    ), handle="cinema_ruth"),
    ProfileResult("u8", 91, (
        'Created 2025-01-20, 12 days old, 220 posts, following-to-followers ratio of 310.0. Posts '
        'link-shortened giveaway spam, writes "CLAIM YOUR PRIZE NOW bit.ly/xxx" at unrelated '
        'accounts. Volume, age and the link pattern converge.'
    ), handle="Prize_Winner_Now"),
    ProfileResult("u9", 12, (
        'Created August 2011, about 13 years old, 8,900 posts, ratio of 1.4. Ordinary personal '
        'account with varied conversation over many years.'
    ), handle="tom_hendricks"),
    ProfileResult("u10", 19, (
        'Created February 2014, roughly 10.5 years old, 1,205 posts, ratio of 2.2. Personal '
        'account, writes in English as a second language, which is not a tell. Varied topics.'
    ), handle="Priya_K"),
    ProfileResult("u11", 44, (
        'Created April 2021, about 3.3 years old, 640 posts, ratio of 0.9. A business account: '
        'posts are promotional by nature, writes "todays soup is minestrone". Promotional content '
        'is expected for a storefront and is the innocent explanation.'
    ), handle="NorthsideDeli"),
]


def test_the_operation_is_found_and_labelled_a_campaign():
    res = analyze(WORKED_EXAMPLE)
    camps = [c for c in res.clusters if c.label == "coordinated_bot_campaign"]
    assert len(camps) == 1, [(c.label, c.members) for c in res.clusters]
    assert set(camps[0].members) == {"u1", "u2", "u3", "u4"}
    assert camps[0].coordination >= 0.85
    assert camps[0].botness >= 0.55


def test_the_campaign_is_carried_by_discriminative_views_not_by_score():
    """The finding must rest on the accounts' own words and shape, not on their scores agreeing."""
    camp = next(c for c in analyze(WORKED_EXAMPLE).clusters
                if c.label == "coordinated_bot_campaign")
    assert "quote_echo" in camp.views
    assert camp.components["discriminative_views"] >= 2
    assert camp.components["quote_strength"] > 0.9


def test_the_lone_wolf_is_isolated_not_clustered():
    """A 91-scoring obvious bot with no partners is a lone wolf, not a one-member campaign."""
    res = analyze(WORKED_EXAMPLE)
    assert "u8" in res.lone_wolves
    assert all("u8" not in c.members for c in res.clusters)


def test_ordinary_people_are_left_alone():
    """The fan accounts, the personal accounts and the deli must not be swept into anything.
    A false positive here is a published claim about a real person who cannot check it."""
    res = analyze(WORKED_EXAMPLE)
    for pid in ("u5", "u6", "u7", "u9", "u10", "u11"):
        assert all(pid not in c.members for c in res.clusters), f"{pid} was clustered"


def test_every_member_gets_its_own_evidence():
    """A cluster-level score is not evidence about the person in position seven. Each named account
    carries the specific links that put it there."""
    camp = next(c for c in analyze(WORKED_EXAMPLE).clusters
                if c.label == "coordinated_bot_campaign")
    for m in camp.members:
        assert camp.per_member[m], f"{m} has no individual justification"
        assert any("linked to" in line for line in camp.per_member[m])


# --------------------------------------------------------------------------------------------- #
# The confounds. These are the tests that make the system more than a score re-report.
# --------------------------------------------------------------------------------------------- #
def test_a_shared_score_band_alone_is_not_a_campaign():
    """Eight accounts all scoring ~80 for entirely different, individually-stated reasons.

    A naive TF-IDF over verdicts clusters these instantly, because high-scoring verdicts share
    vocabulary BY CONSTRUCTION. Band-conditional centring plus the corroboration gate must refuse."""
    reasons = [
        ("a1", "Account created January 2015, 9 years old, 4,000 posts, ratio of 1.2. Posts "
               "link-shortened affiliate offers, writes \"grab yours here\"."),
        ("a2", "Created May 2016, 8 years old, 12,000 posts, ratio of 0.4. Extremely high volume "
               "of short replies, writes \"agreed 100\"."),
        ("a3", "Created July 2012, 12 years old, 900 posts, ratio of 3.1. Long dormancy then a "
               "sudden burst, writes \"back after a while\"."),
        ("a4", "Created March 2020, 4 years old, 6,600 posts, ratio of 0.9. Reposts headlines "
               "constantly, writes \"breaking news\"."),
        ("a5", "Created October 2013, 11 years old, 2,200 posts, ratio of 2.0. Argumentative "
               "replies to strangers, writes \"you are wrong about that\"."),
        ("a6", "Created December 2009, 15 years old, 30,000 posts, ratio of 0.2. Automated "
               "weather updates, writes \"today high 21c\"."),
        ("a7", "Created February 2022, 2 years old, 480 posts, ratio of 5.5. Sells merchandise, "
               "writes \"restock friday\"."),
        ("a8", "Created June 2011, 13 years old, 7,700 posts, ratio of 1.7. Sports commentary, "
               "writes \"what a finish\"."),
    ]
    batch = [ProfileResult(pid, 80, text, handle=pid) for pid, text in reasons]
    res = analyze(batch)
    assert not [c for c in res.clusters if c.label == "coordinated_bot_campaign"], (
        "a shared score band was reported as a campaign: "
        f"{[(c.label, c.members, c.coordination) for c in res.clusters]}"
    )


def test_protocol_boilerplate_alone_does_not_link_accounts():
    """Every verdict shares the protocol's scaffolding. Document-frequency subtraction must strip it
    so identical framing with different facts produces no cluster."""
    tmpl = (
        "Account created {m} {y}, about {a} years old, {p} posts, following-to-followers ratio of "
        "{r}. The evidence is stated below and this would be overturned by a longer history."
    )
    batch = [
        ProfileResult("b1", 30, tmpl.format(m="April", y=2011, a=13, p=9000, r=1.1), handle="ann_h"),
        ProfileResult("b2", 33, tmpl.format(m="August", y=2015, a=9, p=430, r=2.4), handle="Rob_T"),
        ProfileResult("b3", 29, tmpl.format(m="March", y=2019, a=5, p=12000, r=0.7), handle="k_lee"),
        ProfileResult("b4", 35, tmpl.format(m="July", y=2013, a=11, p=2200, r=1.9), handle="MJ99x"),
        ProfileResult("b5", 31, tmpl.format(m="May", y=2010, a=14, p=700, r=3.3), handle="sam-p"),
    ]
    res = analyze(batch)
    assert not [c for c in res.clusters if c.coordination >= 0.6], (
        f"boilerplate produced a cluster: {[(c.members, c.coordination) for c in res.clusters]}"
    )


def test_a_numeric_blob_bigger_than_the_batch_majority_is_rejected():
    """DBSCAN returns the population's centre of mass as its densest region. On a small scan that
    region is just 'ordinary accounts', and reporting it as a cohort swept six unrelated real people
    into a coordinated cluster the first time this ran."""
    batch = [
        ProfileResult(f"n{i}", 20 + i,
                      f"Created March 201{i % 5}, about {8 + i % 3} years old, "
                      f"{2000 + i * 40} posts, ratio of 1.{i % 4}. Ordinary personal account.",
                      handle=f"person_{i}")
        for i in range(10)
    ]
    res = analyze(batch)
    for c in res.clusters:
        assert len(c.members) / len(batch) <= MAX_COHORT_SHARE + 0.2, (
            f"a majority blob was reported as a cluster: {c.members}"
        )


# --------------------------------------------------------------------------------------------- #
# The degenerate null. Regression test for a bug that suppressed a correct detection.
# --------------------------------------------------------------------------------------------- #
def test_a_stratified_null_that_cannot_vary_is_reported_not_believed():
    """When a cluster fills its own score band, every permuted draw IS the cluster, the null
    collapses onto the observation, and p lands near 0.5. That is zero power, not evidence of
    nothing unusual. The tiering must widen the strata and say so."""
    res = analyze(WORKED_EXAMPLE)
    camp = next(c for c in res.clusters if c.label == "coordinated_bot_campaign")
    assert camp.significance.strata != "band", (
        "the exact-band null was usable here; the fixture no longer reproduces the bug"
    )
    assert camp.significance.p_value is not None
    assert camp.significance.p_value < 0.05
    assert "degenerate" in camp.significance.note


def test_an_untestable_batch_lowers_confidence_rather_than_the_score():
    """`p_value is None` means the question could not be asked. Treating it as 'not significant' is
    how a cluster with 100%-identical quoted text gets thrown away."""
    from app.campaigns.verdict_coordination import Significance

    comps = {
        "density": 1.0, "cohesion": 0.99, "view_multiplicity": 1.0,
        "discriminative_views": 3.0, "size_prior": 0.4,
        "quote_strength": 1.0, "cohort_strength": 0.9, "handle_strength": 0.5,
    }
    untested = combine_coordination(comps, Significance(None, "none", 0.0, "too small"))
    insignificant = combine_coordination(comps, Significance(0.9, "band", 500.0, "ok"))
    assert untested > insignificant, (
        "an untested cluster was penalised as heavily as one the null explained"
    )
    assert untested >= 0.6, "strong discriminative evidence was thrown away for lack of a null"


def test_a_null_with_real_power_still_suppresses_a_dense_but_ordinary_group():
    from app.campaigns.verdict_coordination import Significance

    comps = {
        "density": 1.0, "cohesion": 0.8, "view_multiplicity": 0.66,
        "discriminative_views": 1.0, "size_prior": 0.5,
        "quote_strength": 0.0, "cohort_strength": 0.7, "handle_strength": 0.0,
    }
    assert combine_coordination(comps, Significance(0.42, "band", 5000.0, "ok")) <= 0.25


# --------------------------------------------------------------------------------------------- #
# Labelling: coordination and botness are separate axes
# --------------------------------------------------------------------------------------------- #
def test_a_coordinated_group_of_low_scorers_is_not_called_a_bot_campaign():
    """Fan communities, brands and news feeds genuinely coordinate. Recognising real coordination
    among real people is a correct finding; calling it a bot campaign is the defamation case."""
    from app.campaigns.verdict_coordination import Significance

    sig = Significance(0.01, "band", 900.0, "ok")
    assert label_cluster(0.85, 0.20, sig, 6) == "coordinated_authentic"
    assert label_cluster(0.85, 0.80, sig, 6) == "coordinated_bot_campaign"
    assert label_cluster(0.85, 0.45, sig, 6) == "coordinated_mixed"


def test_a_confident_negative_is_reported_as_organic_not_ambiguous():
    """'Ambiguous' has to keep meaning 'we could not tell'. A group the null reproduces easily, whose
    members score low, is the most reassuring finding a report can carry."""
    from app.campaigns.verdict_coordination import Significance

    assert label_cluster(0.3, 0.2, Significance(0.8, "band", 900.0, "ok"), 5) == "organic_cluster"


def test_supporting_views_alone_cannot_produce_a_strong_verdict():
    from app.campaigns.verdict_coordination import SUPPORTING_ONLY_CEILING, Significance

    comps = {
        "density": 1.0, "cohesion": 1.0, "view_multiplicity": 1.0,
        "discriminative_views": 0.0, "size_prior": 1.0,
        "quote_strength": 0.0, "cohort_strength": 0.0, "handle_strength": 0.0,
    }
    got = combine_coordination(comps, Significance(0.001, "band", 9000.0, "ok"))
    assert got <= SUPPORTING_ONLY_CEILING


# --------------------------------------------------------------------------------------------- #
# Cross-investigation / cross-tenant linkage
# --------------------------------------------------------------------------------------------- #
def test_the_same_operation_links_across_investigations_with_zero_shared_accounts():
    """The requirement that member-set matching cannot serve: an operation that rotates its accounts
    between posts shares no members with its own previous run, but keeps its script, its handle
    factory and its creation cohort."""
    run_a = [
        ProfileResult(f"A{i}", 76 + i, _script(f"cryptoone{i}111", "04", 140 + i, 9, 21.0, _QUOTE),
                      handle=f"cryptoone{i}111")
        for i in range(4)
    ]
    run_b = [
        ProfileResult(f"B{i}", 75 + i, _script(f"cryptotwo{i}222", "07", 138 + i, 10, 22.0, _QUOTE),
                      handle=f"cryptotwo{i}222")
        for i in range(4)
    ]
    assert not ({p.profile_id for p in run_a} & {p.profile_id for p in run_b})

    ca = analyze(run_a).clusters
    cb = analyze(run_b).clusters
    assert ca and cb, "one of the runs produced no cluster"

    sim = signature_similarity(ca[0].signature, cb[0].signature)
    assert sim >= 0.4, f"the same script did not link across runs (signature similarity {sim})"
    assert set(ca[0].signature_bands) & set(cb[0].signature_bands), (
        "no LSH band collided, so the indexed lookup would never surface the match"
    )


def test_a_batch_that_is_entirely_one_operation_cannot_be_scored_from_within():
    """The system measures coordination RELATIVE TO THE BATCH, so a scan containing nothing but one
    operation has no background to contrast against and cannot call it coordinated. Everything in
    that batch is equally similar, which is exactly what the null reports.

    This is a real limitation, not a bug, and the mitigation is the signature: the same operation
    seen inside a normal comment section scores 0.99, and the two link. Do not "fix" this by
    removing the null; that would trade a known blind spot for an unknown false-positive rate.
    """
    pure = [
        ProfileResult(f"A{i}", 76 + i, _script(f"cryptoone{i}111", "04", 140 + i, 9, 21.0, _QUOTE),
                      handle=f"cryptoone{i}111")
        for i in range(4)
    ]
    alone = analyze(pure).clusters[0]
    assert alone.label != "coordinated_bot_campaign"
    assert alone.p_value is None  # no null was constructible

    in_situ = [c for c in analyze(pure + WORKED_EXAMPLE[4:]).clusters
               if set(c.members) >= {"A0", "A1"}][0]
    assert in_situ.label == "coordinated_bot_campaign"
    assert in_situ.coordination > alone.coordination

    # The rescue: the blind case still links to the detected one.
    assert signature_similarity(alone.signature, in_situ.signature) >= 0.8


def test_unrelated_operations_do_not_link():
    """The other half: linkage must not collapse every campaign into one."""
    run_a = [
        ProfileResult(f"A{i}", 78, _script(f"cryptoone{i}111", "04", 140, 9, 21.0, _QUOTE),
                      handle=f"cryptoone{i}111")
        for i in range(4)
    ]
    run_c = [
        ProfileResult(f"C{i}", 77, (
            f"Created 2023-11-0{i + 1}, {400 + i} days old, {60 + i} posts, ratio of 8.{i}. "
            f'Repeats "Follow for follow back, engagement pod open" in replies. No bio.'
        ), handle=f"growth_pod_{i}")
        for i in range(4)
    ]
    ca, cc = analyze(run_a).clusters, analyze(run_c).clusters
    assert ca and cc
    assert signature_similarity(ca[0].signature, cc[0].signature) < 0.4


def test_a_signature_reveals_nothing_about_who_was_scanned():
    """Cross-tenant linkage is only acceptable if the linking key carries no customer information.
    The sketch is built from script, handle template and cohort, never from profile ids."""
    feats = {f.profile_id: f for f in extract_features(WORKED_EXAMPLE)}
    sketch_1, _ = campaign_signature({"u1", "u2", "u3", "u4"}, feats)
    renamed = {}
    for pid, f in feats.items():
        f.profile_id = f"zz_{pid}"
        renamed[f.profile_id] = f
    sketch_2, _ = campaign_signature({"zz_u1", "zz_u2", "zz_u3", "zz_u4"}, renamed)
    assert sketch_1 == sketch_2, "the signature changed when only the profile ids changed"


# --------------------------------------------------------------------------------------------- #
# Plumbing and degenerate inputs
# --------------------------------------------------------------------------------------------- #
def test_it_adapts_to_the_engines_existing_cluster_shape():
    """So CampaignService.record_clusters persists these with no second code path."""
    out = analyze(WORKED_EXAMPLE).to_coordination_clusters()
    assert out and all(c.method == "verdict_coordination" for c in out)
    assert all(c.members and c.evidence for c in out)


def test_an_empty_batch_does_not_explode():
    res = analyze([])
    assert res.clusters == [] and res.lone_wolves == []


def test_verdicts_with_no_recoverable_structure_abstain_loudly():
    """If the analyst produced prose with no quotes and no figures, the discriminative views cannot
    fire. The batch notes must say so rather than letting weak views look authoritative."""
    batch = [ProfileResult(f"x{i}", 50 + i, "This account seems unusual to me.", handle=f"x{i}")
             for i in range(6)]
    res = analyze(batch)
    assert any("quoted text" in n for n in res.batch_notes)
    assert not [c for c in res.clusters if c.label == "coordinated_bot_campaign"]


def test_handle_skeleton_collapses_runs():
    assert handle_skeleton("cryptoalex8837") == "a9"
    assert handle_skeleton("Priya_K") == "Aa_A"
    assert handle_skeleton("@tom_hendricks") == "a_a"
    assert handle_skeleton("") is None


def test_numerics_are_parsed_from_prose():
    f = extract_features([ProfileResult("p", 70, (
        "Created 2024-03-04, 141 days old, with 9 posts and a following-to-followers ratio of "
        '21.5. Writes "buy now".'
    ), handle="p")])[0]
    assert f.numerics["age_days"] == 141
    assert f.numerics["posts"] == 9
    assert f.numerics["ratio"] == 21.5
    assert f.cohort == "2024-03"
    assert f.quotes == ["buy now"]


def test_significance_is_deterministic():
    """The output is a published claim about named people; it must not move between runs."""
    a = analyze(WORKED_EXAMPLE)
    b = analyze(WORKED_EXAMPLE)
    assert [c.members for c in a.clusters] == [c.members for c in b.clusters]
    assert [c.coordination for c in a.clusters] == [c.coordination for c in b.clusters]
    assert [c.p_value for c in a.clusters] == [c.p_value for c in b.clusters]
