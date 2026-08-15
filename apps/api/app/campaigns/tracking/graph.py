"""Pairwise evidence that accumulates across every scan the deployment has ever run.

This is the part that makes tracking globally worth doing. Without it, "planet scale" would just
mean a bigger table; with it, seeing the same two accounts run the same script under two unrelated
posts is **new evidence**, and the probability moves accordingly.

Concretely: one sighting of a shared script puts a pair at P=0.86, under the bar. A second sighting
on a different post takes the same pair to P=0.99. That is the correct behaviour and it is
unreachable from a per-investigation detector, however good.

---------------------------------------------------------------------------------------------------
WHY THE SECOND SIGHTING IS DISCOUNTED
---------------------------------------------------------------------------------------------------

Two observations of the same pair are not independent. Both accounts follow the same topic, so they
turn up under the same kinds of posts, and the same script is likely to be deployed on all of them.
Treating repeat sightings as fully independent would let a single operation's normal behaviour
compound into arbitrary certainty, and by the fifth post every pair in it would read as 0.99999,
which is a claim no evidence supports.

So each additional distinct context contributes **half** its log-likelihood, and only the first
``MAX_CONTEXTS`` count at all. The first sighting is not discounted; it is already in the per-scan
posterior.

---------------------------------------------------------------------------------------------------
WHAT COUNTS AS A NEW OBSERVATION
---------------------------------------------------------------------------------------------------

A **distinct post**. Re-scanning the same post, or a continuation batch over it, is the same
observation seen twice and must not compound: that is why ``contexts_json`` stores the set of posts
rather than a counter, and why ``last_shared_parent`` could not be used (it is overwritten, so one
post scanned twice is indistinguishable from two posts).
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.campaigns.detector.probability import MAX_LOG10_LR
from app.storage.models import CoordinationEdge

logger = logging.getLogger(__name__)

#: Fraction of its log-likelihood each repeat sighting contributes. See the module docstring.
REPEAT_DISCOUNT = 0.5
#: Distinct posts beyond which further sightings add nothing. Five independent posts is already
#: decisive for any pair whose per-scan evidence was worth anything.
MAX_CONTEXTS = 5
#: Ceiling on carried evidence, below the global cap so accumulation alone can never max out the
#: posterior without any evidence on the post in front of you.
MAX_CARRIED_LOG10 = MAX_LOG10_LR / 2.0


def _ordered(a: str, b: str) -> tuple[str, str] | None:
    if not a or not b or a == b:
        return None
    return (a, b) if a < b else (b, a)


def record_pairs(
    session,
    *,
    platform: str,
    context_id: str | None,
    pair_evidence: dict[tuple[str, str], dict[str, float]],
) -> int:
    """Fold this scan's pairwise evidence into the global graph.

    ``pair_evidence`` is ``fuse.pair_evidence`` output: per pair, the strongest log10 likelihood
    ratio each family contributed. Returns the number of edges written.

    Best-effort by construction. A failure here loses accumulated history, which degrades future
    findings, but must never fail the scan that produced the evidence.
    """
    if not pair_evidence:
        return 0

    written = 0
    for pair, families in sorted(pair_evidence.items()):
        ordered = _ordered(pair[0], pair[1])
        if ordered is None:
            continue
        a, b = ordered
        total = sum(max(0.0, v) for v in families.values())
        if total <= 0:
            continue
        try:
            row = session.execute(
                select(CoordinationEdge).where(
                    CoordinationEdge.platform == platform,
                    CoordinationEdge.account_a == a,
                    CoordinationEdge.account_b == b,
                )
            ).scalar_one_or_none()

            if row is None:
                row = CoordinationEdge(
                    platform=platform, account_a=a, account_b=b,
                    observation_count=0, methods_json=[], mean_cluster_score=0.0,
                    log_lr_sum=0.0, families_json=[], contexts_json=[], platforms_json=[],
                )
                session.add(row)

            contexts = list(row.contexts_json or [])
            is_new_context = bool(context_id) and context_id not in contexts

            # ONLY a genuinely new post adds evidence. A re-scan or a continuation batch over a post
            # already recorded is the same observation arriving twice, and compounding it would let
            # anyone strengthen a finding by pressing rescan.
            if is_new_context:
                if len(contexts) < MAX_CONTEXTS:
                    row.log_lr_sum = min(
                        MAX_CARRIED_LOG10,
                        float(row.log_lr_sum or 0.0) + total * REPEAT_DISCOUNT,
                    )
                contexts.append(context_id)
                row.contexts_json = contexts[:MAX_CONTEXTS + 1]
                row.observation_count = int(row.observation_count or 0) + 1

            fams = set(row.families_json or []) | set(families)
            row.families_json = sorted(fams)
            plats = set(row.platforms_json or []) | {platform}
            row.platforms_json = sorted(plats)
            if context_id:
                row.last_shared_parent = context_id
            written += 1
        except Exception:  # noqa: BLE001 - accumulation must never fail a scan
            logger.warning("coordination graph: could not record %s/%s", a, b, exc_info=True)
    return written


def carried_evidence(
    session,
    *,
    platform: str,
    accounts: list[str],
    exclude_context: str | None = None,
) -> dict[tuple[str, str], float]:
    """Prior cross-scan evidence for every pair among ``accounts``.

    ``exclude_context`` drops history earned on the post currently being analysed, so a re-run of
    the same investigation does not read its own previous output back in as corroboration. Without
    it, running the detector twice on one scan would raise every posterior, which is a feedback loop
    dressed as evidence.
    """
    if len(accounts) < 2:
        return {}
    wanted = set(accounts)
    try:
        rows = session.execute(
            select(CoordinationEdge).where(
                CoordinationEdge.platform == platform,
                CoordinationEdge.account_a.in_(wanted),
                CoordinationEdge.account_b.in_(wanted),
            )
        ).scalars().all()
    except Exception:  # noqa: BLE001
        logger.warning("coordination graph: could not read carried evidence", exc_info=True)
        return {}

    out: dict[tuple[str, str], float] = {}
    for row in rows:
        carried = float(row.log_lr_sum or 0.0)
        if carried <= 0:
            continue
        contexts = list(row.contexts_json or [])
        if exclude_context and contexts and contexts == [exclude_context]:
            # Everything this pair knows came from the post we are looking at right now.
            continue
        if exclude_context and exclude_context in contexts and len(contexts) > 1:
            # Approximate the removal by the share of contexts that are not this one. Exact would
            # need per-context evidence, which is not worth another table for a correction this
            # small.
            carried *= (len(contexts) - 1) / len(contexts)
        pair = _ordered(row.account_a, row.account_b)
        if pair:
            out[pair] = min(MAX_CARRIED_LOG10, carried)
    return out


def pair_history(session, *, platform: str, a: str, b: str) -> dict | None:
    """Everything the deployment knows about one pair, for the admin drill-down."""
    ordered = _ordered(a, b)
    if ordered is None:
        return None
    row = session.execute(
        select(CoordinationEdge).where(
            CoordinationEdge.platform == platform,
            CoordinationEdge.account_a == ordered[0],
            CoordinationEdge.account_b == ordered[1],
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return {
        "account_a": row.account_a,
        "account_b": row.account_b,
        "observation_count": int(row.observation_count or 0),
        "contexts": list(row.contexts_json or []),
        "families": list(row.families_json or []),
        "platforms": list(row.platforms_json or []),
        "carried_log10_lr": round(float(row.log_lr_sum or 0.0), 4),
        "first_observed_at": row.first_observed_at,
        "last_observed_at": row.last_observed_at,
    }
