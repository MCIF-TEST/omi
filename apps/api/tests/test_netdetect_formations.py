"""Operations that persist, and the accounts that walk into them.

`detect` answers "are these accounts, in this corpus, coordinated?" and then forgets. This suite
covers the layer that remembers: a formation is an ENTITY with a lifecycle, and a newly scanned
account can be placed into one catalogued weeks earlier in a different investigation.

THE MEASUREMENTS THAT JUSTIFY IT, taken before any of it was wired up:

* Held-out members of a known operation, scored against its profile in a corpus it has never seen:
  40 of 40 assigned correctly across five runs of two operators, 0 wrong formation, and 0 false
  assignments among 300 organic accounts.
* Profile similarity separates operators by an order of magnitude: the same operator scored 0.356
  to 0.770 across runs, different operators 0.022 to 0.036.
* The discipline dial degrades honestly. A well-run operation becomes UNASSIGNABLE (0 of 8 at
  discipline 1.0) rather than wrongly assigned, and never produces a false positive on the way down.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import tests.netdetect_corpora as C
from app.netdetect import detect_from_commenters
from app.netdetect.assign import (
    ASSIGN_THRESHOLD,
    MIN_HARD_EVIDENCE,
    best,
    rank,
    score_against,
)
from app.netdetect.features import profile_from_commenter
from app.netdetect.formation import (
    CONCEALED_MEDIAN_SCORE,
    build_profile,
    composition_of,
    merge_profiles,
    phase_of,
    profile_similarity,
)
from app.netdetect.significance import Corpus
from app.netdetect.types import HARD_FAMILIES as HARD_FAMILIES_FOR_TEST

SHUFFLES = 20
_LEARNED: dict[tuple, object] = {}


def learn(operator: str = "stadium", *, bg: int = 5, op: int = 6, discipline: float = 0.0):
    """A formation profile, learned the way the pipeline learns one.

    Cached: detection is seconds per corpus and several tests want the same profile. Safe only
    because the detector is deterministic, which `test_netdetect.py` pins in three subprocesses.
    """
    key = (operator, bg, op, discipline)
    if key not in _LEARNED:
        rows = C.organic_population(60, seed=bg) + C.planted_operation(
            8, seed=op, discipline=discipline, operator=operator)
        result = detect_from_commenters(rows, shuffles=SHUFFLES)
        hits = [c for c in result.findings
                if sum(1 for m in c.members if m.startswith("op")) >= 4]
        _LEARNED[key] = (build_profile(hits[0], result.corpus), result) if hits else (None, result)
    return _LEARNED[key]


def corpus_of(operator: str, bg: int, op: int, discipline: float = 0.0) -> Corpus:
    rows = C.organic_population(60, seed=bg) + C.planted_operation(
        8, seed=op, discipline=discipline, operator=operator)
    return Corpus([profile_from_commenter(r) for r in rows if r.get("external_id")])


# ==================================================================================================
# The fixture had to grow a second operator before any of this was testable
# ==================================================================================================
def test_two_operators_are_actually_different_operations():
    """EVERY FIELD THAT IDENTIFIES AN OPERATOR USED TO BE HARDCODED, so `planted_operation(seed=6)`
    and `planted_operation(seed=99)` were two account sets running the SAME operation: same script,
    tool, signup week, targets, bio and handle factory. The seed varied only filler text.

    Nothing noticed, because every test asked whether the operation was FOUND and none asked whether
    it was told apart from a different one. That question is the whole of assignment."""
    a = C.planted_operation(4, seed=6, operator="stadium")
    b = C.planted_operation(4, seed=6, operator="clinic")
    assert a[0]["bio"] != b[0]["bio"]
    assert a[0]["handle"].split("_")[0] != b[0]["handle"].split("_")[0]
    assert (a[0]["recent_activity"][0]["source_client"]
            != b[0]["recent_activity"][0]["source_client"])
    assert a[0]["account_created_at"] != b[0]["account_created_at"]


# ==================================================================================================
# Assignment
# ==================================================================================================
def test_a_member_is_recognised_in_an_investigation_the_profile_never_saw():
    """THE CAPABILITY. An operation learned from one post, an account scanned under another."""
    profile, _ = learn()
    held_out = corpus_of("stadium", bg=31, op=6)
    members = [a for a in held_out.accounts if a.external_id.startswith("op")]
    assert members

    assigned = [a for a in members if score_against(a, profile, formation_key="F").assigned]
    assert len(assigned) == len(members), "a known operation's members were not recognised"


def test_ordinary_accounts_in_the_same_comment_section_are_not_assigned():
    profile, _ = learn()
    held_out = corpus_of("stadium", bg=31, op=6)
    strangers = [a for a in held_out.accounts if not a.external_id.startswith("op")]
    assert len(strangers) >= 50

    wrong = [a for a in strangers if score_against(a, profile, formation_key="F").assigned]
    assert wrong == [], f"{len(wrong)} ordinary accounts were placed in an operation"


def test_a_member_of_one_operation_is_not_placed_in_another():
    """THE FALSE POSITIVE `MIN_HARD_EVIDENCE` EXISTS FOR, and it was real before the floor.

    Measured: a true member scored against its OWN formation carried 17.8 of evidence in the
    operator's own acts across five families. The same member against an UNRELATED operation carried
    0.0, its whole match being text and timing, which is what any two automated accounts share.
    Without the floor it cleared the posterior bar and would have been named in the wrong operation.
    """
    stadium, _ = learn("stadium", bg=5, op=6)
    clinic, _ = learn("clinic", bg=17, op=23)
    assert clinic is not None, "the clinic operator produced no finding; fixture changed"

    member = next(a for a in corpus_of("stadium", bg=31, op=6).accounts
                  if a.external_id.startswith("op"))

    own = score_against(member, stadium, formation_key="STADIUM")
    other = score_against(member, clinic, formation_key="CLINIC")

    assert own.assigned
    assert own.hard_evidence >= MIN_HARD_EVIDENCE
    assert not other.assigned, "a member was placed in an unrelated operation"
    assert other.hard_evidence < MIN_HARD_EVIDENCE

    # WHICH guard refuses it is not the claim; that it is refused, and that the hard-evidence floor
    # would refuse it, are. Since the operation carries a campaign hashtag and a brigading target,
    # the wrong formation now matches on fewer families and the family-count guard fires first, so
    # pinning one refusal string was pinning the order the guards happen to run in.
    assert other.refused, "the wrong formation was neither assigned nor refused"
    assert any(reason in other.refused for reason in (
        "operator's own acts", "kind of evidence",
    )), f"refused for an unrecognised reason: {other.refused}"


def test_ranking_survives_the_certainty_cap():
    """The cap is a statement about what may be CLAIMED. Applying it to the ordering too would
    collapse every strong match to one value and make "which formation" unanswerable, which is the
    question this module exists for."""
    stadium, _ = learn("stadium", bg=5, op=6)
    clinic, _ = learn("clinic", bg=17, op=23)
    member = next(a for a in corpus_of("stadium", bg=31, op=6).accounts
                  if a.external_id.startswith("op"))

    ordered = rank(member, {"STADIUM": stadium, "CLINIC": clinic})
    assert ordered[0].formation_key == "STADIUM"
    assert ordered[0].raw_log_lr > ordered[1].raw_log_lr, (
        "the uncapped value did not separate the two formations, so ranking is blind"
    )


def test_a_well_run_operation_becomes_unassignable_rather_than_wrongly_assigned():
    """The honest failure mode, and the same shape as the dilution curve `detect` already reports.
    A disciplined operation emits no rare features; no statistics recover a signal never sent."""
    profile, _ = learn()
    loose = corpus_of("stadium", bg=31, op=6, discipline=0.0)
    tight = corpus_of("stadium", bg=31, op=6, discipline=1.0)

    def hits(corpus):
        return sum(1 for a in corpus.accounts
                   if a.external_id.startswith("op")
                   and score_against(a, profile, formation_key="F").assigned)

    assert hits(loose) >= 6
    assert hits(tight) == 0, "a disciplined operation was assigned on evidence it never emitted"

    strangers_wrongly = [
        a for a in tight.accounts
        if not a.external_id.startswith("op")
        and score_against(a, profile, formation_key="F").assigned
    ]
    assert strangers_wrongly == [], "degradation produced false positives instead of silence"


@pytest.mark.parametrize("label,rows", [
    ("professional beat", C.organic_population(40, seed=9) + C.professional_beat(10, seed=21)),
    ("fan community", C.organic_population(40, seed=9) + C.fan_community(12, seed=33)),
    ("pure organic", C.organic_population(60, seed=3)),
])
def test_innocent_populations_are_never_assigned_to_an_operation(label, rows):
    stadium, _ = learn()
    clinic, _ = learn("clinic", bg=17, op=23)
    profiles = {"STADIUM": stadium, "CLINIC": clinic}
    corpus = Corpus([profile_from_commenter(r) for r in rows if r.get("external_id")])

    placed = [a.external_id for a in corpus.accounts if best(a, profiles) is not None]
    assert placed == [], f"{label}: {len(placed)} innocent accounts were placed in an operation"


def test_no_known_formation_is_never_read_as_uncoordinated():
    """An operation nobody has catalogued is exactly what `detect` exists to find, so a null from
    `best()` must not be reported as innocence. The refusals are returned so a reader can see the
    system looked."""
    profile, _ = learn()
    ring = C.organic_population(40, seed=12) + C.amplifier_ring(8, seed=13)
    corpus = Corpus([profile_from_commenter(r) for r in ring if r.get("external_id")])
    member = next(a for a in corpus.accounts if a.external_id.startswith("amp"))

    assert best(member, {"STADIUM": profile}) is None
    results = rank(member, {"STADIUM": profile})
    assert results and (results[0].refused or results[0].abstained), (
        "a non-match came back with no stated reason, which reads as an all-clear"
    )


def test_a_thin_profile_abstains_rather_than_matching_everything():
    from app.netdetect.formation import FormationProfile, ProfileFeature

    thin = FormationProfile(
        features=[ProfileFeature("text", "shingle", "a lone phrase", surprise=1.0, prevalence=0.01)],
        families={"text"},
    )
    member = next(a for a in corpus_of("stadium", bg=31, op=6).accounts
                  if a.external_id.startswith("op"))
    out = score_against(member, thin, formation_key="THIN")
    assert not out.assigned
    assert out.abstained and "identifying evidence" in out.abstained


def test_assignment_never_reads_the_accounts_own_suspicion_score():
    """Same rule as detection, same reason: a competent operation's accounts each look ordinary, and
    gating on suspicion would refuse exactly the members worth finding."""
    profile, _ = learn()
    corpus = corpus_of("stadium", bg=31, op=6)
    member = next(a for a in corpus.accounts if a.external_id.startswith("op"))

    baseline = score_against(member, profile, formation_key="F")
    for score, tier in ((0.0, "low"), (99.0, "high"), (None, None)):
        member.score, member.tier = score, tier
        again = score_against(member, profile, formation_key="F")
        assert again.log_lr == baseline.log_lr
        assert again.assigned == baseline.assigned


# ==================================================================================================
# Identity: recognising the operator, not the run
# ==================================================================================================
def test_the_same_operator_looks_like_itself_and_a_different_one_does_not():
    """MEASURED: same operator 0.356 to 0.770 across runs and backgrounds, different operators 0.022
    to 0.036. The match threshold sits inside that gap, and is deliberately looser than
    `tracking/signature.SIGNATURE_MATCH_THRESHOLD` (0.40), which would have missed the worst
    genuine match."""
    from app.netdetect.registry import FORMATION_MATCH_THRESHOLD

    a, _ = learn("stadium", bg=5, op=6)
    b, _ = learn("stadium", bg=31, op=6)
    other, _ = learn("clinic", bg=17, op=23)

    same = profile_similarity(a, b)
    different = profile_similarity(a, other)
    assert same >= FORMATION_MATCH_THRESHOLD, f"one operator did not match itself ({same:.3f})"
    assert different < FORMATION_MATCH_THRESHOLD, f"two operators matched ({different:.3f})"
    assert same > different * 3, "the two distributions are no longer clearly separated"


def test_merging_a_repeat_sighting_discounts_it():
    """Two sightings of one operation are not two independent observations: the same script on two
    posts is one script. Matches `tracking/graph.REPEAT_DISCOUNT` so the layers agree."""
    a, _ = learn("stadium", bg=5, op=6)
    merged = merge_profiles(a, a)
    by_token = {f.token(): f for f in a.features}
    for feature in merged.features:
        prior = by_token.get(feature.token())
        if prior is None:
            continue
        assert feature.surprise <= prior.surprise * 2, "a repeat was counted at full weight"
        assert feature.surprise >= prior.surprise, "a repeat weakened the evidence"


# ==================================================================================================
# Composition: the OMI score, used where it belongs
# ==================================================================================================
def test_a_coordinated_group_of_ordinary_looking_accounts_is_the_headline_case():
    """THE FINDING ONLY THIS SYSTEM PRODUCES. Individually these accounts read as people; the null
    says they are coordinated anyway. Reading the score into DETECTION would have hidden them, which
    is exactly what the old 70+ cohort filter did."""
    comp = composition_of([30.0, 28.0, 34.0, 22.0, 31.0])
    assert comp.posture == "concealed"
    assert comp.concealment is True
    assert comp.median <= CONCEALED_MEDIAN_SCORE
    assert "would not have flagged them" in comp.note


def test_an_already_flagged_group_is_described_as_the_lesser_finding():
    comp = composition_of([88.0, 79.0, 92.0, 85.0])
    assert comp.posture == "overt"
    assert comp.concealment is False


def test_a_missing_score_is_counted_and_never_imputed():
    """Substituting a mean would let a formation of mostly-unscored accounts present a confident
    posture built from two numbers."""
    comp = composition_of([None, None, 30.0, None])
    assert comp.unscored == 3
    assert comp.posture == "unknown"
    assert comp.median is None
    assert "gap in what was scanned" in comp.note


# ==================================================================================================
# Lifecycle
# ==================================================================================================
def test_an_operation_that_went_quiet_and_came_back_is_named_as_such():
    """RESURGENT ONLY EXISTS BECAUSE THE ENTITY SURVIVED THE GAP. No per-run detector can report it:
    it is a statement about two campaigns, not about one corpus."""
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    first = now - timedelta(days=200)

    assert phase_of(first, now - timedelta(days=90), now=now) == "dormant"
    assert phase_of(first, now, previous_phase="dormant", now=now) == "resurgent"
    assert phase_of(first, now, previous_phase="active", now=now) == "active"
    assert phase_of(now - timedelta(days=2), now, now=now) == "forming"


def test_an_unseen_formation_is_forming_rather_than_dormant():
    assert phase_of(None, None) == "forming"


# ==================================================================================================
# The registry, against a real database
# ==================================================================================================
def _seed(slug: str, rows: list[dict], target: str) -> None:
    from app.storage.db import get_session
    from app.storage.models import Investigation

    with get_session() as session:
        session.add(Investigation(
            user_id=1, slug=slug, label=slug, platform="x",
            input_url="https://x.com/i/status/1", target_id=target,
            kind="comprehensive",
            payload_json={"commenters": rows, "platform": "x"},
        ))
        session.commit()


def _client():
    from fastapi.testclient import TestClient

    from app.main import app
    return TestClient(app)


def test_a_second_campaign_resolves_to_the_same_operation():
    """THE POINT OF THE REGISTRY. Two findings, two posts, one adversary. A finding store would
    report two unrelated groups."""
    from app.storage.db import get_session
    from app.storage.models import NetdetectFormation

    client = _client()
    _seed("reg_a", C.organic_population(60, seed=5) + C.planted_operation(8, seed=6),
          "reg-post-a")
    _seed("reg_b", C.organic_population(60, seed=31) + C.planted_operation(8, seed=6),
          "reg-post-b")

    first = client.post(f"/v1/admin/netdetect/reg_a?shuffles={SHUFFLES}").json()
    assert first["findings"], "the fixture stopped producing a finding"
    client.post(f"/v1/admin/netdetect/reg_b?shuffles={SHUFFLES}")

    with get_session() as session:
        rows = list(session.execute(
            NetdetectFormation.__table__.select()
        ).mappings())
        keys = {r["formation_key"] for r in rows}
        assert len(keys) == 1, f"one operation was recorded as {len(keys)} formations"
        only = rows[0]
        assert only["sighting_count"] == 2, "a second distinct post was not counted as a sighting"
        assert only["member_count"] >= 8


def test_re_running_one_post_is_not_a_second_sighting():
    """An operator re-runs constantly while tuning. Counting that would let anyone inflate an
    operation's history by pressing a button, exactly as `tracking/graph` refuses for pairs."""
    from app.storage.db import get_session
    from app.storage.models import NetdetectFormation

    client = _client()
    _seed("reg_same", C.organic_population(60, seed=5) + C.planted_operation(8, seed=6),
          "reg-post-same")
    client.post(f"/v1/admin/netdetect/reg_same?shuffles={SHUFFLES}")
    client.post(f"/v1/admin/netdetect/reg_same?shuffles={SHUFFLES}")

    with get_session() as session:
        rows = [r for r in session.execute(NetdetectFormation.__table__.select()).mappings()
                if "reg-post-same" in (r["contexts_json"] or [])]
        assert rows and rows[0]["sighting_count"] == 1


def test_the_assign_route_is_reachable_and_not_shadowed_by_the_run_route():
    """A ROUTING BUG THAT LOOKED LIKE A DATA BUG. At `/assign` this was matched by
    `POST /{slug}` with slug="assign", so every call answered 404 "No such investigation" and read
    as a missing row. Nesting it under /formations makes a one-segment parameter unable to shadow
    it at all, which is structural rather than an ordering somebody has to remember."""
    client = _client()
    _seed("asg", C.organic_population(60, seed=5) + C.planted_operation(8, seed=6), "asg-post")
    client.post(f"/v1/admin/netdetect/asg?shuffles={SHUFFLES}")

    _seed("asg2", C.organic_population(60, seed=31) + C.planted_operation(8, seed=6), "asg-post-2")
    reply = client.post("/v1/admin/netdetect/formations/assign",
                        json={"slug": "asg2", "external_id": "op003"})
    assert reply.status_code == 200, reply.text[:300]
    body = reply.json()
    assert body["best"] is not None, "a known member was not placed"
    assert body["best"]["posterior"] >= ASSIGN_THRESHOLD
    assert body["best"]["hard_evidence"] >= MIN_HARD_EVIDENCE
    assert body["best"]["matched"], "an assignment arrived with no readable evidence"


def test_the_assignment_response_says_what_an_empty_result_does_not_mean():
    client = _client()
    _seed("asg3", C.organic_population(40, seed=77), "asg-post-3")
    body = client.post("/v1/admin/netdetect/formations/assign",
                       json={"slug": "asg3", "external_id": "org000"}).json()
    assert body["best"] is None
    note = body["note"].lower()
    assert "never that the account is uncoordinated" in note
    assert "omi score" in note


def test_an_account_the_investigation_never_scanned_is_a_404_not_an_empty_match():
    client = _client()
    _seed("asg4", C.organic_population(20, seed=7), "asg-post-4")
    reply = client.post("/v1/admin/netdetect/formations/assign",
                        json={"slug": "asg4", "external_id": "nobody_here"})
    assert reply.status_code == 404


# ==================================================================================================
# Guards for two bugs introduced while building this
# ==================================================================================================
def test_the_netdetect_columns_did_not_leak_onto_another_model():
    """A REAL BUG THAT SHIPPED, and 2474 tests did not catch it.

    `weak_members_json`, `attachment_note` and `attachment_checked` were added to `NetdetectFinding`
    with a `str.replace()` on text that appears in two model classes, so they landed on
    `CrossFinding` as well. Nothing failed: an unused column is invisible, and no test asserts that
    a model LACKS a field. It surfaced only because the boot upgrade pass then tried to build an
    index on a column the real table did not have.

    The harm is not the wasted column. `CrossFinding` advertised a membership test it never runs,
    and its `attachment_checked=False` would have read as "not checked" for a concept that does not
    apply to it."""
    from app.storage.models import CrossFinding, NetdetectFinding

    netdetect_only = (
        "weak_members_json", "attachment_note", "attachment_checked", "formation_key",
    )
    for name in netdetect_only:
        assert hasattr(NetdetectFinding, name), f"NetdetectFinding lost {name}"
        assert not hasattr(CrossFinding, name), (
            f"{name} leaked onto CrossFinding, which runs no membership test"
        )


def test_every_netdetect_route_is_reachable():
    """The shadowing bug again, as a property rather than one case. A single-segment `{slug}` will
    match any sibling declared after it, and the failure is a plausible-looking 404 rather than a
    routing error, so it is worth asserting the whole surface answers."""
    from app.main import create_app

    # The OpenAPI document, not `app.routes`: this FastAPI version wraps included routers in
    # objects that expose neither a path nor their children, and the spec is what a client sees.
    paths = set(create_app().openapi()["paths"])
    for expected in (
        "/v1/admin/netdetect/{slug}",
        "/v1/admin/netdetect/findings/all",
        "/v1/admin/netdetect/findings/calibration",
        "/v1/admin/netdetect/formations",
        "/v1/admin/netdetect/formations/assign",
    ):
        assert expected in paths, f"{expected} is not registered"

    # THE PROPERTY THAT ACTUALLY MATTERS: a one-segment sibling is shadowed by `{slug}` only when
    # they share a METHOD. `GET /formations` is safe today because `{slug}` is POST-only, and that
    # is exactly the fragile arrangement CLAUDE.md records for `/v1/investigations/claim`. Asserting
    # it here means adding `GET /{slug}` later fails loudly instead of silently breaking a sibling.
    spec = create_app().openapi()["paths"]
    slug_methods = {m.lower() for m in spec["/v1/admin/netdetect/{slug}"]}
    for path, operations in spec.items():
        if not path.startswith("/v1/admin/netdetect/") or "{slug}" in path:
            continue
        tail = path[len("/v1/admin/netdetect/"):]
        if "/" in tail:
            continue  # two segments deep: structurally unshadowable
        clash = {m.lower() for m in operations} & slug_methods
        assert not clash, (
            f"{path} is one segment deep and shares {sorted(clash)} with /{{slug}}, which is "
            f"declared first and will swallow it. Nest it a segment deeper."
        )


# ==================================================================================================
# The sweep: a whole comment section against the whole catalogue
# ==================================================================================================
def test_a_sweep_places_a_rotated_operation_and_leaves_the_bystanders_alone():
    """THE CAPABILITY THE SINGLE-ACCOUNT ROUTE COULD NOT OFFER.

    `score_against` answers "does THIS account belong to THAT operation", which needs an operator to
    already suspect both. When a comment section lands nobody suspects anything, so the useful
    direction is the other way round.

    Measured here: the catalogue holds two unrelated operations, a NEW comment section arrives
    carrying the stadium operator on accounts that share no id with anything catalogued, and the
    sweep places 8 of 8 in the right formation, 0 of 60 ordinary accounts anywhere, and none in the
    wrong operation.
    """
    from app.netdetect.assign import sweep

    stadium, _ = learn("stadium", bg=5, op=6)
    clinic, _ = learn("clinic", bg=17, op=23)
    assert stadium is not None and clinic is not None, "fixture changed"
    profiles = {"STADIUM": stadium, "CLINIC": clinic}

    rows = C.organic_population(60, seed=31) + C.planted_operation(
        8, seed=6, discipline=0.0, operator="stadium", prefix="new")
    accounts = [profile_from_commenter(r) for r in rows if r.get("external_id")]

    result = sweep(accounts, profiles)
    placed = {p.external_id: p.assignment.formation_key for p in result.placed}

    operation = {r["external_id"] for r in rows if r["external_id"].startswith("new")}
    ordinary = {r["external_id"] for r in rows if r["external_id"].startswith("org")}

    assert operation <= set(placed), (
        f"only {len(operation & set(placed))} of {len(operation)} rotated members were placed"
    )
    assert not (ordinary & set(placed)), (
        f"ordinary accounts were placed in an operation: {sorted(ordinary & set(placed))}"
    )
    assert all(key == "STADIUM" for eid, key in placed.items() if eid in operation), (
        "a member was placed in the unrelated catalogued operation"
    )
    assert result.unplaced == len(ordinary)
    assert not result.truncated


def test_an_unplaced_account_is_a_count_and_never_a_clean_bill_of_health():
    """`unplaced` is a NUMBER, not a list of names, and the response says why.

    Publishing "these 140 accounts matched no known operation" invites reading it as innocence. An
    account placed in nothing is one this deployment has never catalogued doing this before, and an
    operation nobody has recorded is exactly what `detect` exists to find.
    """
    from app.netdetect.assign import NOT_A_CLEARANCE, Sweep, sweep

    stadium, _ = learn("stadium", bg=5, op=6)
    rows = C.organic_population(40, seed=13)
    accounts = [profile_from_commenter(r) for r in rows]

    result = sweep(accounts, {"STADIUM": stadium})
    assert result.placed == []
    assert result.unplaced == len(accounts)
    assert isinstance(result.unplaced, int)
    assert not hasattr(result, "unplaced_ids")

    assert "not a finding of innocence" in NOT_A_CLEARANCE
    assert "never as" in NOT_A_CLEARANCE

    # An empty catalogue is a THIRD state: nobody looked, which is not "no match".
    empty = sweep(accounts, {})
    assert not empty.looked and empty.skipped == len(accounts)
    assert empty.unplaced == 0, "no catalogue was read as every account matching nothing"
    assert isinstance(Sweep(), Sweep)


def test_the_sweep_reports_its_own_truncation():
    """A capped sweep that answered silently would be a claim about the accounts it never weighed."""
    from app.netdetect.assign import MAX_SWEEP_ACCOUNTS, sweep

    stadium, _ = learn("stadium", bg=5, op=6)
    rows = C.organic_population(60, seed=13)
    accounts = [profile_from_commenter(r) for r in rows] * 10
    assert len(accounts) > MAX_SWEEP_ACCOUNTS

    result = sweep(accounts, {"STADIUM": stadium})
    assert result.truncated
    assert result.placed == [] and result.unplaced == MAX_SWEEP_ACCOUNTS


def test_the_sweep_route_is_reachable_and_not_shadowed():
    """`POST /{slug}` is declared first and would match a single-segment `/sweep` with
    slug="sweep", answering 404 "No such investigation": a routing fault that reads as a data one.
    Two segments cannot be shadowed by a one-segment parameter."""
    from app.main import create_app

    paths = create_app().openapi()["paths"]
    assert "/v1/admin/netdetect/formations/sweep" in paths
    assert "post" in paths["/v1/admin/netdetect/formations/sweep"]


def test_both_assignment_routes_serialise_through_one_function():
    """A second copy is how one of them quietly stops carrying `refused` or `hard_evidence`, and
    both make the same claim about a named person. This repo already paid for a hardcoded field
    list once, in `coerce_comprehensive_model_output`."""
    import inspect

    from app.routes import netdetect as routes

    source = inspect.getsource(routes)
    assert source.count("def _assignment_out(") == 1
    assert source.count("AssignmentOut(\n") == 1, (
        "AssignmentOut is constructed in more than one place; use _assignment_out"
    )


def test_the_score_characterises_a_placement_and_never_decides_it():
    """THE INVERTED READING, AND THE RULE THAT KEEPS IT SAFE.

    `Placement.concealed` marks an account placed in a known operation that would nonetheless pass
    an individual review. That is the most valuable row in a sweep: an account the per-account
    engine already flags is one an analyst could have found without this.

    It is CHARACTERISATION. `score_against` reads behaviour only, which is what kept the old 70+
    cohort filter's blind spot from being rebuilt here. Measured: the same accounts scored 30, 85
    and unscored produce the IDENTICAL placement, and only the label changes.
    """
    from app.netdetect.assign import sweep

    stadium, _ = learn("stadium", bg=5, op=6)
    rows = C.organic_population(60, seed=31) + C.planted_operation(
        8, seed=6, discipline=0.0, operator="stadium", prefix="new")

    def placed_with(score):
        for r in rows:
            if r["external_id"].startswith("new"):
                r["omi_score"] = score
                r["overall_probability"] = score
        result = sweep([profile_from_commenter(r) for r in rows], {"STADIUM": stadium})
        return result, {p.external_id for p in result.placed}

    low, low_ids = placed_with(30.0)
    high, high_ids = placed_with(85.0)
    none, none_ids = placed_with(None)

    assert low_ids == high_ids == none_ids, (
        "the OMI score changed WHICH accounts were placed; placement must read behaviour only"
    )
    assert low_ids, "the operation was not placed at all; fixture changed"

    assert all(p.concealed for p in low.placed if p.external_id.startswith("new")), (
        "members that would pass an individual review were not marked concealed"
    )
    assert not any(p.concealed for p in high.placed), (
        "an account the engine already flags was marked concealed, which inverts the reading"
    )
    assert not any(p.concealed for p in none.placed), (
        "an UNSCORED account was marked concealed. None is not low: it means nobody examined it, "
        "and reading it as concealed manufactures the most alarming label out of missing data"
    )


# ==================================================================================================
# Ageing the catalogue
# ==================================================================================================
def test_the_monitoring_pass_ages_the_formation_catalogue():
    """DORMANCY IS THE ABSENCE OF AN EVENT, which nothing else in this package has to deal with.

    Every other state change here is driven by something happening: a finding is recorded, an
    operator judges it, an account is placed. A formation that simply STOPPED posting emits nothing
    to notice, so without a sweep it stays `active` forever and the catalogue slowly fills with
    operations that ended months ago, all presenting as live.

    `registry.refresh_phases` was written for exactly this and had nothing calling it.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.monitoring.scheduler import _refresh_formation_phases
    from app.netdetect.formation import DORMANT_AFTER_DAYS
    from app.storage.db import get_session
    from app.storage.models import NetdetectFormation

    now = datetime.now(timezone.utc)
    with get_session() as session:
        for key, last_seen in (
            ("stale_op", now - timedelta(days=DORMANT_AFTER_DAYS + 30)),
            ("live_op", now - timedelta(days=1)),
        ):
            session.add(NetdetectFormation(
                formation_key=key, platform="x", phase="active",
                profile_json={}, families_json=[], members_json=["a", "b"], member_count=2,
                contexts_json=["p"], sighting_count=1,
                first_seen=now - timedelta(days=200), last_seen=last_seen,
            ))
        session.commit()

    assert _refresh_formation_phases() == 1

    with get_session() as session:
        phases = {
            f.formation_key: f.phase
            for f in session.execute(select(NetdetectFormation)).scalars()
        }
    assert phases["stale_op"] == "dormant", "a formation that stopped posting still reads as live"
    assert phases["live_op"] == "active", "an active formation was aged out"


def test_ageing_the_catalogue_never_fails_the_monitoring_pass():
    """A phase is a label on a lead an operator reads. Failing the pass over one would take the
    anomaly detection and the watchlist rescans down with it, and those are what customers
    actually depend on."""
    from app.monitoring import scheduler

    class Exploding:
        def __enter__(self):
            raise RuntimeError("the database went away")

        def __exit__(self, *a):
            return False

    original = scheduler.get_session
    scheduler.get_session = lambda: Exploding()
    try:
        assert scheduler._refresh_formation_phases() == 0
    finally:
        scheduler.get_session = original


# ==================================================================================================
# Across platforms, only evidence that means the same thing on both may count
# ==================================================================================================
def _profile_on(platform: str):
    from app.netdetect.formation import FormationProfile

    base, _ = learn("stadium", bg=5, op=6)
    assert base is not None, "fixture changed"
    return FormationProfile(features=base.features, families=base.families,
                            corpus_size=base.corpus_size, platform=platform)


def _account_on(platform: str):
    rows = C.planted_operation(8, seed=6, discipline=0.0, prefix="yt")
    for r in rows:
        r["platform"] = platform
    return profile_from_commenter(rows[0])


def test_a_cross_platform_placement_may_not_rest_on_identity_or_infrastructure():
    """THE RULE `campaigns/tracking/crossplatform.py` ARGUES, WHICH ASSIGNMENT NEVER APPLIED.

    An X account id and a YouTube channel id never match, so a cross-platform claim can only rest on
    what the accounts DID. A client string is read from an X-only field, and handle conventions
    differ per platform, so a shared skeleton across two services is evidence about the services'
    naming rules rather than about the accounts.

    It matters because `identity` is weighted 1.00 and is HARD, so a coincidental cross-platform
    collision there could clear `MIN_HARD_EVIDENCE` alone. Measured before the restriction: the same
    operator's accounts relabelled as another platform placed at posterior 0.990 carrying
    `identity: 9.0` and `infrastructure: 6.0`.
    """
    same = score_against(_account_on("x"), _profile_on("x"), formation_key="XOP")
    cross = score_against(_account_on("youtube"), _profile_on("x"), formation_key="XOP")

    assert same.by_family.get("identity", 0) > 0
    assert same.by_family.get("infrastructure", 0) > 0
    assert not cross.by_family.get("identity"), "identity survived a platform change"
    assert not cross.by_family.get("infrastructure"), "infrastructure survived a platform change"
    assert cross.hard_evidence < same.hard_evidence

    # STILL PLACED, on evidence that travels. The restriction removes families, not the finding:
    # refusing every cross-platform placement would be a different and wrong rule.
    assert cross.assigned, "a genuine cross-platform operation stopped being recognisable at all"


def test_a_mention_does_not_travel_but_a_hashtag_does():
    """`narrative` is the one family that is HALF neutral, and it only became so recently.

    It was wholly neutral when it meant topic ids, which come from the cross-investigation embedding
    space rather than from any platform. Then mentions and hashtags started filling it. A hashtag is
    the same campaign tag on any service; a mention is a handle inside a per-platform namespace, so
    `@someone` on two services is two unrelated accounts and a match between them is a collision.

    Excluded by KIND, because dropping the family would throw away hashtags and topics to remove
    mentions.
    """
    from app.netdetect.types import is_platform_neutral

    assert is_platform_neutral("narrative", "hashtag")
    assert is_platform_neutral("narrative", "topic")
    assert not is_platform_neutral("narrative", "mentions")
    assert not is_platform_neutral("identity", "signup_week")
    assert is_platform_neutral("text", "shingle")

    cross = score_against(_account_on("youtube"), _profile_on("x"), formation_key="XOP")
    same = score_against(_account_on("x"), _profile_on("x"), formation_key="XOP")
    assert 0 < cross.by_family.get("narrative", 0) < same.by_family["narrative"], (
        "narrative either survived whole (mentions travelled) or was dropped whole (hashtags lost)"
    )
    assert not any(m.kind == "mentions" for m in cross.matched)


def test_an_unknown_platform_does_not_restrict_anything():
    """Profiles stored before the platform was carried have none, and reading absence as a mismatch
    would silently stop assigning against every one of them."""
    legacy = score_against(_account_on("youtube"), _profile_on(""), formation_key="LEGACY")
    same = score_against(_account_on("x"), _profile_on("x"), formation_key="XOP")
    assert legacy.by_family.get("identity", 0) == same.by_family.get("identity", 0)
    assert legacy.hard_evidence == same.hard_evidence


def test_the_neutral_family_rule_agrees_with_the_tracking_layer():
    """Two copies in two packages, restated rather than imported because the tracking module is
    built from the OTHER detector's family constants and predates `FAMILY_NARRATIVE`. They must not
    drift on the families they share."""
    from app.campaigns.tracking.crossplatform import (
        PLATFORM_NEUTRAL_FAMILIES as TRACKING,
    )
    from app.netdetect.types import PLATFORM_NEUTRAL_FAMILIES as NETDETECT

    shared = {"text", "network", "timing"}
    assert shared <= TRACKING and shared <= NETDETECT
    assert not (TRACKING - NETDETECT), (
        "the tracking layer calls a family neutral that netdetect does not"
    )


def test_one_coincidence_is_not_enough_to_place_somebody_in_an_operation():
    """`MIN_HARD_EVIDENCE` weighs the SUM, and one feature can carry it alone.

    `creation_week` is a single identity feature, and a rare week scores about 5.8 by itself, which
    clears the 3.0 floor unaided. All the account then needs is any second family to satisfy
    `MIN_FAMILIES`, and a shared quiet-hours bucket will do. A person should not be named as part of
    an operation because they signed up the same week it did.

    Measured on the fan-community control: the one false assignment rested on exactly ONE hard
    feature at 5.78, while every genuine member rested on FIVE at 19.27. The populations do not
    overlap, which is what makes the floor free.
    """
    from app.netdetect.assign import MIN_HARD_FEATURES, score_against
    from app.netdetect.types import HARD_FAMILIES

    stadium, _ = learn("stadium", bg=5, op=6)
    assert stadium is not None, "fixture changed"

    def hard_features(assignment):
        return len({(m.kind, m.value) for m in assignment.matched
                    if m.family in HARD_FAMILIES})

    members = [score_against(profile_from_commenter(r), stadium, formation_key="OP")
               for r in C.planted_operation(8, seed=6, discipline=0.0)]
    assert all(a.assigned for a in members), "the floor cost a genuine member its assignment"
    assert all(hard_features(a) >= MIN_HARD_FEATURES for a in members)

    # Nobody in an innocent population is placed, and any that come close do so on one coincidence.
    for row in C.fan_community(12, seed=33):
        out = score_against(profile_from_commenter(row), stadium, formation_key="OP")
        assert not out.assigned, f"{row['external_id']} was placed in an operation"


def test_an_arrival_bucket_is_never_part_of_a_formations_identity():
    """A formation profile has to survive account rotation, which it can only do by holding what the
    operator KEEPS DOING. An arrival bucket is a wall-clock moment under one specific post.

    Two accounts under that post can meaningfully share it; an account seen six weeks later cannot,
    and any match it produces is a coincidence of the calendar. Measured before the exclusion: a
    member of the fan-community control was assigned to a catalogued operation.
    """
    from app.netdetect.formation import CONTEXTUAL_KINDS

    stadium, _ = learn("stadium", bg=5, op=6)
    assert stadium is not None
    assert "arrival" in CONTEXTUAL_KINDS
    assert not [f for f in stadium.features if f.kind in CONTEXTUAL_KINDS], (
        "a timestamp bucket became part of an operation's durable identity"
    )


def test_a_contaminated_finding_pollutes_the_profile_and_still_places_nobody():
    """THE THIRD DOWNSTREAM PATH, and the one that matters most because assignment names an
    INDIVIDUAL rather than describing a set.

    A published amplifier-ring finding names 52.9% innocent accounts, and that finding is what a
    formation profile is distilled from. `build_profile` reads the candidate's EVIDENCE rather than
    the members' feature bags, so a feature reaches the profile only when two or more members share
    it. Bystanders are members, so two of them sharing something puts it into the operation's
    permanent identity, and every later sweep is measured against that identity.

    MEASURED, AND IT IS THE SAME SHAPE AS THE GRAPH LEAK. Across the pinned ring grid the profile is
    40% bystander-only (48 features of 120), so the pollution is real and substantial. NONE of it is
    a hard family, and no ordinary account in the section places against the polluted profile
    (0 of 31, 0 of 45, 0 of 63).

    That holds for the reason the whole package rests on rather than by luck: a hard family is the
    operator's own act, which a swept-in bystander does not perform, and `MIN_HARD_EVIDENCE` plus
    `MIN_HARD_FEATURES` mean soft features alone can never place anybody. So contamination reaches
    the profile and stops at the point where it would name someone.

    WHAT IT DOES COST is discriminative power rather than safety: 40% of the profile is noise that
    a genuine future member does not match, which can only make assignment harder. That is a recall
    risk, and it is the argument for trimming stated from a third direction.
    """
    from app.netdetect.types import HARD_FAMILIES

    ring = C.amplifier_ring(8, seed=63)
    ring_ids = {r["external_id"] for r in ring}
    rows = C.organic_population(40, seed=31) + ring
    result = detect_from_commenters(rows, shuffles=SHUFFLES)

    checked = 0
    for finding in result.findings:
        members = set(finding.members)
        if len(members & ring_ids) < 4 or not (members - ring_ids):
            continue
        profile = build_profile(finding, result.corpus)
        assert profile.features, "the finding produced no profile at all"

        bystander_only = []
        for pf in profile.features:
            holders: set[str] = set()
            for feature, hs in result.corpus.feature_accounts.items():
                if (feature.family, feature.kind, feature.value) == (pf.family, pf.kind, pf.value):
                    holders = set(hs) & members
                    break
            if holders and not (holders & ring_ids):
                bystander_only.append(pf)

        checked += 1
        # The premise: if this stops being true the measurement below is about a different thing.
        assert bystander_only, (
            "no bystander-only feature reached the profile, so this test is no longer exercising "
            "the pollution path it was written for"
        )
        assert not [pf for pf in bystander_only if pf.family in HARD_FAMILIES], (
            "a HARD family feature held only by bystanders entered the operation's durable "
            "identity; soft pollution is contained by MIN_HARD_EVIDENCE and this would not be"
        )

        # THE HARM TEST. Ordinary accounts from this very section are the population nearest the
        # finding and so the likeliest to match a polluted profile.
        for account in result.corpus.accounts:
            if account.external_id in members:
                continue
            outcome = score_against(account, profile, formation_key="ring")
            assert not outcome.assigned, (
                f"{account.external_id} was placed in the operation on a profile built from a "
                f"finding that was mostly bystanders"
            )

    assert checked, "no contaminated ring finding was produced; the test asserted nothing"


def test_a_bystander_can_hold_hard_evidence_and_one_coincidence_still_places_nobody():
    """CORRECTS A CLAIM I MADE THREE TIMES: that a bystander never holds hard-family evidence
    because a hard family is the operator's own act. That is overstated, and it is falsifiable.

    `creation_week` is the one hard feature that is a PROPERTY rather than an act. An innocent
    account can be provisioned in the same week as an operative by coincidence, and nothing forbids
    it. `repost_of` is different: converging on an outside target IS an act, and it never
    contaminated in any configuration measured.

    Measured over a grid wider than the pinned one (14 findings, 43 hard-family evidence features):
    ONE had a bystander holder, an identity/creation_week feature at ring 60/62. On the pinned
    corpus family that is 1 hard pair out of 937 touching a bystander, i.e. 0.1% against 56.5% of
    the accumulated weight being soft. So containment is real and large, and it is not zero.

    THE CONCLUSION SURVIVES FOR A BETTER REASON THAN THE ONE I GAVE, and the reason was already in
    the code. `MIN_HARD_FEATURES` requires TWO DISTINCT hard features before an account is placed,
    and its own note says why: a rare `creation_week` scores about 5.8 alone, clearing
    `MIN_HARD_EVIDENCE` unaided, and the package added the floor after measuring exactly one false
    assignment that rested on one such coincidence. So the safety does not depend on bystanders
    being unable to hold hard evidence. It depends on one coincidence never being enough.

    This test therefore pins the GUARD rather than the absence, because the absence is not true.
    """
    from app.netdetect.assign import MIN_HARD_FEATURES

    assert MIN_HARD_FEATURES >= 2, (
        "assignment would place an account on a single hard feature, and `creation_week` is a "
        "calendar coincidence an innocent account can share; the measured false assignment this "
        "floor was added for rested on exactly one such feature"
    )

    ring = C.amplifier_ring(8, seed=62)
    ring_ids = {r["external_id"] for r in ring}
    rows = C.organic_population(60, seed=31) + ring
    result = detect_from_commenters(rows, shuffles=SHUFFLES)

    seen_contaminated_hard = False
    for finding in result.findings:
        members = set(finding.members)
        if len(members & ring_ids) < 4:
            continue
        bystanders = members - ring_ids
        for item in finding.evidence or []:
            if item.feature.family not in HARD_FAMILIES_FOR_TEST:
                continue
            holders = set(result.corpus.feature_accounts.get(item.feature, ())) & members
            if holders & bystanders:
                seen_contaminated_hard = True
                # The mechanism, named. If a NETWORK family ever turns up here the reasoning above
                # is wrong in a way that matters much more: convergence on an outside target is an
                # act, and a bystander performing it would not be a coincidence.
                assert item.feature.family == "identity", (
                    f"a {item.feature.family} feature reached a bystander. Only identity is "
                    f"coincidental (a shared provisioning week); network is an act."
                )

        # Whatever the evidence looks like, no ordinary account may be placed on this profile.
        profile = build_profile(finding, result.corpus)
        for account in result.corpus.accounts:
            if account.external_id in members:
                continue
            assert not score_against(account, profile, formation_key="r").assigned

    assert seen_contaminated_hard, (
        "no bystander held hard evidence on the corpus this was measured on, so the correction "
        "this test records has stopped being demonstrated; re-measure before restoring any claim "
        "that it cannot happen"
    )


def test_the_monitoring_pass_itself_ages_the_catalogue_not_just_its_helper():
    """THE WIRING, WHICH THE TEST ABOVE DOES NOT COVER.

    `test_the_monitoring_pass_ages_the_formation_catalogue` calls `_refresh_formation_phases`
    directly. That proves the helper works and says nothing about whether anything calls it: delete
    the line from `run_one_pass` and that test still passes, while the catalogue silently stops
    ageing and every dormant operation goes on presenting as live.

    This is the gap this repo keeps paying for one level up. `registry.refresh_phases` was itself
    written and left with nothing calling it, which is why the helper exists at all; the fix added a
    caller and a test for the helper, and left the caller unguarded.

    So this drives the real entry point and asserts the catalogue actually moved.
    """
    from datetime import datetime, timedelta, timezone

    from app.monitoring.scheduler import run_one_pass
    from app.netdetect.formation import DORMANT_AFTER_DAYS
    from app.storage.db import get_session
    from app.storage.models import NetdetectFormation

    now = datetime.now(timezone.utc)
    with get_session() as session:
        session.add(NetdetectFormation(
            formation_key="wiring_stale", platform="x", phase="active",
            profile_json={}, families_json=[], members_json=["a", "b"], member_count=2,
            contexts_json=["p"], sighting_count=1,
            first_seen=now - timedelta(days=200),
            last_seen=now - timedelta(days=DORMANT_AFTER_DAYS + 30),
        ))
        session.commit()

    out = run_one_pass()

    assert out.get("formation_phases") == 1, (
        "the monitoring pass did not report ageing any formation. If the call was removed from "
        "run_one_pass the catalogue stops ageing silently and every dormant operation keeps "
        "presenting as live."
    )
    with get_session() as session:
        row = session.query(NetdetectFormation).filter_by(formation_key="wiring_stale").one()
        assert row.phase != "active", (
            "run_one_pass reported a phase change that did not reach the row"
        )
