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
    assert "operator's own acts" in (other.refused or "")


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
