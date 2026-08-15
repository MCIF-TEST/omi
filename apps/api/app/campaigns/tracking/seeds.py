"""Known real-world operations, ingested as signatures to match against.

Without this, the system can only recognise operations it has personally seen before, so a brand
new deployment knows nothing and a customer's first scan of a documented state operation reports it
as an unremarkable first sighting. Public disclosure archives already describe these operations in
detail; seeding their behavioural signatures means a scan can match against what is publicly known
rather than only against local history.

Two properties that must not drift:

* **A seed has a signature and no live members.** Its accounts were suspended years ago and will
  never appear in a scan. Carrying them as `CampaignMember` rows would make the member-overlap path
  match on accounts that no longer exist while implying this deployment observed them.
* **A seed is never published.** ``origin="disclosure"`` marks it, and nothing mints a share token
  for one. The public claim about these operations belongs to whoever disclosed them.

``app/content/featured_campaigns.json`` already holds two entries produced exactly this way (see
``content/featured.py``), so this generalises an existing path rather than inventing one.
"""

from __future__ import annotations

import json
import logging
import pathlib

from sqlalchemy import select

from app.campaigns.tracking import operations, signature as sig
from app.storage.models import Campaign

logger = logging.getLogger(__name__)

ORIGIN_DISCLOSURE = "disclosure"

#: Where a seed file lives if the operator drops one in. Absent by default, and absence is normal:
#: the real archives are large and are not committed (see CLAUDE.md, "The dataset corpus is not in
#: git"), so this reads whatever is present and does nothing when nothing is.
SEED_PATH = pathlib.Path(__file__).resolve().parents[2] / "content" / "known_operations.json"


def _campaign_key(name: str) -> str:
    import hashlib

    return "seed_" + hashlib.blake2b(name.encode("utf-8"), digest_size=6).hexdigest()


def ingest_seed(session, seed: dict) -> Campaign | None:
    """Create or refresh one known operation.

    ``seed`` needs a ``name`` and enough behaviour to sketch: ``scripts``, ``handles``,
    ``creation_buckets``, ``clients``, ``link_domains``. A seed too thin to sketch is skipped
    rather than stored, because a signature over three tokens matches everything.
    """
    name = str(seed.get("name") or "").strip()
    if not name:
        return None

    built = sig.build_signature(sig.behavioural_tokens(
        scripts=list(seed.get("scripts") or []),
        handles=list(seed.get("handles") or []),
        creation_buckets=list(seed.get("creation_buckets") or []),
        clients=list(seed.get("clients") or []),
        link_domains=list(seed.get("link_domains") or []),
    ))
    if built is None:
        logger.info("seeds: %r has too little behaviour to sign, skipped", name)
        return None
    sketch, keys = built

    key = _campaign_key(name)
    campaign = session.execute(
        select(Campaign).where(Campaign.campaign_key == key)
    ).scalar_one_or_none()
    if campaign is None:
        campaign = Campaign(
            campaign_key=key,
            name=name,
            platform=str(seed.get("platform") or "unknown"),
            coordination_score=0.0, max_coordination_score=0.0, confidence=0.0,
            member_count=0, observation_count=0,
            methods_json=[], hashtags_json=[], mentions_json=[],
            evidence_json=[str(e) for e in (seed.get("evidence") or [])][:8],
            theme=str(seed.get("theme") or "") or None,
            status="known",
        )
        session.add(campaign)
        session.flush()

    campaign.origin = ORIGIN_DISCLOSURE
    campaign.platforms_json = sorted({str(seed.get("platform") or "unknown")})
    operations.store_signature(session, campaign, sketch, keys)
    return campaign


def ingest_file(session, path: pathlib.Path | None = None) -> int:
    """Ingest a seed file if one exists. Returns how many operations were seeded.

    Silent and harmless when the file is absent, which is the normal state.
    """
    path = path or SEED_PATH
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        logger.warning("seeds: could not read %s", path, exc_info=True)
        return 0
    if not isinstance(data, list):
        return 0

    count = 0
    for seed in data:
        if not isinstance(seed, dict):
            continue
        try:
            if ingest_seed(session, seed) is not None:
                count += 1
        except Exception:  # noqa: BLE001 - one bad seed must not lose the rest
            logger.warning("seeds: could not ingest %r", seed.get("name"), exc_info=True)
    if count:
        logger.info("seeds: ingested %d known operation(s)", count)
    return count
