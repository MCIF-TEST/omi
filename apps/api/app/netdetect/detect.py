"""The pipeline: corpus in, corrected findings out.

    features -> corpus -> candidates -> set-level surprise -> refusals -> shuffled null -> findings

Two properties hold everything together and both are easy to lose in a refactor:

**The search used on real data is the same callable used to build the null.** ``_search`` is passed
to ``build_null`` verbatim. A null built from a cheaper approximation would be correcting a
different search than the one that produced the output, which is worse than no correction because
it still looks like one.

**Refusals run BEFORE the null, not after.** A candidate that fails a structural rule is not a weak
finding to be filtered later; it is a candidate that should never have entered the search, and
leaving it in would inflate the shuffled maxima it is then compared against.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
It never reads an account's OMI score or tier. Coordination and botness are orthogonal axes, and a
dense improbable cluster of LOW-scoring accounts is the most valuable thing this system can find:
that is the competent operation the old 70+ filter was blind to by construction. Scores ride along
on the output so a finding can be described, and they never touch detection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import logging
from dataclasses import dataclass, field

from app.netdetect import attachment
from app.netdetect import candidates as cand
from app.netdetect.shuffle import DEFAULT_QUANTILE, DEFAULT_SHUFFLES, build_null
from app.netdetect.significance import (
    MAX_SINGLE_FAMILY_SHARE,
    MIN_FAMILY_CONTRIBUTION,
    Corpus,
    internal_reply_ratio,
    score_candidate,
)
from app.netdetect.types import FAMILY_WEIGHT, Candidate

log = logging.getLogger("omi.netdetect")

#: A finding must rest on at least two families that EACH carry real weight, and no single family
#: may dominate.
#:
#: Counting families that merely fire is not enough, and the controls proved it: a professional beat
#: sharing a topic and a publishing tool produced three "firing" families where one carried almost
#: everything. One family is ONE KIND OF EVIDENCE however many times it fires; fifty shared shingles
#: out of one copy-pasted post is a single observation seen fifty times.
MIN_FAMILIES = 2

#: Above this internal-reply ratio the group is a conversation, not a formation.
#:
#: Real communities talk to each other and operations broadcast. This is the exculpatory half of the
#: same insight that excludes in-group targets from the evidence, and it is deliberately a REFUSAL
#: rather than a score penalty: a group whose defining behaviour is talking among itself should not
#: be reported at a lower confidence, it should not be reported.
MAX_INTERNAL_REPLY_RATIO = 0.35

#: Weighted evidence that must come from families where innocent sharing is implausible
#: (``HARD_FAMILIES``) before a finding is presentable to a customer without review. Below it the
#: finding is still reported, flagged for adjudication.
MIN_HARD_EVIDENCE = 3.0

#: Below this many accounts the null is not estimable: the shuffle has too few edges to rewire, so
#: the shuffled maxima collapse and everything looks significant. Refusing is the honest answer.
MIN_CORPUS = 25


if TYPE_CHECKING:
    from app.netdetect.domination import Domination


@dataclass(slots=True)
class DetectionResult:
    findings: list[Candidate] = field(default_factory=list)
    #: Candidates that scored but did not survive. Kept because "we looked and refused" is a
    #: different, more trustworthy statement than "we found nothing", and an operator reviewing
    #: calibration needs to see the near-misses.
    rejected: list[Candidate] = field(default_factory=list)
    corpus_size: int = 0
    rare_features: int = 0
    null_threshold: float | None = None
    null_shuffles: int = 0
    #: Set when the whole run was refused rather than merely finding nothing.
    refused: str | None = None
    #: Whether one group is large enough here to poison the null this section provides.
    #:
    #: THE DIFFERENCE BETWEEN "NOTHING FOUND" AND "CANNOT TELL". An operation that owns more than a
    #: quarter of a comment section pushes its own hard-family tells past `RARITY_CEILING`, so they
    #: are dropped as ordinary and the group is refused for want of a second family. Without this
    #: the run returns no findings and reads exactly like a clean section. See `domination.py`.
    domination: "Domination | None" = None
    #: The corpus the findings were made in. Carried so a caller can decompose a finding back to
    #: the features each pair actually shares (see `app.netdetect.persist`) without rebuilding it,
    #: which would risk rebuilding it DIFFERENTLY and attributing evidence that was never scored.
    corpus: "Corpus | None" = None

    @property
    def looked(self) -> bool:
        return self.refused is None


def _structural_refusal(corpus: Corpus, c: Candidate) -> str | None:
    """Why this candidate should never have entered the search. None means it may proceed.

    Applied INSIDE ``_search``, so the shuffled null replicates exactly the same refusals. Filtering
    after the null would compare survivors against a threshold built from a different, more
    permissive search, which quietly weakens the correction while appearing to strengthen it.
    """
    if c.score <= 0:
        return "no rare feature reached the group"

    contributing = [v for v in c.by_family.values() if v >= MIN_FAMILY_CONTRIBUTION]
    if len(contributing) < MIN_FAMILIES:
        return (
            f"only {len(contributing)} family carried real weight; a finding needs "
            f"{MIN_FAMILIES} independent kinds of evidence"
        )

    top_weighted = max(v * FAMILY_WEIGHT.get(k, 0.5) for k, v in c.by_family.items())
    if c.score > 0 and (top_weighted / c.score) > MAX_SINGLE_FAMILY_SHARE:
        return (f"one family carries {top_weighted / c.score:.0%} of the evidence; "
                f"that is one kind of thing seen many times")

    ratio = internal_reply_ratio(corpus, c.members)
    if ratio > MAX_INTERNAL_REPLY_RATIO:
        return (
            f"{ratio:.0%} of the group's replies are to each other; this is a conversation, "
            f"not a broadcast formation"
        )
    return None


def _search(corpus: Corpus) -> list[Candidate]:
    """Candidate generation plus scoring plus structural refusals. The unit the null replicates."""
    out: list[Candidate] = []
    for members in cand.communities(corpus):
        c = score_candidate(corpus, members, collect_evidence=False)
        if _structural_refusal(corpus, c) is None:
            out.append(c)
    return out


def detect(corpus: Corpus, *, shuffles: int = DEFAULT_SHUFFLES,
           quantile: float = DEFAULT_QUANTILE) -> DetectionResult:
    """Run the detector. Deterministic: the same corpus always produces the same findings."""
    result = DetectionResult(corpus_size=corpus.size, corpus=corpus)

    if corpus.size < MIN_CORPUS:
        result.refused = (
            f"corpus of {corpus.size} accounts is below the {MIN_CORPUS} needed to estimate a null. "
            "Nothing was tested."
        )
        return result

    rare = corpus.rare_features()
    result.rare_features = len(rare)
    if not rare:
        result.refused = "no rare features in this corpus; there is nothing improbable to find."
        return result

    # The significance level this run is being asked for, and whether the shuffle budget can
    # actually express it.
    #
    # THIS REFUSAL REPLACES A SILENT IMPOSSIBILITY. With K shuffles the smallest honestly
    # reportable p-value is 1/(K+1), so a run with K=8 asked for p<=0.05 can never report anything
    # no matter what is in the data. That failed silently and looked exactly like a clean corpus,
    # which is the worst way for a detector to be broken: it is indistinguishable from working.
    alpha = 1.0 - quantile
    needed = int(round(1.0 / alpha)) - 1 if alpha > 0 else 0
    if shuffles < needed:
        result.refused = (
            f"{shuffles} shuffles cannot express p<={alpha:.3f}; the smallest achievable p-value is "
            f"1/(K+1)={1 / (shuffles + 1):.3f}. Raise shuffles to at least {needed} or lower the "
            f"quantile. Nothing was tested."
        )
        return result

    # Assessed on the CANDIDATE COMMUNITIES, which is where a dominant group is still intact: the
    # generator finds it and only the significance test loses it. Computed before the early return
    # below, or the one case that most needs saying would be the one case that never says it.
    from app.netdetect import domination as dom

    result.domination = dom.assess(corpus, list(cand.communities(corpus)))

    found = _search(corpus)
    if not found:
        return result       # looked, found nothing. Not a refusal.

    null = build_null(corpus, _search, shuffles=shuffles, quantile=quantile)
    result.null_threshold = null.threshold
    result.null_shuffles = null.shuffles

    for c in sorted(found, key=lambda x: x.score, reverse=True):
        # ONE test, not two. The corrected p-value IS the decision; the quantile threshold is
        # reported alongside it because it is the number an operator can hold in their head, but
        # gating on both would let them disagree at small K and silently refuse everything.
        c.corrected_p = null.p_value(c.score)
        if c.corrected_p <= alpha:
            full = score_candidate(corpus, c.members, collect_evidence=True)
            full.corrected_p = c.corrected_p
            # A finding built only from families a profession or a community shares for free is
            # real as a statistical statement and unresolved as a claim about people. It is not
            # suppressed (that would hide genuine operations using aged accounts) and it is not
            # published either. It goes to a reader, which is the only thing that can actually tell
            # a newsroom from a formation.
            if full.hard_evidence < MIN_HARD_EVIDENCE:
                full.needs_adjudication = (
                    "no evidence of the operator's own acts: nothing shared in identity "
                    "(provisioning) or network (outside targets). A shared profession or interest "
                    "produces this pattern innocently."
                )
            # Who in this set is not carrying it. A REPORT, never an exclusion: dropping a member
            # here would change the finding's membership, score and stored identity on the strength
            # of a heuristic, and would delete a real participant when it got it the other way
            # round. See `app/netdetect/attachment.py` for why it abstains rather than guessing.
            attach = attachment.assess(corpus, full.members)
            full.weakly_attached = list(attach.weak)
            full.attachment_note = attach.abstained
            full.attachment_checked = attach.answered
            result.findings.append(full)
        else:
            c.refused = (
                f"score {c.score:.2f} did not beat the shuffled search "
                f"(threshold {null.threshold:.2f}, p={c.corrected_p:.3f})"
            )
            result.rejected.append(c)

    log.info(
        "netdetect: %d accounts, %d rare features, %d candidates, %d findings (null threshold %.2f)",
        corpus.size, len(rare), len(found), len(result.findings), null.threshold,
    )
    return result


def detect_from_commenters(rows: list[dict], *, exclude_context: set[str] | None = None,
                           shuffles: int = DEFAULT_SHUFFLES) -> DetectionResult:
    """Convenience entry point from persisted scan rows.

    ``exclude_context`` must carry the scanned post's ids. Every commenter engaged that post by
    construction, so without the exclusion the whole comment section shares a perfect feature and
    reports as one enormous operation.
    """
    from app.netdetect.features import (
        MIN_ACCOUNTS_FOR_CO_ARRIVAL,
        _parse_ts,
        arrival_scales,
        profile_from_commenter,
    )

    usable = [r for r in rows if isinstance(r, dict) and r.get("external_id")]

    # CO-ARRIVAL IS DECIDED FOR THE WHOLE CORPUS, NOT PER ACCOUNT, and it has to be.
    #
    # A shared arrival window is priced by how many accounts hold it, so it needs a population of
    # arrivals to be rare AGAINST. If only five rows carry thread comments, three of them sharing a
    # minute reads as improbable against the whole corpus while the only background that could
    # judge it is those five. That is measuring nothing and reporting a finding, so below the floor
    # the feature is not emitted at all rather than emitted and hoped about.
    with_arrivals = sum(
        1 for r in usable
        if any(isinstance(c, dict) and c.get("created_at")
               for c in (r.get("thread_comments") or []))
    )
    windows: tuple[int, ...] = ()
    all_arrivals: list = []
    if with_arrivals >= MIN_ACCOUNTS_FOR_CO_ARRIVAL:
        # Scales come from the POST'S OWN arrival rate, so "shared a window" means the same thing on
        # a thread drawing a comment an hour and one drawing sixty a minute. Computed here because
        # it is a question about the population, not about any one account.
        all_arrivals = [
            t for r in usable
            for t in (_parse_ts(c.get("created_at"))
                      for c in (r.get("thread_comments") or []) if isinstance(c, dict))
            if t is not None
        ]
        windows = arrival_scales(all_arrivals)

    profiles = [profile_from_commenter(r, exclude_context=exclude_context,
                                       arrival_windows=windows, all_arrivals=all_arrivals)
                for r in usable]
    return detect(Corpus(profiles), shuffles=shuffles)
