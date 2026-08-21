"""Admin surface for the coordinated-network detector: /v1/admin/netdetect/*.

Admin-only, and for the same reason `/campaigns` and `/narratives` are: this reports groups of
NAMED REAL PEOPLE as running together, on evidence that is statistical rather than certain. It is an
operator's lead, not a customer-facing verdict, and it stays that way until the dilution curve and
the adjudication layer say otherwise.

Deliberately read-only and stateless. Nothing here persists a finding or mints a share token,
because a claim this system makes about a person should be a decision somebody took, never a side
effect of a page being loaded.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.core.auth import CurrentUser, require_user
from app.netdetect import detect_from_commenters
from app.netdetect.shuffle import DEFAULT_SHUFFLES
from app.storage.db import get_session
from app.storage.models import Investigation

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
    evidence: list[EvidenceOut]


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


@admin_router.post("/{slug}", response_model=RunOut)
def run_on_investigation(
    slug: str,
    shuffles: int = Query(DEFAULT_SHUFFLES, ge=1, le=200),
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

    handles = {str(r.get("external_id")): str(r.get("handle") or "") for r in rows}
    return RunOut(
        slug=slug,
        corpus_size=result.corpus_size,
        rare_features=result.rare_features,
        null_shuffles=result.null_shuffles,
        null_threshold=result.null_threshold,
        rejected=len(result.rejected),
        refused=result.refused,
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
                evidence=[
                    EvidenceOut(
                        family=e.feature.family, kind=e.feature.kind,
                        shared_by=e.shared_by, corpus_count=e.corpus_count,
                        surprise=round(e.surprise, 3), sentence=e.sentence,
                    )
                    for e in c.evidence[:25]
                ],
            )
            for c in result.findings
        ],
    )
