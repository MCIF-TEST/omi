"""Keeping netdetect's findings, and folding them into the graph that accumulates.

WHY THIS EXISTS. The detector was read-only, and that cost it twice. Its findings evaporated when
the page closed, so the tracking layer that survives account rotation learned only from the older
cohort detector; and there was nothing for an operator to dismiss, so the one reservoir of ground
truth this system will ever accumulate stayed empty while the better detector ran.

---------------------------------------------------------------------------------------------------
THE HONEST PART: A SET FINDING IS NOT A PAIR FINDING
---------------------------------------------------------------------------------------------------

netdetect's whole thesis is that a set-level statistic is not recoverable by fusing pairwise ones,
so turning a set finding back into pairwise edges has to be done carefully or it undoes the
argument. This module does NOT distribute the set score across pairs. Doing that would invent
pairwise significance nobody measured and would put a number in the graph that no test produced.

Instead each pair carries only the surprise of the features THAT PAIR ACTUALLY SHARES, taken from
the finding's own evidence list. The set-level correction decides whether a finding is worth
recording at all; the pairwise decomposition records what the pair itself was seen doing. Those are
different claims and the code keeps them apart.

The consequence worth knowing: a pair in a large finding that shares only one weak feature
contributes almost nothing, even though the finding as a whole scored highly. That is correct. The
set was significant; that pair, on its own, was not.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.netdetect.significance import Corpus
from app.netdetect.types import Candidate
from app.storage.models import NetdetectFinding

logger = logging.getLogger("omi.netdetect.persist")

#: Longest member list folded into pairwise edges WHOLE. Pairs grow quadratically, so a 200-account
#: finding would write ~20,000 rows for one observation.
#:
#: THE OTHER HALF OF THIS NOTE USED TO SAY SUCH A FINDING "is refused upstream anyway", AND THAT WAS
#: FALSE. Measured on a 168-account section, the amplifier ring produces findings of 44 and 49
#: members that are published (with a review flag), and both folded to exactly NOTHING: the
#: deployment's memory learned nothing at all from its largest findings, silently, because a
#: returned empty mapping is indistinguishable from a finding with no shared evidence.
#:
#: DO NOT "FIX" THAT BY RAISING THIS CONSTANT. Measured on the 49-member finding, folding it whole
#: writes 997 edges in 0.61s, so cost is not what makes it a bad idea: **969 of those 997 pairs
#: touch an innocent account**. The cap has been protecting the permanent graph from the worst
#: findings for a reason its own docstring never stated, and raising it would pour 97%
#: bystander-touching weight into shared state that `corroboration.py` reads back forever.
#:
#: What happens above the cap instead is a fallback to the finding's CORE, exactly as
#: `candidates._densest_core` falls back rather than discarding a community that exceeds
#: `MAX_GROUP_SHARE`. See `pair_evidence_from`.
MAX_MEMBERS_FOR_PAIRS = 40


def members_key(members: list[str]) -> str:
    """The identity of the SET, because the set is what was tested."""
    return "|".join(sorted(members))


def pair_evidence_from(corpus: Corpus, candidate: Candidate) -> dict[tuple[str, str], dict[str, float]]:
    """Per-pair, per-family log10 surprise, from the features each pair genuinely shares.

    Reads the candidate's own evidence rather than recomputing, so what lands in the graph is
    exactly what a reader was shown. A feature held by only one member of a pair contributes
    nothing to that pair, which is the point.

    THAT LAST RULE IS WHAT CONTAINS A CONTAMINATED FINDING, and it was measured rather than assumed.
    A finding's pairs go into the graph permanently, and the amplifier ring publishes 52.9%
    bystanders, so an over-broad finding could poison the deployment's memory rather than one page.
    Measured on the PINNED corpus family (organic seed 31, the one the contamination figure cites):
    1189 pairs recorded, 937 touching an innocent account and 56.5% of the accumulated weight, and
    ONE of those 937 carrying a hard family.

    So contamination lands almost entirely in `log_lr`, which `corroboration.py` already documents
    as non-discriminating (a newsroom saturates it too), and at 0.1% in `hard_pairs`, which is what
    decisions are keyed on.

    IT IS NOT ZERO, AND AN EARLIER VERSION OF THIS NOTE SAID IT WAS. The first measurement used a
    different corpus family (organic seed equal to the ring seed) and reported zero, and the reason
    given was that a hard family is the operator's own act which a bystander does not perform. That
    reasoning is wrong for one feature: `creation_week` is a PROPERTY, not an act, so an innocent
    account can be provisioned in the same week by coincidence. `repost_of` is an act and never
    contaminated in any configuration measured.

    The safety conclusion survives on a better footing, already stated in `assign.py`:
    `MIN_HARD_FEATURES` requires TWO distinct hard features to place an account, precisely because a
    rare `creation_week` clears `MIN_HARD_EVIDENCE` alone. One coincidence is never enough.

    MEASURED AND DELIBERATELY NOT TAKEN: RESTRICTING TO THE CORE BELOW THE CAP TOO. The fallback
    above the cap folds only the members the membership test says carry the finding, and that same
    restriction would work below it. On the ring findings that sit under the cap it is dramatic:

        finding      folded today   touching an innocent account   core only   innocent
        38 members            578                            550          28          0
        40 members            624                            596          28          0
        23 members            185                            157          28          0

    Across every corpus measured it drops no genuine pair and keeps no bystander-touching one, and
    the controls are untouched because a real community is what `attachment` abstains on (the
    newsroom's 45 pairs are identical either way).

    IT IS STILL NOT DONE, and the reason is the same one that keeps the trim in CLAUDE.md's open
    decisions. Today's behaviour is not a bug: the contamination above was measured, and accepted on
    the argument that it lands in `log_lr` (which does not discriminate) rather than in `hard_pairs`
    (which does). Changing it improves on a documented trade rather than fixing a defect, and it
    changes what the deployment permanently remembers about named real people on synthetic evidence.
    The silent zero ABOVE the cap was a defect, because its stated justification was false, and that
    is the part fixed here.
    """
    members = sorted(candidate.members)
    if len(members) < 2:
        return {}

    fold = members
    if len(members) > MAX_MEMBERS_FOR_PAIRS:
        # TOO LARGE TO FOLD WHOLE, SO FOLD ITS CORE RATHER THAN NOTHING. This used to return an
        # empty mapping, which meant the largest findings contributed nothing to the accumulating
        # graph and nothing recorded that they had not: an empty return also means "this finding
        # shares no pairwise evidence", so the two were indistinguishable.
        #
        # The core is the members the membership test says actually carry the finding. Measured on
        # the two ring findings that cross the cap (49 and 44 members), the core is 8 accounts and
        # 28 pairs, with ZERO touching an innocent account, against 997 and 883 pairs of which 969
        # and 855 do. So this both raises coverage (0 pairs to 28) and is cleaner than folding the
        # whole finding would have been.
        #
        # WITHOUT A MEMBERSHIP VERDICT THERE IS NO CORE, and the old behaviour stands. An abstention
        # is not permission to guess at who belongs: `attachment_checked` false means nobody looked,
        # which is exactly the case where picking a subset would be inventing one.
        weak = set(candidate.weakly_attached or ())
        core = [m for m in members if m not in weak]
        if not candidate.attachment_checked or not (2 <= len(core) <= MAX_MEMBERS_FOR_PAIRS):
            return {}
        fold = core

    fold_set = set(fold)
    out: dict[tuple[str, str], dict[str, float]] = {}
    for item in candidate.evidence or []:
        holders = corpus.feature_accounts.get(item.feature)
        if not holders:
            continue
        # THE DIVISOR STAYS OVER THE WHOLE FINDING, not over the core, and that is what makes the
        # fallback a strict subset. Dividing among the core's pairs instead would hand each of them
        # a larger share than folding the finding whole would have, which is inventing weight out of
        # a cost cap. Every edge written here carries exactly the number it would have carried with
        # no cap at all; there are simply fewer of them.
        sharing = sorted(set(holders) & set(members))
        if len(sharing) < 2:
            continue
        # Spread across the pairs that actually share it, so one feature held by ten accounts does
        # not deposit its full surprise onto each of the forty-five pairs it touches. Without this
        # a single popular-among-the-group feature would dominate the accumulated graph.
        pairs = [(a, b) for i, a in enumerate(sharing) for b in sharing[i + 1:]]
        if not pairs:
            continue
        share = item.surprise / float(len(pairs))
        for pair in pairs:
            if pair[0] not in fold_set or pair[1] not in fold_set:
                continue
            bucket = out.setdefault(pair, {})
            bucket[item.feature.family] = bucket.get(item.feature.family, 0.0) + share
    return out


def persist_finding(
    session,
    candidate: Candidate,
    corpus: Corpus,
    *,
    investigation_id: int | None,
    context_id: str | None,
    platform: str,
    corpus_size: int,
    null_shuffles: int,
    null_threshold: float | None,
    accumulate: bool = True,
    member_scores: list[float | None] | None = None,
    now: datetime | None = None,
) -> NetdetectFinding:
    """Store one finding, and fold its pairs into the global graph.

    Upserts on ``(investigation_id, members_key)``: re-running the detector on a post updates the
    row rather than stacking duplicates, and an operator re-runs constantly while tuning.

    **A dismissed row keeps its dismissal** when the numbers are refreshed. Somebody who has already
    said "this is a newsroom" must not be asked again on the next re-run, and silently reopening it
    would make the dismissal worthless as the training signal it is the only source of.
    """
    at = now or datetime.now(timezone.utc)
    key = members_key(candidate.members)

    row = session.execute(
        select(NetdetectFinding).where(
            NetdetectFinding.investigation_id == investigation_id,
            NetdetectFinding.members_key == key,
        )
    ).scalar_one_or_none()
    if row is None:
        row = NetdetectFinding(investigation_id=investigation_id, members_key=key)
        session.add(row)

    row.context_id = context_id
    row.platform = candidate.platform or platform
    row.members_json = sorted(candidate.members)
    row.member_count = len(candidate.members)
    row.score = float(candidate.score)
    row.corrected_p = candidate.corrected_p
    row.by_family_json = {k: round(v, 6) for k, v in (candidate.by_family or {}).items()}
    row.needs_adjudication = candidate.needs_adjudication
    row.weak_members_json = list(getattr(candidate, "weakly_attached", []) or [])
    row.attachment_note = getattr(candidate, "attachment_note", None)
    row.attachment_checked = bool(getattr(candidate, "attachment_checked", False))
    # What was already known about these people from other posts, as of this run. A snapshot, like
    # `score` and `corrected_p`, refreshed whenever the detector is re-run on this investigation.
    # Left as NULL when the lookup did not run, which must never be read as "never seen together".
    _cor = getattr(candidate, "corroboration", None)
    row.corroboration_json = None if _cor is None else {
        "log_lr": round(_cor.log_lr, 6),
        "pairs_with_history": _cor.pairs_with_history,
        "hard_pairs": _cor.hard_pairs,
        "contexts": list(_cor.contexts),
        "families": list(_cor.families),
        "hard_families": list(_cor.hard_families),
        "checked": _cor.checked,
        "sentence": _cor.sentence(),
    }
    # WHICH MEMBERS HOLD EACH FEATURE, not just how many.
    #
    # `shared_by` is a count, and a count cannot answer the question a reviewer actually has about a
    # named group: are these the SAME people across the evidence, or two sub-groups joined at a
    # seam? The finding is a members-by-features incidence structure and everything downstream had
    # been storing two disconnected projections of it, so the join could only be taken on faith.
    #
    # It is also the honest form of the per-member number this package already refused. Publishing
    # how much shared evidence a member participates in was MEASURED to rank bystanders above
    # genuine operation members; naming which features each member holds shows the COMPOSITION
    # instead of the magnitude, which is the same distinction corroboration draws between `log_lr`
    # (does not discriminate) and `hard_pairs` (does).
    member_set = set(candidate.members)
    row.evidence_json = [
        {
            "family": e.feature.family,
            "kind": e.feature.kind,
            "shared_by": e.shared_by,
            # The DENOMINATOR travels with the claim. A rarity assertion with no corpus count
            # behind it asks to be trusted rather than read.
            "corpus_count": e.corpus_count,
            "surprise": round(e.surprise, 6),
            "sentence": e.sentence,
            "members": sorted(
                (corpus.feature_accounts.get(e.feature) or set()) & member_set
            ),
        }
        for e in (candidate.evidence or [])[:20]
    ]
    row.corpus_size = corpus_size
    row.null_shuffles = null_shuffles
    row.null_threshold = null_threshold
    row.updated_at = at

    if accumulate:
        _accumulate(session, candidate, corpus, context_id=context_id, platform=row.platform)
        # Resolve the finding to the OPERATION behind it, so a second campaign by the same adversary
        # is recognised even when it shares no accounts with the first. Best-effort for the same
        # reason accumulation is: losing it degrades future findings and must never turn a completed
        # run into an error for the operator reading the results now.
        try:
            from app.netdetect import registry

            formation, _how = registry.record(
                session, candidate, corpus,
                platform=row.platform, context_id=context_id, scores=member_scores,
            )
            row.formation_key = formation.formation_key
        except Exception:  # noqa: BLE001
            logger.warning("netdetect: could not resolve a finding to a formation", exc_info=True)
    return row


def persist_section(
    session,
    domination,
    *,
    investigation_id: int | None,
    context_id: str | None,
    platform: str,
    corpus_size: int,
    catalogue=None,
    now: datetime | None = None,
):
    """Record, or clear, "this section could not be resolved".

    Returns the row when one is held open, and None when the section is resolvable and any earlier
    warning has been withdrawn.

    THE WITHDRAWAL IS THE HALF THAT IS EASY TO FORGET AND WORST TO GET WRONG. These rows are written
    on a re-run, and a section stops being unresolvable as soon as enough ordinary accounts comment
    under the post to give the group a background again. A warning left standing after that is a
    claim about a comment section that is no longer true, sitting in a queue an operator is meant to
    trust. So a resolvable section deletes its row rather than leaving it.

    A row an operator has already REVIEWED is kept, for the same reason a dismissed finding is kept:
    somebody's verdict is the only ground truth this system accumulates, and silently deleting it
    would make reviewing worthless.

    ``catalogue`` is what the formation catalogue said about this section, and it is the reason the
    row is worth opening at all: the section could not resolve itself, but a profile learned in a
    DIFFERENT investigation does not depend on this section's rarity, so it can still place these
    accounts. Counts only, never names, exactly as the rest of this row: a placement is a claim
    about a person and belongs in the sweep panel that renders its evidence. Optional, because a
    caller that could not run the fallback must still be able to write the warning.
    """
    from app.storage.models import NetdetectSection

    at = now or datetime.now(timezone.utc)
    existing = session.execute(
        select(NetdetectSection).where(
            NetdetectSection.investigation_id == investigation_id,
            NetdetectSection.context_id == context_id,
        )
    ).scalar_one_or_none()

    if domination is None or not domination.unresolvable:
        if existing is not None and existing.status == "open":
            session.delete(existing)
        return None

    row = existing
    if row is None:
        row = NetdetectSection(
            investigation_id=investigation_id, context_id=context_id, created_at=at,
        )
        session.add(row)
    row.platform = platform or "unknown"
    row.corpus_size = corpus_size
    row.suppressed = domination.suppressed
    row.group_size = domination.group_size
    row.top_prevalence = round(domination.top_prevalence, 6)
    row.families_json = list(domination.families)
    row.sentence = domination.sentence()
    # Refreshed on every re-run, exactly as the numbers above are. The catalogue GROWS between
    # runs, so a section that placed nobody last week can place somebody today, and carrying a
    # stale zero forward would be the same defect as a stale warning left standing.
    if catalogue is not None:
        row.catalogue_checked = bool(catalogue.checked)
        row.catalogue_empty = bool(catalogue.empty)
        row.catalogue_placed = int(catalogue.placed)
        row.catalogue_concealed = int(catalogue.concealed)
    row.updated_at = at
    return row


def _accumulate(session, candidate: Candidate, corpus: Corpus, *, context_id, platform) -> int:
    """Fold the finding's pairs into `CoordinationEdge`. Never raises into the caller."""
    try:
        from app.campaigns.tracking.graph import record_pairs

        evidence = pair_evidence_from(corpus, candidate)
        if not evidence:
            return 0
        return record_pairs(
            session, platform=platform, context_id=context_id, pair_evidence=evidence,
        )
    except Exception:  # noqa: BLE001 - accumulation must never fail the run that produced it
        logger.warning("netdetect: could not accumulate a finding", exc_info=True)
        return 0
