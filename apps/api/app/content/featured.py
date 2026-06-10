"""Featured campaigns — first-run value.

A brand-new user lands on an empty dashboard and has nothing to explore until
they spend a credit. That is the time-to-value gap. To close it WITHOUT the
discredited fake-bot fixtures (see ``seed.py``), we seed a small set of
**real** coordinated campaigns from the platform's own state-actor disclosure
archives (Russia GRU, China Xinjiang), scored by the **real** engine — the
exact ``CampaignService`` path a live scan uses.

The fixture (``featured_campaigns.json``) was generated offline by running the
existing IO-coordination evaluation over the committed disclosure datasets and
capturing the genuine output (real members, methods, evidence, scores). Nothing
here is synthetic and no new intelligence is computed at runtime — this is
durable, real, validated coordination intelligence surfaced for onboarding.

Seeding is idempotent (keyed by ``campaign_key``) and best-effort: a failure
must never break boot. Featured campaigns are public by default (stable token)
so the public report + share surfaces work immediately.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

_FIXTURE = Path(__file__).with_name("featured_campaigns.json")


@lru_cache(maxsize=1)
def featured_definitions() -> list[dict]:
    """The committed real-campaign fixture, or [] if absent/unreadable."""
    try:
        data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:  # noqa: BLE001 — onboarding must never hard-fail
        log.warning("featured fixture unreadable: %s", e)
        return []


def featured_keys() -> list[str]:
    return [d["campaign_key"] for d in featured_definitions()]


def featured_blurbs() -> dict[str, str]:
    return {d["campaign_key"]: d.get("blurb", "") for d in featured_definitions()}


def _stable_token(key: str) -> str:
    # Featured campaigns are meant to be publicly shareable demos, so a stable,
    # guessable token is intentional (not a secret) — it keeps the public URL
    # consistent across re-seeds and environments.
    return f"cmp_{key}"


def seed_featured_campaigns(session: Session) -> int:
    """Idempotently insert the featured campaigns. Returns the number created."""
    from app.storage.models import Campaign, CampaignMember, CampaignObservation

    defs = featured_definitions()
    if not defs:
        return 0
    now = datetime.now(timezone.utc)
    created = 0
    for d in defs:
        key = d["campaign_key"]
        existing = session.execute(
            select(Campaign).where(Campaign.campaign_key == key)
        ).scalar_one_or_none()
        if existing is not None:
            continue  # idempotent
        members = d.get("members", [])
        camp = Campaign(
            campaign_key=key,
            name=d.get("display_name") or key,
            platform=d.get("platform", "x"),
            coordination_score=float(d.get("coordination_score", 0.0)),
            max_coordination_score=float(d.get("coordination_score", 0.0)),
            confidence=float(d.get("confidence", 0.0)),
            member_count=int(d.get("member_count", len(members))),
            observation_count=1,
            methods_json=d.get("methods", []),
            hashtags_json=d.get("hashtags", []),
            mentions_json=d.get("mentions", []),
            evidence_json=d.get("evidence", []),
            theme=d.get("blurb"),
            status="observed",
            share_token=_stable_token(key),
            is_public=1,
            published_at=now,
        )
        session.add(camp)
        session.flush()
        for m in members:
            session.add(CampaignMember(
                campaign_id=camp.id, platform=camp.platform,
                account_external_id=m["account_external_id"],
                handle=m.get("handle"), times_observed=1,
                methods_json=m.get("methods", []),
            ))
        session.add(CampaignObservation(
            campaign_id=camp.id, platform=camp.platform, context_id=key,
            coordination_score=camp.coordination_score, member_count=camp.member_count,
            methods_json=camp.methods_json, evidence_json=camp.evidence_json,
            member_ids_json=[m["account_external_id"] for m in members],
        ))
        created += 1
    return created
