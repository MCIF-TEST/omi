"""Running the detector: pure detection, then the two scheduled entry points.

`detect` is the single scoring core. Both passes call it, which is what stops them disagreeing.
"""

from __future__ import annotations

import logging

from app.campaigns.detector import cohort as cohort_mod
from app.campaigns.detector import fuse
from app.campaigns.detector.signals import SIGNALS
from app.campaigns.detector.types import (
    THRESHOLDS_VERSION,
    Cohort,
    DetectionRun,
    Edge,
)

logger = logging.getLogger(__name__)

#: Above this many cohort members, skip the O(n^2) pair signals and note why. The 70+ cohort is
#: small by construction (a 150-account scan rarely puts more than a couple of dozen accounts over
#: 70), so this exists only so a pathological batch cannot pin a worker.
MAX_COHORT = 400


def detect(
    cohort: Cohort,
    *,
    passes: int = 1,
    inherited_edges: list[Edge] | None = None,
    accumulated: dict[tuple[str, str], float] | None = None,
) -> DetectionRun:
    """Every signal, then fusion, clustering and the gates.

    ``inherited_edges`` carries pass 1's findings into pass 2. Timing evidence in particular cannot
    be recomputed after the scan, because the full comment stream (including authors who were never
    scored) only exists in memory during the scan. Recomputing it from the persisted payload would
    measure the arrival rate over a subset and therefore over-state significance, so pass 2 inherits
    those edges rather than inventing weaker ones.
    """
    notes: list[str] = []
    accounts = cohort.accounts
    if len(accounts) > MAX_COHORT:
        notes.append(
            f"Cohort truncated to the {MAX_COHORT} highest-scoring accounts "
            f"of {len(accounts)}."
        )
        accounts = sorted(accounts, key=lambda a: -a.score)[:MAX_COHORT]
        cohort = Cohort(
            accounts=sorted(accounts, key=lambda a: a.external_id),
            background=cohort.background,
            platform=cohort.platform,
            score_source=cohort.score_source,
            score_threshold=cohort.score_threshold,
        )

    edges: list[Edge] = list(inherited_edges or [])
    if len(cohort.accounts) >= 2:
        for signal in SIGNALS:
            try:
                edges.extend(signal(cohort))
            except Exception:  # noqa: BLE001 - one broken signal must not lose the others
                logger.exception(
                    "campaign detector: signal %s failed", getattr(signal, "__name__", "?"),
                )
                notes.append(f"Signal {getattr(signal, '__name__', '?')} failed and was skipped.")
    else:
        notes.append("Fewer than two accounts scored at or above the threshold.")

    # A platform-specific family may not link accounts on two different platforms. Applied once,
    # here, rather than inside seven signals that would each have to remember it.
    edges = _drop_illegal_cross_platform(edges, cohort)

    ids = [a.external_id for a in cohort.accounts]
    findings = fuse.build_findings(ids, edges, accumulated=accumulated)
    for f in findings:
        f.evidence = _evidence_lines(f)

    return DetectionRun(
        findings=findings,
        cohort_size=len(cohort.accounts),
        scanned_total=cohort.background.scanned_total,
        score_source=cohort.score_source,
        platform=cohort.platform,
        passes=passes,
        thresholds_version=THRESHOLDS_VERSION,
        lone_high_scorers=fuse.lone_high_scorers(ids, edges),
        notes=notes,
    )


def _drop_illegal_cross_platform(edges: list[Edge], cohort: Cohort) -> list[Edge]:
    """Enforce the cross-platform rule. See ``tracking/crossplatform.py`` for why it is this one."""
    try:
        from app.campaigns.tracking.crossplatform import may_link, split_key

        platforms = {a.external_id: split_key(a.external_id)[0] for a in cohort.accounts}
        default = cohort.platform or "unknown"

        def platform_of(account_id: str) -> str:
            found = platforms.get(account_id, "unknown")
            return default if found == "unknown" else found

        return [e for e in edges if may_link(platform_of(e.a), platform_of(e.b), e.family)]
    except Exception:  # noqa: BLE001 - a filter that fails must not lose the evidence
        logger.warning("campaign detector: cross-platform filter failed", exc_info=True)
        return edges


def _carried_evidence(session, platform: str, cohort: Cohort, context_id: str | None):
    """Prior cross-scan evidence for this cohort's pairs, or nothing if the lookup fails."""
    try:
        from app.campaigns.tracking import graph

        return graph.carried_evidence(
            session,
            platform=platform,
            accounts=[a.external_id for a in cohort.accounts],
            exclude_context=context_id,
        )
    except Exception:  # noqa: BLE001 - history is an enhancement, never a precondition
        logger.warning("campaign detector: could not load carried evidence", exc_info=True)
        return {}


#: How many evidence sentences to render per finding. The raw edges are all persisted; this is the
#: readable summary.
MAX_EVIDENCE_LINES = 12


def _evidence_lines(finding) -> list[str]:
    """One sentence per distinct claim, strongest first, deduplicated.

    Several signals emit the same sentence across every pair in a group (a burst of six accounts
    produces fifteen identical edges). Repeating it fifteen times would read as fifteen findings.
    """
    seen: set[str] = set()
    out: list[str] = []
    for e in finding.edges:
        if e.sentence in seen:
            continue
        seen.add(e.sentence)
        out.append(e.sentence)
        if len(out) >= MAX_EVIDENCE_LINES:
            break
    return out


# ---------------------------------------------------------------------------------------------
# The one scheduled job. Both passes are this function; only `prefer` differs.
# ---------------------------------------------------------------------------------------------
def detect_for_investigation(
    slug: str,
    user_id: int | None,
    prefer: str = cohort_mod.SOURCE_ANALYST,
) -> DetectionRun | None:
    """Run the detector over a persisted investigation and republish the result.

    Pass 1 (``prefer="engine"``) fires when the scan is saved, on the deterministic engine
    probability, so a coordination finding exists even when the analyst is unreachable, which is a
    documented recurring failure. Pass 2 (``prefer="analyst"``) fires when the assessment lands and
    re-cuts the cohort on the customer-visible OMI score.

    There is one stored result, not two. Pass 2 overwrites pass 1's block rather than sitting
    beside it, and both go through the same ``detect`` core, so the two passes cannot present
    competing verdicts about the same accounts.

    Never raises. It runs on the background pool, where an exception becomes a Sentry event and
    nothing else, and a coordination refinement is never worth risking an investigation over.
    """
    from app.campaigns.detector import persist
    from app.storage.db import get_session
    from app.storage.repository import AccountRepository

    try:
        with get_session() as session:
            inv = AccountRepository(session).get_investigation(slug=slug, user_id=user_id)
            if inv is None:
                return None
            payload = dict(inv.payload_json or {})
            if not payload:
                return None

            if prefer == cohort_mod.SOURCE_ANALYST and not cohort_mod.analyst_scores(payload):
                # Nothing to refine with. Pass 1's result already stands, and re-running it on
                # engine scores would only reproduce it while overwriting its timestamp.
                return None

            cohort_mod.backfill_thread_comments(session, inv, payload)
            previous = persist.stored_run(payload)
            inherited = persist.inherited_timing_edges(previous)

            platform = str(getattr(inv, "platform", "") or payload.get("platform") or "unknown")
            c = cohort_mod.from_payload(payload, platform=platform, prefer=prefer)

            # What the deployment already knows about these pairs from OTHER posts. This is what
            # makes a pair that was merely suspicious here decisive when it has been seen before,
            # and it is the only reason tracking globally improves accuracy rather than just
            # storage. The current post is excluded so a re-run cannot read its own output back in.
            carried = _carried_evidence(
                session, platform, c, str(getattr(inv, "target_id", "") or "") or None,
            )

            run = detect(
                c,
                passes=2 if prefer == cohort_mod.SOURCE_ANALYST else 1,
                inherited_edges=inherited,
                accumulated=carried,
            )
            persist.save(session, inv, run, cohort=c)
            return run
    except Exception:  # noqa: BLE001
        logger.exception("campaign detector: run failed for slug=%s prefer=%s", slug, prefer)
        return None


def schedule(slug: str, user_id: int | None, prefer: str = cohort_mod.SOURCE_ANALYST) -> bool:
    """Queue a run on the shared background pool.

    ``submit`` and not ``submit_slow``: the slow pool exists because an analyst run holds a worker
    for minutes, and taking one of those for a few seconds of pure CPU would delay the analyst runs
    queued behind it.
    """
    try:
        from app.core import background

        background.submit(detect_for_investigation, slug, user_id, prefer)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("campaign detector: could not schedule a run for slug=%s", slug)
        return False
