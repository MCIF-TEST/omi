"""What we already knew about these people, before this post.

THE LAYER THAT WAS BUILT AND NEVER READ BACK. `campaigns/tracking/graph.py` has been folding every
finding's pairwise evidence into `CoordinationEdge` since the tracking layer shipped, accumulating a
record of which accounts keep turning up together across unrelated posts. `netdetect.detect` has
never once consulted it. Every run scores a set purely on what this corpus shows, as though the
deployment had no memory at all.

---------------------------------------------------------------------------------------------------
THE MEASUREMENT THAT DECIDED THE DESIGN, AND IT IS THE OPPOSITE OF THE OBVIOUS ONE
---------------------------------------------------------------------------------------------------

The tempting version of this module adds accumulated history to a finding's confidence: seen
together before, therefore more likely an operation. That was measured against this package's own
innocent controls, each seeded under three unrelated posts, and it is WRONG:

    group        total log_lr   pairs with history   pairs with HARD history
    operation      2.000 (cap)         28                    28
    newsroom       2.000 (cap)         45                     0
    fan community  0.000                0                     0
    organic        0.598                1                     0

An operation and a newsroom covering one beat are INDISTINGUISHABLE on total accumulated history,
and the newsroom carries more linked pairs than the operation. Reporters on a beat genuinely keep
appearing under the same posts; that is what a beat is. So a confidence lift driven by history would
promote the exact control this package exists to refuse, and it would do it with a number that looks
like corroborating evidence.

What separates them is WHICH FAMILIES the prior evidence sits in, which is `MIN_HARD_EVIDENCE`'s
insight extended across time. `HARD_FAMILIES` are the operator's own acts: provisioning a batch of
accounts (identity) and converging on outside targets (network). A shared profession produces text,
timing and infrastructure overlap for free and produces neither of those. Measured, the operation's
prior evidence was hard on all 28 pairs and the newsroom's on none of 45.

So this module reports two different things and never conflates them:

* **`log_lr` is CONTEXT.** How much has accumulated. It does not discriminate, it is not added to
  any score, and the docstring above is why.
* **`hard_pairs` / `hard_families` are the DISCRIMINATING half.** Prior evidence of the operator's
  own acts, gathered under other posts.

---------------------------------------------------------------------------------------------------
WHY THIS IS A PRIOR AND NOT A SEVENTH FAMILY
---------------------------------------------------------------------------------------------------

The families in `significance.py` are all measured INSIDE one corpus against a null built from that
corpus, and the shuffled search correction in `shuffle.py` is what makes their sum honest. History is
measured somewhere else entirely, so adding it as a family would slip evidence past the correction it
was never subjected to. It belongs beside the corrected result, not inside it: `corrected_p` answers
"is this set surprising in this corpus", corroboration answers "and had we seen these people doing
this before". Two questions, two numbers.

---------------------------------------------------------------------------------------------------
THREE RULES
---------------------------------------------------------------------------------------------------

* **THE CURRENT POST IS EXCLUDED.** An edge that accumulated its evidence from this very
  investigation is not independent corroboration, it is the same observation counted twice.
  `contexts_json` records which posts contributed, so the exclusion is exact rather than approximate.
  Without it a formation would corroborate itself the moment it was first recorded, and every re-run
  would strengthen the illusion.
* **IT NEVER MANUFACTURES A FINDING AND NEVER CLEARS ONE.** History does not promote a candidate that
  failed the shuffled search, and it does not clear `needs_adjudication`. That flag means a person
  has to look; resolving it from accumulated numbers would be a threshold quietly overruling a human
  review step, which is the same thing `calibration.py` refuses to do.
* **REPEAT SIGHTINGS ARE ALREADY DISCOUNTED** where they accumulate, by
  `tracking/graph.REPEAT_DISCOUNT`. This module does not discount again: doing so would price the
  same correlation twice and quietly make history worthless.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select

from app.netdetect.types import HARD_FAMILIES
from app.storage.models import CoordinationEdge

logger = logging.getLogger("omi.netdetect.corroboration")

#: Ceiling on the total reported for one set. History is context, not a verdict, and it is capped so
#: a long-running subject cannot present an unbounded number beside a bounded one. Note the measured
#: table above: both the operation and the newsroom SATURATE this, which is precisely why the total
#: is not a discriminator and nothing may key a decision on it.
MAX_HISTORY_LOG10 = 2.0

#: Pairs beyond this are not queried. A finding is bounded upstream, and an unbounded IN clause over
#: a large member list is how a cheap read becomes a slow one on a page an operator is waiting for.
MAX_PAIRS = 800


@dataclass(slots=True)
class Corroboration:
    """What the accumulating graph already held about this set, from OTHER posts."""

    #: Total accumulated log10 evidence from other contexts. CONTEXT ONLY: measured not to separate
    #: an operation from a newsroom (both saturate the cap). Never add this to a score.
    log_lr: float = 0.0
    #: Pairs of these members carrying any prior evidence.
    pairs_with_history: int = 0
    #: Pairs whose prior evidence includes a HARD family. This is the half that discriminates:
    #: measured 28 of 28 on a planted operation and 0 of 45 on the professional-beat control.
    hard_pairs: int = 0
    #: Distinct earlier posts contributing. One post seen twice is one observation.
    contexts: list[str] = field(default_factory=list)
    #: Families that carried the prior evidence.
    families: list[str] = field(default_factory=list)
    #: The subset of those that are the operator's own acts (identity, network).
    hard_families: list[str] = field(default_factory=list)
    #: Set when the lookup could not run. Never read a zero here as "these people were strangers":
    #: it may mean nobody looked. Same distinction as `attachment_checked`.
    unavailable: str | None = None

    @property
    def checked(self) -> bool:
        return self.unavailable is None

    @property
    def seen_before(self) -> bool:
        return self.checked and bool(self.contexts)

    @property
    def hard_history(self) -> bool:
        """Prior evidence of the operator's OWN ACTS under other posts. The discriminating claim."""
        return self.checked and self.hard_pairs > 0 and bool(self.hard_families)

    def sentence(self) -> str:
        """One line for a reader, phrased so the total is never mistaken for a verdict."""
        if self.unavailable:
            return f"No history was read: {self.unavailable}"
        if not self.contexts:
            return "These accounts have not been seen together before this post."
        posts = len(self.contexts)
        s = "s" if posts != 1 else ""
        head = (
            f"{self.pairs_with_history} of these pairs were already seen together under "
            f"{posts} earlier post{s}."
        )
        if self.hard_history:
            return (
                f"{head} {self.hard_pairs} of them on the operator's own acts "
                f"({', '.join(self.hard_families)}), which a shared profession or interest does not "
                f"produce."
            )
        return (
            f"{head} None of it is the operator's own acts, which is also what a group covering one "
            f"beat looks like, so this is context rather than corroboration."
        )


def for_members(session, members: list[str], *, platform: str,
                exclude_context: str | None) -> Corroboration:
    """Prior pairwise evidence about this set, from posts other than the one in hand.

    Best-effort by construction: a failure here costs context on a finding and must never turn a
    completed detection into an error.
    """
    out = Corroboration()
    unique = sorted(dict.fromkeys(m for m in members if m))
    if len(unique) < 2:
        return out
    if len(unique) * (len(unique) - 1) // 2 > MAX_PAIRS:
        out.unavailable = (
            f"{len(unique)} members is more pairs than this lookup runs for; the finding stands on "
            f"the current corpus alone"
        )
        return out

    try:
        rows = list(session.execute(
            select(CoordinationEdge).where(
                CoordinationEdge.platform == platform,
                CoordinationEdge.account_a.in_(unique),
                CoordinationEdge.account_b.in_(unique),
            )
        ).scalars())
    except Exception as exc:  # noqa: BLE001
        logger.warning("netdetect: could not read coordination history", exc_info=True)
        out.unavailable = str(exc)[:200]
        return out

    inside = set(unique)
    hard = set(HARD_FAMILIES)
    contexts: set[str] = set()
    families: set[str] = set()
    hard_families: set[str] = set()
    total = 0.0
    pairs = 0
    hard_pairs = 0

    for row in rows:
        # The IN clause matches each column independently, so a row pairing a member with an
        # outsider can come back. Both ends have to be inside the set for it to be about the set.
        if row.account_a not in inside or row.account_b not in inside:
            continue
        row_contexts = [c for c in (row.contexts_json or []) if c]
        # THE EXCLUSION THAT MAKES THIS INDEPENDENT. An edge whose only context is the post being
        # scanned carries nothing this corpus has not already supplied.
        other = [c for c in row_contexts if c != exclude_context]
        if not other:
            continue

        carried = float(row.log_lr_sum or 0.0)
        if carried <= 0:
            continue
        # Attribute only the share that came from other posts. Crediting the whole sum would count
        # this post's own contribution a second time.
        total += carried * (len(other) / max(1, len(row_contexts)))
        pairs += 1
        contexts.update(other)

        row_families = {f for f in (row.families_json or []) if f}
        families.update(row_families)
        if row_families & hard:
            hard_pairs += 1
            hard_families.update(row_families & hard)

    out.log_lr = round(min(MAX_HISTORY_LOG10, total), 6)
    out.pairs_with_history = pairs
    out.hard_pairs = hard_pairs
    out.contexts = sorted(contexts)[:20]
    out.families = sorted(families)
    out.hard_families = sorted(hard_families)
    return out


def annotate(session, candidates, *, platform: str | None = None,
             exclude_context: str | None = None) -> int:
    """Attach corroboration to findings and to refused candidates alike.

    Refused candidates are included deliberately: a set the current corpus could not prove, whose
    members were already seen doing the operator's own acts under other posts, is the most useful
    thing in the near-miss pile. It stays refused, because history must never manufacture a finding,
    and it becomes a lead a person can act on.

    **Stated honestly: that path has not been observed firing.** Across every synthetic scenario in
    `tests/netdetect_corpora.py` the rejected list is empty, because a candidate weak enough to fail
    the shuffled search is normally caught earlier by a structural refusal and never reaches it.
    Whether real corpora produce a near-miss pile at all is unmeasured, so treat the lead path as
    built and unproven rather than as a feature.

    Must run BEFORE this run's own pairs are folded into the graph. The context exclusion makes it
    correct either way, but reading first keeps the two acts in the order a reader would assume.
    """
    annotated = 0
    for candidate in candidates:
        try:
            # The candidate's OWN platform, because the graph is keyed on it and a cross-platform
            # lookup would silently return nothing. `platform` is only a fallback for a candidate
            # that carries none.
            where = getattr(candidate, "platform", None) or platform
            if not where:
                continue
            candidate.corroboration = for_members(
                session, candidate.members, platform=where, exclude_context=exclude_context,
            )
            annotated += 1
        except Exception:  # noqa: BLE001
            logger.warning("netdetect: could not annotate a candidate", exc_info=True)
    return annotated
