"""Admin surface for the coordinated-network detector: /v1/admin/netdetect/*.

Admin-only, and for the same reason `/campaigns` and `/narratives` are: this reports groups of
NAMED REAL PEOPLE as running together, on evidence that is statistical rather than certain. It is an
operator's lead, not a customer-facing verdict, and it stays that way until the dilution curve and
the adjudication layer say otherwise.

Findings are now RECORDED, and the distinction that makes that acceptable is worth stating: this
persists an internal finding, it does not publish one. No share token is minted, no `Campaign` row
is created, and nothing reaches a customer surface. The original rule, that a claim this system
makes about a person is a decision somebody took rather than a side effect of a page load, is about
PUBLICATION and is untouched.

Recording is what the detector was missing twice over. Its findings evaporated when the page
closed, so the tracking layer that survives account rotation learned only from the older cohort
detector; and there was nothing to dismiss, so the one reservoir of ground truth this system will
ever accumulate stayed empty while the better detector ran.
"""

from __future__ import annotations

import logging

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.core.auth import CurrentUser, require_user
from app.netdetect import corroboration as corrob
from app.netdetect import detect_from_commenters
from app.netdetect.persist import persist_finding, persist_section
from app.netdetect.shuffle import DEFAULT_SHUFFLES
from app.storage.db import get_session
from app.storage.models import Investigation, NetdetectFinding, NetdetectFormation

log = logging.getLogger("omi.netdetect.routes")

admin_router = APIRouter(prefix="/v1/admin/netdetect", tags=["admin-netdetect"])


def _require_admin(current: CurrentUser) -> None:
    if not current.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only.")


class EvidenceOut(BaseModel):
    family: str
    kind: str
    shared_by: int
    corpus_count: int
    surprise: float
    sentence: str
    #: WHICH members hold this feature, not just how many.
    #:
    #: A finding is a members-by-features incidence structure, and `members` plus `shared_by` are
    #: two disconnected projections of it: they cannot say whether the evidence is about the SAME
    #: people throughout or about two sub-groups joined at a seam. This carries the join, so a
    #: reviewer can read the shape instead of taking it on trust.
    #:
    #: None means the holders were not recorded (a row written before this field existed), which is
    #: NOT the same as "no member holds it" and must never render as an empty grid. Same three-state
    #: discipline as `attachment_checked`.
    members: list[str] | None = None


#: What a reader has to be told about the member list, on the response rather than in a docstring.
#:
#: Candidate generation is community detection, which pulls in boundary accounts. Measured over a
#: systematic grid of planted operations in organic backgrounds: recall 8/8 everywhere, and about
#: 7% of all NAMED members were innocent bystanders, with one finding running to 3 of 11.
#:
#: `weakly_attached` now names them, from `app/netdetect/attachment.py`, and it is a REPORT rather
#: than an exclusion: a flagged account is still a member and still listed. It is also NOT a
#: confidence score. The obvious per-member number (how much shared evidence a member participates
#: in) was measured and ranks some bystanders ABOVE genuine members, which is why this asks the
#: different question of what each member ADDED, and why it abstains rather than guessing when the
#: evidence is spread evenly.
MEMBERSHIP_NOTE = (
    "Membership is a set-level claim. Candidate generation is community detection, so a finding "
    "can include an account that borders the group without belonging to it: measured at roughly 7% "
    "of named members, and up to 3 of 11 in one case. `weakly_attached` names the members that do "
    "not carry the finding, and it is a pointer for review rather than a verdict: they remain "
    "members and are still listed. When `attachment_note` is set no membership verdict was "
    "reached, which is not the same as every member belonging. Check each name against the "
    "evidence before acting on it."
)


class FindingOut(BaseModel):
    members: list[str]
    handles: list[str]
    size: int
    score: float
    by_family: dict[str, float]
    hard_evidence: float
    corrected_p: float | None
    #: Non-null when the evidence cannot settle whether this is an operation or a community, and a
    #: person has to look. The reason is in the string.
    needs_adjudication: str | None
    #: Members that do not carry this finding. A pointer for review, never an exclusion, and never
    #: a confidence score. See MEMBERSHIP_NOTE.
    weakly_attached: list[str] = []
    #: Why no membership verdict was reached, or null when one was. An empty `weakly_attached` with
    #: this set does NOT mean every member belongs.
    attachment_note: str | None = None
    #: Whether the membership test ran. An empty `weakly_attached` means "every member carries this
    #: finding" only when this is true; when it is false the question was not answered.
    attachment_checked: bool = False
    #: What was already known about these people from OTHER posts. A PRIOR reported beside the
    #: corrected result, never folded into `score`. Null when the lookup did not run.
    corroboration: CorroborationOut | None = None
    evidence: list[EvidenceOut]


class CorroborationOut(BaseModel):
    """What the accumulating graph already held about this set, from OTHER posts."""

    #: Total accumulated log10 evidence. CONTEXT ONLY, and this comment is load-bearing: measured,
    #: a planted operation and the professional-beat control BOTH saturate the cap, so this number
    #: does not separate them and nothing may key a decision on it.
    log_lr: float
    pairs_with_history: int
    #: Pairs whose prior evidence includes a HARD family (identity, network): the operator's own
    #: acts. THIS is the half that discriminates: measured 28 of 28 on a planted operation and
    #: 0 of 45 on the newsroom control.
    hard_pairs: int
    #: Distinct EARLIER posts. The post being scanned is excluded, so a set cannot corroborate
    #: itself and a re-run cannot strengthen it.
    contexts: list[str]
    families: list[str]
    hard_families: list[str]
    #: Whether the lookup ran. A zero with this false means nobody looked, not that these accounts
    #: were strangers. Same distinction as `attachment_checked`.
    checked: bool
    sentence: str


def _corroboration_out(c) -> "CorroborationOut | None":
    cor = getattr(c, "corroboration", None)
    if cor is None:
        return None
    return CorroborationOut(
        log_lr=round(cor.log_lr, 3),
        pairs_with_history=cor.pairs_with_history,
        hard_pairs=cor.hard_pairs,
        contexts=list(cor.contexts),
        families=list(cor.families),
        hard_families=list(cor.hard_families),
        checked=cor.checked,
        sentence=cor.sentence(),
    )


class RunOut(BaseModel):
    slug: str
    corpus_size: int
    rare_features: int
    null_shuffles: int
    null_threshold: float | None
    findings: list[FindingOut]
    #: How many candidates scored but did not beat the shuffled search. "We looked and refused" is a
    #: more trustworthy statement than "we found nothing", and an operator calibrating needs the
    #: near-misses.
    rejected: int
    #: Set when the run could not be performed at all, as distinct from performing it and finding
    #: nothing. Never read an empty findings list as a clean result without checking this.
    refused: str | None
    #: Set when one group is large enough HERE to poison the null this section provides, so an
    #: empty findings list means "cannot tell" rather than "clean".
    #:
    #: An operation owning more than a quarter of a comment section pushes its own provisioning and
    #: targeting evidence past the rarity ceiling, where it is dropped as ordinary before any
    #: arithmetic runs. Measured: recall falls from 8/8 to 0 between 24% and 32% share, and the run
    #: reports nothing, which reads exactly like a clean scan. This is the third state.
    #:
    #: It never claims an operation is present, because the same statistic fires on a fan community
    #: filling a small section: a null built from a section one group dominates cannot resolve that
    #: group in either direction. See `app/netdetect/domination.py`.
    unresolvable: str | None = None
    #: What the member list does and does not claim. Served with the numbers rather than left in a
    #: docstring, for the same reason `/narratives` states what its detector cannot see.
    membership_note: str = MEMBERSHIP_NOTE
    #: Findings written to the store.
    recorded: int = 0
    #: Whether a "could not resolve this section" record is being held open for this investigation.
    #: False also means an earlier one was WITHDRAWN because the section became resolvable, which is
    #: why the run reports it rather than leaving the caller to infer it from `unresolvable`.
    section_recorded: bool = False
    #: THE FALLBACK, run only when this section could not resolve itself. A formation profile
    #: carries the surprise each feature had in the corpus it was LEARNED in, so the catalogue does
    #: not read this corpus's rarity at all and a group big enough to poison its own background
    #: here cannot poison a profile built where it was a minority.
    #:
    #: Measured, rotating one catalogued operator onto fresh accounts: through this section recall
    #: falls 8/8 to 0 between 24% and 32% share, while through the catalogue it stays 8/8 at 32%,
    #: 40% and 50%, with zero organic accounts placed. On the innocent controls that also trip the
    #: statistic (a fan community at 44% and 60%, a newsroom at 40%, an uncatalogued ring at 32%)
    #: it places nobody, so the fallback cannot turn a refusal into an accusation. See
    #: `app/netdetect/domination.py` for both tables.
    #:
    #: THREE STATES, and two of them show zero. False means the section resolved itself so there
    #: was nothing to fall back to; true with `catalogue_empty` means nothing has ever been
    #: catalogued to compare against; true without it means the catalogue was consulted.
    catalogue_checked: bool = False
    catalogue_empty: bool = False
    #: A COUNT, never names. The names have a home already: `POST /formations/sweep` renders them
    #: with the placement discipline built for exactly that, and a second serialiser on a second
    #: path is how one of them quietly stops carrying `refused` or `hard_evidence`. This number is
    #: the pointer to that panel, not a replacement for it.
    catalogue_placed: int = 0
    #: Of those, how many would have passed an individual review. The row to read first: an account
    #: the per-account engine already flags is one an analyst could have found without any of this.
    catalogue_concealed: int = 0
    #: Why an empty fallback is not an all-clear. Reused verbatim from the sweep route rather than
    #: reworded here, because the claim is identical and two wordings drift.
    catalogue_note: str | None = None
    #: NEW pairs in the accumulating graph. A pair already in it is strengthened rather than
    #: created, so this is "how many of these people had never been linked before" and deliberately
    #: not "how much evidence was folded in". Zero on a re-run of one post is the correct answer.
    accumulated_pairs: int = 0
    #: Candidates this corpus REFUSED whose members were already seen doing the operator's own acts
    #: under other posts. Not findings and never promoted to findings: history must not manufacture
    #: one. They are the near-miss pile worth a second look. See `corroboration.annotate`, which
    #: states honestly that this path has never been observed firing on the synthetic corpora.
    leads: int = 0
    #: False when history could not be read at all, so an all-zero corroboration is not mistaken for
    #: "none of these people have ever been seen together".
    history_checked: bool = False


@admin_router.post("/{slug}", response_model=RunOut)
def run_on_investigation(
    slug: str,
    shuffles: int = Query(DEFAULT_SHUFFLES, ge=1, le=200),
    record: bool = Query(True, description="Store the findings and accumulate their pairs."),
    current: CurrentUser = Depends(require_user),
) -> RunOut:
    """Run the detector over one stored investigation.

    Costs nothing: no provider call, no model call, no credit. It reads a payload that is already
    stored, which is what makes it safe to offer as a button.

    The scanned post's own ids are excluded from the evidence. Every commenter engaged that post by
    construction, so without the exclusion the whole comment section shares a perfect feature and
    reports as one enormous operation.
    """
    _require_admin(current)

    with get_session() as session:
        inv = session.execute(
            select(Investigation).where(Investigation.slug == slug)
        ).scalar_one_or_none()
        if inv is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such investigation.")
        payload = inv.payload_json or {}
        target = str(getattr(inv, "target_id", "") or "")
        investigation_id = inv.id

    rows = [c for c in (payload.get("commenters") or []) if isinstance(c, dict)]
    if not rows:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "That investigation stored no commenters, so there is nothing to compare.",
        )

    exclude = {target} if target else set()
    for key in ("content_id", "video_id", "post_id"):
        v = payload.get(key)
        if v:
            exclude.add(str(v))

    result = detect_from_commenters(rows, exclude_context=exclude, shuffles=shuffles)

    # What the deployment already knew about these people, from OTHER posts.
    #
    # READ BEFORE THIS RUN'S OWN PAIRS ARE WRITTEN, and reported BESIDE the corrected result rather
    # than folded into it. History is measured outside this corpus and was never subjected to the
    # shuffled search correction that makes the families' sum honest, so adding it to a score would
    # slip evidence past the very thing that makes the score defensible. It is also measured NOT to
    # separate an operation from a newsroom on its own; see `app/netdetect/corroboration.py`.
    history_checked = False
    leads = 0
    try:
        with get_session() as session:
            corrob.annotate(
                session, [*result.findings, *result.rejected],
                exclude_context=target or None,
            )
        history_checked = True
        leads = sum(
            1 for c in result.rejected
            if c.corroboration is not None and c.corroboration.hard_history
        )
    except Exception:  # noqa: BLE001 - context on a finding, never a reason to fail the run
        log.warning("netdetect: could not read history for %s", slug, exc_info=True)

    handles = {str(r.get("external_id")): str(r.get("handle") or "") for r in rows}

    recorded = 0
    accumulated = 0
    if record and result.findings and result.corpus is not None:
        # Best-effort. A failure here loses accumulated history, which degrades FUTURE findings, and
        # must never turn a completed run into an error for the operator looking at it now.
        try:
            with get_session() as session:
                before = _edge_count(session)
                for candidate in result.findings:
                    persist_finding(
                        session, candidate, result.corpus,
                        investigation_id=investigation_id,
                        context_id=target or None,
                        platform=candidate.platform,
                        corpus_size=result.corpus_size,
                        null_shuffles=result.null_shuffles,
                        null_threshold=result.null_threshold,
                        # The OMI scores of the members, for `Composition`. Read AFTER detection and
                        # never fed back into it: see app/netdetect/formation.py.
                        member_scores=[
                            result.corpus.by_id[m].score
                            for m in candidate.members if m in result.corpus.by_id
                        ],
                    )
                    recorded += 1
                session.commit()
                accumulated = max(0, _edge_count(session) - before)
        except Exception:  # noqa: BLE001
            log.warning("netdetect: could not record findings for %s", slug, exc_info=True)
            recorded = 0

    # THE FALLBACK. Only on a section that could not resolve itself, because that is the one state
    # where this system otherwise has nothing further to offer: the detector reports nothing and the
    # nothing is indistinguishable from a clean scan. The catalogue is blind to a different thing
    # (it reads the surprise a feature carried where it was LEARNED, not here), so it is worth
    # consulting exactly where the primary path fails and nowhere else.
    unresolvable = (
        result.domination.sentence()
        if result.domination is not None and result.domination.unresolvable
        else None
    )
    fallback = (
        _catalogue_fallback(rows, exclude_context=target or "")
        if unresolvable else _CatalogueFallback()
    )

    # THE SECTION VERDICT IS RECORDED SEPARATELY, AND THAT IS THE WHOLE POINT.
    #
    # The block above is gated on `result.findings`, which is exactly the case a dominated section
    # fails: it produces no findings at all. Folding this in there would mean the one state that
    # cannot speak for itself is the one state never written down.
    #
    # It also runs when the section IS resolvable, because `persist_section` withdraws a warning
    # that no longer holds. A stale "cannot resolve" sitting in the queue after enough ordinary
    # accounts have commented is a claim about a section that has stopped being true.
    section_open = False
    if record:
        try:
            with get_session() as session:
                row = persist_section(
                    session, result.domination,
                    investigation_id=investigation_id,
                    context_id=target or None,
                    platform=(result.findings[0].platform if result.findings else "unknown"),
                    corpus_size=result.corpus_size,
                    catalogue=fallback,
                )
                section_open = row is not None
                session.commit()
        except Exception:  # noqa: BLE001 - same rule as accumulation: never fail a completed run
            log.warning("netdetect: could not record the section verdict for %s", slug,
                        exc_info=True)

    return RunOut(
        slug=slug,
        corpus_size=result.corpus_size,
        rare_features=result.rare_features,
        null_shuffles=result.null_shuffles,
        null_threshold=result.null_threshold,
        rejected=len(result.rejected),
        refused=result.refused,
        unresolvable=unresolvable,
        catalogue_checked=fallback.checked,
        catalogue_empty=fallback.empty,
        catalogue_placed=fallback.placed,
        catalogue_concealed=fallback.concealed,
        # Carried only when the fallback actually looked. Attaching it to a run that never
        # consulted the catalogue would state a caveat about a question nobody asked.
        catalogue_note=fallback.note,
        recorded=recorded,
        section_recorded=section_open,
        accumulated_pairs=accumulated,
        leads=leads,
        history_checked=history_checked,
        findings=[
            FindingOut(
                members=c.members,
                handles=[handles.get(m, m) for m in c.members],
                size=c.size,
                score=round(c.score, 3),
                by_family={k: round(v, 3) for k, v in sorted(c.by_family.items())},
                hard_evidence=round(c.hard_evidence, 3),
                corrected_p=c.corrected_p,
                needs_adjudication=c.needs_adjudication,
                weakly_attached=list(c.weakly_attached),
                attachment_note=c.attachment_note,
                attachment_checked=c.attachment_checked,
                corroboration=_corroboration_out(c),
                evidence=[
                    EvidenceOut(
                        family=e.feature.family, kind=e.feature.kind,
                        shared_by=e.shared_by, corpus_count=e.corpus_count,
                        surprise=round(e.surprise, 3), sentence=e.sentence,
                        members=_holders_of(result.corpus, e, c.members),
                    )
                    for e in c.evidence[:25]
                ],
            )
            for c in result.findings
        ],
    )


@dataclass(slots=True)
class _CatalogueFallback:
    """What the formation catalogue could say about a section that could not resolve itself.

    Counts only. The names have a home already at `POST /formations/sweep`, which serialises a
    placement through `_assignment_out` with every field a reader needs to argue with it. A second
    rendering on a second path is precisely how one of them quietly stops carrying `refused` or
    `hard_evidence`, and this repo has paid for a hardcoded per-item field list once already in
    `coerce_comprehensive_model_output`.
    """

    checked: bool = False
    empty: bool = False
    placed: int = 0
    concealed: int = 0

    @property
    def note(self) -> str | None:
        """Why an empty fallback is not an all-clear, or None when it never looked.

        Reused verbatim from the sweep route's constant rather than reworded: the claim is
        identical, and two wordings of one caveat drift until they disagree about what the product
        is willing to say.
        """
        from app.netdetect.assign import NOT_A_CLEARANCE
        return NOT_A_CLEARANCE if self.checked and not self.empty else None


def _catalogue_fallback(rows: list[dict], *, exclude_context: str) -> _CatalogueFallback:
    """Weigh an unresolvable section against formations catalogued in OTHER investigations.

    ONLY CALLED WHEN THIS SECTION COULD NOT RESOLVE ITSELF, and that restraint is deliberate rather
    than a cost saving: on a section the detector CAN price, its own findings are the better answer
    and a second number beside them would invite reading the two as agreeing or disagreeing when
    they measure different things.

    Never raises. It is a fallback on a path that has already refused to answer, so failing it would
    turn a completed run into an error for an operator who is looking at a real result.
    """
    from app.netdetect import registry
    from app.netdetect.assign import sweep
    from app.netdetect.features import profile_from_commenter

    out = _CatalogueFallback(checked=True)
    try:
        with get_session() as session:
            profiles = registry.load_profiles(session)
        if not profiles:
            out.empty = True
            return out
        accounts = [
            profile_from_commenter(r, exclude_context={exclude_context} if exclude_context else set())
            for r in rows if r.get("external_id")
        ]
        result = sweep(accounts, profiles)
        out.placed = len(result.placed)
        out.concealed = sum(1 for p in result.placed if p.concealed)
    except Exception:  # noqa: BLE001 - same rule as accumulation: never fail a completed run
        log.warning("netdetect: the catalogue fallback failed", exc_info=True)
        return _CatalogueFallback(checked=False)
    return out


def _holders_of(corpus, item, members: list[str]) -> list[str] | None:
    """Which of this finding's members hold one evidence feature.

    Returns None rather than an empty list when the corpus is not available to ask, because "we did
    not record who holds this" and "nobody holds this" are opposite statements about named people
    and the second one cannot be true of a feature that reached the evidence list at all.
    """
    if corpus is None:
        return None
    holders = corpus.feature_accounts.get(item.feature)
    if not holders:
        return None
    return sorted(set(holders) & set(members))


def _edge_count(session) -> int:
    from sqlalchemy import func

    from app.storage.models import CoordinationEdge

    return int(session.execute(select(func.count(CoordinationEdge.id))).scalar_one() or 0)


# ---------------------------------------------------------------------------------------------
# The queue, and the dismissals.
#
# THESE DISMISSALS ARE THE ONLY GROUND TRUTH THIS DETECTOR WILL EVER ACCUMULATE. Every constant in
# `app/netdetect` is reasoned rather than fitted, because no labelled corpus of coordinated accounts
# exists and none can be bought. An operator saying "this is a newsroom" or "this one is real" is
# the only signal a later calibration can be fitted against, which is why the reason is required and
# why a judged row is never deleted.
# ---------------------------------------------------------------------------------------------------


class StoredFindingOut(BaseModel):
    id: int
    investigation_id: int | None
    context_id: str | None
    platform: str
    members: list[str]
    member_count: int
    score: float
    corrected_p: float | None
    by_family: dict[str, float]
    needs_adjudication: str | None
    weakly_attached: list[str] = []
    attachment_note: str | None = None
    attachment_checked: bool = False
    #: What the graph already held about these members from OTHER posts, as of the last run. Null
    #: means the lookup did not run, never that they had not been seen together. Read `hard_pairs`
    #: inside it, not the total: the total does not separate an operation from a newsroom.
    corroboration: dict | None = None
    evidence: list[EvidenceOut]
    corpus_size: int
    null_shuffles: int
    null_threshold: float | None
    status: str
    dismissal_reason: str | None
    confirmed: bool


def _stored_out(row: NetdetectFinding) -> StoredFindingOut:
    return StoredFindingOut(
        id=row.id,
        investigation_id=row.investigation_id,
        context_id=row.context_id,
        platform=row.platform,
        members=list(row.members_json or []),
        member_count=row.member_count,
        score=row.score,
        corrected_p=row.corrected_p,
        by_family=dict(row.by_family_json or {}),
        needs_adjudication=row.needs_adjudication,
        weakly_attached=list(row.weak_members_json or []),
        attachment_note=row.attachment_note,
        attachment_checked=bool(row.attachment_checked),
        corroboration=row.corroboration_json or None,
        evidence=[EvidenceOut(**e) for e in (row.evidence_json or [])],
        corpus_size=row.corpus_size,
        null_shuffles=row.null_shuffles,
        null_threshold=row.null_threshold,
        status=row.status,
        dismissal_reason=row.dismissal_reason,
        confirmed=row.confirmed_at is not None,
    )


class SectionOut(BaseModel):
    """A comment section this deployment looked at and could not resolve.

    Deliberately names NO accounts. The group failed the significance test, and the statistic that
    flagged the section cannot separate an operation from a community that simply turned up
    together, so naming anyone would publish a claim the evidence could not support. What is served
    is the shape and the next step.
    """

    id: int
    investigation_id: int | None
    context_id: str | None
    platform: str
    corpus_size: int
    #: Hard-family behaviours the group shares that the rarity ceiling discarded as ordinary.
    suppressed: int
    group_size: int
    #: The largest share of the section any suppressed behaviour reached.
    top_prevalence: float
    families: list[str]
    sentence: str
    #: WHAT THE CATALOGUE SAID, and the reason a row in this queue is worth opening. The section
    #: could not price its own dominant group, but a formation profile carries the surprise each
    #: feature had where it was LEARNED, so it does not read this section's rarity at all.
    #: Measured: through the section recall falls 8/8 to 0 between 24% and 32% share, while through
    #: the catalogue it stays 8/8 at 32%, 40% and 50%, placing nobody on the innocent controls that
    #: also trip this statistic.
    #:
    #: THREE STATES. `catalogue_checked` false means it was never consulted (an older row, or a run
    #: whose fallback failed); true with `catalogue_empty` means nothing has been catalogued yet;
    #: true without it means it looked. Two of the three show zero placements and they are not the
    #: same statement about the people who commented here.
    catalogue_checked: bool
    catalogue_empty: bool
    #: Counts, never names. A placement is a claim about a person and belongs in the sweep panel,
    #: which renders the evidence a reader needs to argue with it.
    catalogue_placed: int
    #: Of those, how many would have passed an individual review: the part of the section no
    #: per-account score would have caught, and the row to read first.
    catalogue_concealed: int
    status: str
    review_note: str | None
    created_at: datetime
    updated_at: datetime


#: Served with the list, because a queue of these could otherwise be read as a queue of operations.
SECTION_NOTE = (
    "These are sections this scan could not resolve, NOT sections where an operation was found. A "
    "group large enough to shape the background it is measured against cannot be priced by that "
    "background in either direction: the same shape is produced by an operation and by a community "
    "that turned up together. What the run CAN still do is weigh these accounts against the "
    "formation catalogue, which measures them against other investigations rather than against "
    "this one, and each row carries the result. A row that placed nobody is not a clean section: "
    "the catalogue only recognises operations somebody has already recorded."
)


class SectionListOut(BaseModel):
    sections: list[SectionOut]
    note: str = SECTION_NOTE


def _section_out(row) -> SectionOut:
    return SectionOut(
        id=row.id,
        investigation_id=row.investigation_id,
        context_id=row.context_id,
        platform=row.platform,
        corpus_size=row.corpus_size,
        suppressed=row.suppressed,
        group_size=row.group_size,
        top_prevalence=row.top_prevalence,
        families=list(row.families_json or []),
        sentence=row.sentence or "",
        # `or 0` / `or False` rather than the raw column: a row written before these existed reads
        # them as NULL, and NULL through a non-optional int field is a 500 on the whole queue.
        catalogue_checked=bool(row.catalogue_checked),
        catalogue_empty=bool(row.catalogue_empty),
        catalogue_placed=int(row.catalogue_placed or 0),
        catalogue_concealed=int(row.catalogue_concealed or 0),
        status=row.status,
        review_note=row.review_note,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@admin_router.get("/sections", response_model=SectionListOut)
def list_sections(
    status_filter: str = Query("open", pattern="^(open|reviewed|all)$", alias="status"),
    limit: int = Query(50, ge=1, le=200),
    current: CurrentUser = Depends(require_user),
) -> SectionListOut:
    """Sections that could not be resolved, worst first.

    Worst is the most SUPPRESSED evidence, not the biggest group: how much the ceiling had to throw
    away is the measure of how blind the scan was, and a small group in a small section can blind it
    more completely than a large one in a large section.
    """
    _require_admin(current)
    from app.storage.models import NetdetectSection

    with get_session() as session:
        q = select(NetdetectSection)
        if status_filter != "all":
            q = q.where(NetdetectSection.status == status_filter)
        rows = list(
            session.execute(
                q.order_by(NetdetectSection.suppressed.desc(), NetdetectSection.id.desc())
                .limit(limit)
            ).scalars()
        )
        return SectionListOut(sections=[_section_out(r) for r in rows])


class ReviewRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)

    @field_validator("note")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        # `min_length` alone admits "   ", which strips to nothing on the way into the column and
        # records that somebody looked and nothing about what they concluded.
        out = v.strip()
        if not out:
            raise ValueError("Say what this section turned out to be.")
        return out


@admin_router.post("/sections/{section_id}/reviewed", response_model=SectionOut)
def review_section(
    section_id: int,
    body: ReviewRequest,
    current: CurrentUser = Depends(require_user),
) -> SectionOut:
    """Record that a person read this section and what they concluded.

    NOT a dismissal of a finding, because there is no finding: the scan could not resolve the
    section, and this records what a human resolved it to. The row is kept rather than deleted, and
    a later re-run will not withdraw it, for the same reason a dismissed finding is kept: somebody's
    verdict is ground truth and this system accumulates very little of it.
    """
    _require_admin(current)
    from app.storage.models import NetdetectSection

    with get_session() as session:
        row = session.get(NetdetectSection, section_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such section.")
        row.status = "reviewed"
        row.reviewed_at = datetime.now(timezone.utc)
        row.reviewed_by = getattr(current, "id", None)
        row.review_note = body.note
        row.updated_at = row.reviewed_at
        session.commit()
        return _section_out(row)


@admin_router.get("/findings/all", response_model=list[StoredFindingOut])
def list_findings(
    status_filter: str = Query("open", pattern="^(open|dismissed|confirmed|all)$", alias="status"),
    limit: int = Query(50, ge=1, le=200),
    current: CurrentUser = Depends(require_user),
) -> list[StoredFindingOut]:
    """Everything the detector has recorded, worst first."""
    _require_admin(current)
    with get_session() as session:
        stmt = select(NetdetectFinding)
        if status_filter != "all":
            stmt = stmt.where(NetdetectFinding.status == status_filter)
        rows = list(session.execute(
            stmt.order_by(NetdetectFinding.score.desc()).limit(limit)
        ).scalars())
        return [_stored_out(r) for r in rows]


class JudgementRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        """A reason of spaces is an absent reason wearing a length.

        `min_length` alone lets `"   "` through, and it then strips to nothing on the way into the
        column, so the row records that somebody was unconvinced and nothing about why. That is the
        one thing this field exists to prevent.
        """
        stripped = v.strip()
        if not stripped:
            raise ValueError("A judgement needs a stated reason; it is the only ground truth here.")
        return stripped


@admin_router.post("/findings/{finding_id}/dismiss", response_model=StoredFindingOut)
def dismiss_finding(
    finding_id: int,
    body: JudgementRequest,
    current: CurrentUser = Depends(require_user),
) -> StoredFindingOut:
    """Record that this finding is wrong, and why.

    The reason is required and is the entire point. A dismissal with no stated reason records that
    somebody was unconvinced and nothing about what convinced them, which cannot be fitted against.
    """
    _require_admin(current)
    with get_session() as session:
        row = session.get(NetdetectFinding, finding_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such finding.")
        row.status = "dismissed"
        row.dismissed_at = _now()
        row.dismissed_by = current.id
        row.dismissal_reason = body.reason
        row.confirmed_at = None
        session.commit()
        session.refresh(row)
        return _stored_out(row)


@admin_router.post("/findings/{finding_id}/confirm", response_model=StoredFindingOut)
def confirm_finding(
    finding_id: int,
    body: JudgementRequest,
    current: CurrentUser = Depends(require_user),
) -> StoredFindingOut:
    """Record that this finding is right, and why.

    Positives are rarer and worth more than negatives. A reservoir holding only rejections can only
    ever teach the detector to be quieter, which is not the same as teaching it to be correct.
    """
    _require_admin(current)
    with get_session() as session:
        row = session.get(NetdetectFinding, finding_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such finding.")
        row.status = "confirmed"
        row.confirmed_at = _now()
        row.dismissed_at = None
        row.dismissed_by = current.id
        row.dismissal_reason = body.reason
        session.commit()
        session.refresh(row)
        return _stored_out(row)


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------------------------------
# The calibration report.
#
# IT REPORTS AND IT NEVER MOVES ANYTHING. Every constant in `app/netdetect` stays in code, with a
# commit, a reviewer and a reason beside it. A gate that retunes itself on operator clicks can be
# steered by whoever clicks, and this one decides whether named real people are reported as running
# an operation together. See the module docstring in `app/netdetect/calibration.py`.
# ---------------------------------------------------------------------------------------------------


class SweepRowOut(BaseModel):
    value: float
    confirmed_kept: int
    dismissed_kept: int
    dismissed_removed: int


class SweepOut(BaseModel):
    constant: str
    #: The file to edit by hand if the recommendation is accepted.
    where: str
    current: float
    #: "raise" or "lower". Stated because a reader cannot infer it from the numbers, and reading it
    #: backwards inverts every recommendation on the page.
    stricter_direction: str
    rows: list[SweepRowOut]
    proposed: float | None
    recommendation: str | None


class FamilySplitOut(BaseModel):
    family: str
    weight: float
    hard: bool
    mean_in_confirmed: float
    mean_in_dismissed: float
    present_in_confirmed: int
    present_in_dismissed: int
    separation: float


class NextToJudgeOut(BaseModel):
    """One open finding whose verdict would teach the most.

    NOT A SUSPICION RANKING. `flips_constants` counts how many fitted constants would classify this
    finding differently at some candidate setting, which is close to the OPPOSITE of how likely the
    group is to be an operation: a finding far above every threshold is the most obviously
    coordinated and teaches the least, because nobody needed a label to know how it would come out.
    """

    finding_id: int
    context_id: str | None
    member_count: int
    nearest_constant: str
    distance: float
    value: float
    current: float
    flips_constants: int
    why: str


class CalibrationOut(BaseModel):
    confirmed: int
    dismissed: int
    open: int
    #: False while the reservoir is too thin to fit anything. The sweeps are still returned, because
    #: watching it fill is useful and an empty response would look like a broken endpoint.
    sufficient: bool
    insufficient_reason: str
    sweeps: list[SweepOut]
    families: list[FamilySplitOut]
    recommendations: list[str]
    #: Open findings worth judging first, because their verdict would move a fit. Read the caveat:
    #: this is an information ordering, never a suspicion ordering.
    next_to_judge: list[NextToJudgeOut]
    #: How many more judgements, and of which class, before anything can be recommended. Empty once
    #: the reservoir is deep enough.
    still_needed: str
    caveats: list[str]


@admin_router.get("/findings/calibration", response_model=CalibrationOut)
def calibration_report(current: CurrentUser = Depends(require_user)) -> CalibrationOut:
    """What the accumulated judgements would move, and whether there are yet enough of them.

    Read-only in the strongest sense: it writes nothing and it changes no threshold. The output is a
    recommendation with its arithmetic attached, for a person to read and then edit
    `significance.py` or `detect.py` by hand if they agree.
    """
    _require_admin(current)
    from app.netdetect import calibration as cal

    with get_session() as session:
        report = cal.build_report(session)

    return CalibrationOut(
        confirmed=report.confirmed,
        dismissed=report.dismissed,
        open=report.open,
        sufficient=report.sufficient,
        insufficient_reason=report.insufficient_reason,
        recommendations=report.recommendations,
        caveats=report.caveats,
        sweeps=[
            SweepOut(
                constant=s.constant, where=s.where, current=s.current,
                stricter_direction=s.stricter_direction,
                proposed=s.proposed, recommendation=s.recommendation,
                rows=[
                    SweepRowOut(
                        value=r.value, confirmed_kept=r.confirmed_kept,
                        dismissed_kept=r.dismissed_kept, dismissed_removed=r.dismissed_removed,
                    )
                    for r in s.rows
                ],
            )
            for s in report.sweeps
        ],
        families=[
            FamilySplitOut(
                family=f.family, weight=f.weight, hard=f.hard,
                mean_in_confirmed=f.mean_in_confirmed, mean_in_dismissed=f.mean_in_dismissed,
                present_in_confirmed=f.present_in_confirmed,
                present_in_dismissed=f.present_in_dismissed,
                separation=round(f.separation, 3),
            )
            for f in report.families
        ],
        next_to_judge=[
            NextToJudgeOut(
                finding_id=n.finding_id, context_id=n.context_id,
                member_count=n.member_count, nearest_constant=n.nearest_constant,
                distance=n.distance, value=n.value, current=n.current,
                flips_constants=n.flips_constants, why=n.why,
            )
            for n in report.next_to_judge
        ],
        still_needed=report.still_needed,
    )


# ---------------------------------------------------------------------------------------------------
# The operation registry, and the question it exists to answer.
#
# A finding is an EVENT; an operation is a thing that persists, rotates its accounts, goes quiet and
# comes back. Detection alone starts from nothing every run, so it could never say the most useful
# thing an investigator can hear: we have seen this operator before, and here is the account that
# just walked into it.
# ---------------------------------------------------------------------------------------------------


class FormationOut(BaseModel):
    formation_key: str
    platform: str
    label: str | None
    #: forming / active / dormant / resurgent. RESURGENT exists only because the entity survived the
    #: quiet period, and it is the phase a per-run detector can never report.
    phase: str
    previous_phase: str | None
    member_count: int
    sighting_count: int
    #: Distinct posts. A re-scan of one post is one sighting, never two.
    context_count: int
    families: list[str]
    profile_size: int
    first_seen: str | None
    last_seen: str | None
    status: str
    #: What the per-account engine makes of the members, computed AFTER detection and never fed back
    #: into it. `posture: "concealed"` is the finding only this system can produce: individually
    #: unremarkable accounts that a degree-preserving null says are coordinated anyway.
    composition: dict


def _formation_out(row) -> FormationOut:
    return FormationOut(
        formation_key=row.formation_key,
        platform=row.platform,
        label=row.label,
        phase=row.phase,
        previous_phase=row.previous_phase,
        member_count=row.member_count,
        sighting_count=row.sighting_count,
        context_count=len(row.contexts_json or []),
        families=list(row.families_json or []),
        profile_size=len(row.profile_json or []),
        first_seen=row.first_seen.isoformat() if row.first_seen else None,
        last_seen=row.last_seen.isoformat() if row.last_seen else None,
        status=row.status,
        composition=dict(row.composition_json or {}),
    )


@admin_router.get("/formations", response_model=list[FormationOut])
def list_formations(
    phase: str = Query("all", pattern="^(all|forming|active|dormant|resurgent)$"),
    limit: int = Query(50, ge=1, le=200),
    current: CurrentUser = Depends(require_user),
) -> list[FormationOut]:
    """Known operations, most recently seen first."""
    _require_admin(current)
    from sqlalchemy import select as _select

    from app.netdetect import registry
    from app.storage.models import NetdetectFormation

    with get_session() as session:
        # Phases go stale by the ABSENCE of an event, so nothing ever writes to notice a formation
        # went quiet. Refresh before listing, or a year-dead operation reads as active forever.
        registry.refresh_phases(session)
        stmt = _select(NetdetectFormation)
        if phase != "all":
            stmt = stmt.where(NetdetectFormation.phase == phase)
        rows = list(session.execute(
            stmt.order_by(NetdetectFormation.last_seen.desc().nullslast()).limit(limit)
        ).scalars())
        out = [_formation_out(r) for r in rows]
        session.commit()
        return out


class MatchedOut(BaseModel):
    family: str
    kind: str
    value: str
    surprise: float
    sentence: str


class AssignmentOut(BaseModel):
    formation_key: str
    label: str | None = None
    phase: str | None = None
    #: Capped log10 likelihood ratio; what the posterior is built from.
    log_lr: float
    #: Uncapped, and used only to ORDER formations. The cap is about what may be claimed; applying
    #: it to the ranking too would collapse every strong match to one value.
    raw_log_lr: float
    posterior: float
    by_family: dict[str, float]
    #: Evidence in the operator's own acts (how accounts were made, which outside targets they
    #: converge on). A match on topic and rhythm alone is what any two automated accounts share.
    hard_evidence: float
    assigned: bool
    refused: str | None
    abstained: str | None
    matched: list[MatchedOut]


class AssignRequest(BaseModel):
    #: Investigation to take the account's behaviour from.
    slug: str = Field(min_length=1, max_length=200)
    #: The account to place. Must be a commenter stored on that investigation.
    external_id: str = Field(min_length=1, max_length=128)


ASSIGNMENT_NOTE = (
    "An assignment is a lead, not a membership record. It never reads the account's OMI score, for "
    "the same reason detection does not: a competent operation's accounts each look ordinary, and "
    "gating on suspicion would refuse exactly the members worth finding. An empty result means no "
    "KNOWN formation matched, never that the account is uncoordinated, because an operation nobody "
    "has catalogued yet is precisely what the detector exists to find."
)


class AssignOut(BaseModel):
    external_id: str
    handle: str
    #: Every formation weighed, best first, including the refusals. "We looked at forty and refused
    #: all of them" is a more trustworthy statement than an empty list.
    candidates: list[AssignmentOut]
    best: AssignmentOut | None
    note: str = ASSIGNMENT_NOTE


def _assignment_out(a, labels: dict) -> "AssignmentOut":
    """One serialiser for both the single assignment and the sweep.

    Shared rather than copied: the two routes make the same claim about a named person, and a
    second copy is how one of them quietly stops carrying `refused` or `hard_evidence`. This
    codebase has already paid for a hardcoded field list once, in
    `coerce_comprehensive_model_output`.
    """
    label, phase = labels.get(a.formation_key, (None, None))
    return AssignmentOut(
        formation_key=a.formation_key, label=label, phase=phase,
        log_lr=a.log_lr, raw_log_lr=a.raw_log_lr, posterior=a.posterior,
        by_family={k: round(v, 3) for k, v in sorted(a.by_family.items())},
        hard_evidence=round(a.hard_evidence, 3),
        assigned=a.assigned, refused=a.refused, abstained=a.abstained,
        matched=[MatchedOut(family=m.family, kind=m.kind, value=m.value,
                            surprise=m.surprise, sentence=m.sentence)
                 for m in a.matched[:12]],
    )


class PlacementOut(BaseModel):
    external_id: str
    handle: str
    assignment: AssignmentOut
    #: The account's own OMI score. CHARACTERISATION ONLY: placement reads behaviour, never this.
    #: Null means the account was never scored, which is not the same as scoring low.
    omi_score: float | None = None
    #: Placed in a known operation while reading as an ordinary account on its own. THE MOST
    #: VALUABLE ROW IN A SWEEP: an account the per-account engine already flags is one an analyst
    #: could have found without this, and one that would pass an individual review is not.
    concealed: bool = False


class FormationSweepOut(BaseModel):
    """Every scanned account weighed against every known formation.

    Named for the formations rather than plain `SweepOut`, which the calibration report already
    uses for its threshold sweeps. Two different meanings of "sweep" in one router is the kind of
    collision that gets noticed by a linter once and by a reader never.
    """

    slug: str
    accounts_weighed: int
    formations_considered: int
    placed: list[PlacementOut]
    #: A COUNT, never a list of names. Publishing "these 140 matched nothing" invites reading it as
    #: a clean bill of health, which is exactly what `not_a_clearance` says it is not.
    unplaced: int
    #: True when the account cap was reached, so an empty result is never mistaken for a complete
    #: one that found nothing.
    truncated: bool
    #: Set when there is no catalogue to compare against yet, which is not the same as no match.
    nothing_catalogued: bool
    #: How many placed accounts would have passed an individual review. The number an analyst
    #: should read first: it is the part of the section no per-account score would have caught.
    concealed: int
    not_a_clearance: str


@admin_router.post("/formations/sweep", response_model=FormationSweepOut)
def sweep_investigation(
    slug: str = Query(..., description="The investigation whose commenters to weigh."),
    current: CurrentUser = Depends(require_user),
) -> FormationSweepOut:
    """Is anybody in this comment section part of an operation we already know about?

    THE QUESTION AN ANALYST ACTUALLY HAS. `/formations/assign` answers "does THIS account belong to
    THAT operation", which needs somebody to already suspect both. When a comment section lands
    nobody suspects anything yet, so the useful direction is the other way round: sweep every
    scanned account against the whole catalogue and surface the ones that place.

    This is also the only part of the system that can catch an operation ACROSS investigations
    without re-detecting it. `detect` finds formations inside one corpus; an account scanned today
    could belong to something catalogued weeks ago in a different customer's scan, and nothing else
    would say so.

    Costs nothing: no provider call, no model call, no credit, no write. It reads a stored payload
    and stored profiles.
    """
    _require_admin(current)
    from app.netdetect import registry
    from app.netdetect.assign import NOT_A_CLEARANCE, sweep
    from app.netdetect.features import profile_from_commenter

    with get_session() as session:
        inv = session.execute(
            select(Investigation).where(Investigation.slug == slug)
        ).scalar_one_or_none()
        if inv is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such investigation.")
        payload = inv.payload_json or {}
        target = str(getattr(inv, "target_id", "") or "")
        rows = [c for c in (payload.get("commenters") or []) if isinstance(c, dict)
                and c.get("external_id")]
        profiles = registry.load_profiles(session)
        labels = {
            f.formation_key: (f.label, f.phase)
            for f in session.execute(select(NetdetectFormation)).scalars()
        }

    exclude = {target} if target else set()
    accounts = [profile_from_commenter(r, exclude_context=exclude) for r in rows]
    result = sweep(accounts, profiles)

    return FormationSweepOut(
        slug=slug,
        accounts_weighed=len(result.placed) + result.unplaced,
        formations_considered=result.formations_considered,
        unplaced=result.unplaced,
        truncated=result.truncated,
        nothing_catalogued=not result.looked,
        concealed=sum(1 for p in result.placed if p.concealed),
        not_a_clearance=NOT_A_CLEARANCE,
        placed=[
            PlacementOut(
                external_id=p.external_id,
                handle=p.handle,
                assignment=_assignment_out(p.assignment, labels),
                omi_score=p.omi_score,
                concealed=p.concealed,
            )
            for p in result.placed
        ],
    )


@admin_router.post("/formations/assign", response_model=AssignOut)
def assign_account(
    body: AssignRequest,
    current: CurrentUser = Depends(require_user),
) -> AssignOut:
    """Which known operation does this scanned account belong to?

    NESTED UNDER /formations ON PURPOSE. At `/assign` this was silently shadowed by
    `POST /{slug}`, which is declared first and matched it with slug="assign", so every call came
    back 404 "No such investigation" and read as a data problem rather than a routing one. CLAUDE.md
    records the same trap for `/v1/investigations/claim`, which is safe only because `{slug}` is GET
    and PATCH there. A two-segment path cannot be shadowed by a one-segment parameter at all, which
    is a structural fix rather than an ordering one somebody has to remember.

    THE CAPABILITY DETECTION CANNOT PROVIDE. `detect` finds formations inside one corpus and forgets
    them, so an account scanned today could belong to an operation catalogued weeks ago in a
    different customer's investigation and nothing would say so. This asks that question directly,
    as a likelihood ratio against each known formation's discriminative profile.

    Costs nothing: no provider call, no model call, no credit. It reads a payload already stored.
    """
    _require_admin(current)
    from app.netdetect import registry
    from app.netdetect.assign import rank
    from app.netdetect.features import profile_from_commenter

    with get_session() as session:
        inv = session.execute(
            select(Investigation).where(Investigation.slug == body.slug)
        ).scalar_one_or_none()
        if inv is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such investigation.")
        payload = inv.payload_json or {}
        target = str(getattr(inv, "target_id", "") or "")
        rows = [c for c in (payload.get("commenters") or []) if isinstance(c, dict)]
        row = next((r for r in rows if str(r.get("external_id")) == body.external_id), None)
        if row is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                "That investigation did not scan that account, so there is no behaviour to place.",
            )
        profiles = registry.load_profiles(session)
        labels = {
            f.formation_key: (f.label, f.phase)
            for f in session.execute(select(NetdetectFormation)).scalars()
        }

    account = profile_from_commenter(row, exclude_context={target} if target else set())
    results = rank(account, profiles)

    serialised = [_assignment_out(a, labels) for a in results]
    winner = next((s for s in serialised if s.assigned), None)
    return AssignOut(
        external_id=body.external_id,
        handle=str(row.get("handle") or ""),
        candidates=serialised[:20],
        best=winner,
    )
