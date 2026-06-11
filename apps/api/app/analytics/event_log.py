"""Founder-learning event recorder (master-plan Phase 4).

One function: :func:`record`. Five questions; five event kinds; per-kind
payload whitelists enforced HERE so nothing surveillance-shaped can ever be
written, even by a careless caller — no IP, no user agent, no fingerprint,
no session ids, no free-form payloads (the single free-text field, the
willingness-to-pay answer, is explicitly capped).

Best-effort by contract: recording runs inside a SAVEPOINT on the caller's
session and swallows every failure — a learning write must never break or
taint a product request (platform skill §4).
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# kind -> allowed payload keys. Anything not listed is dropped before write.
EVENT_KINDS: dict[str, frozenset[str]] = {
    # Q1 — did the user experience value? (diagnostic: reached the featured
    # value surface; the activation itself is export/share/scan.)
    "featured_viewed": frozenset({"campaign_key", "ref"}),
    # Q1 — value artifact left the app.
    "campaign_export": frozenset({"campaign_key", "format"}),
    # Q3 — per-user share attribution (Campaign rows are global: no user_id).
    "campaign_share_minted": frozenset({"campaign_key"}),
    # Q3 — was a shared link actually read. Anonymous: user_id stays NULL.
    "public_report_view": frozenset({"token", "report_kind"}),
    # Q5 — the founder's qualitative pricing signal, one per user.
    "wtp_answer": frozenset({"text"}),
    "wtp_dismissed": frozenset(),
}

_WTP_TEXT_CAP = 2000


def record(
    session: Session,
    kind: str,
    *,
    user_id: int | None = None,
    **payload: object,
) -> None:
    """Best-effort, whitelist-filtered event write on the caller's session."""
    allowed = EVENT_KINDS.get(kind)
    if allowed is None:
        log.warning("event_log: unknown kind %r dropped", kind)
        return
    clean: dict[str, object] = {}
    for k, v in payload.items():
        if k not in allowed or v is None:
            continue
        if k == "text":
            v = str(v).strip()[:_WTP_TEXT_CAP]
            if not v:
                continue
        clean[k] = v
    try:
        from app.storage.models import EventLog

        with session.begin_nested():
            session.add(EventLog(
                kind=kind,
                user_id=(user_id or None),  # 0 = local/no-auth mode -> NULL
                payload_json=clean,
            ))
    except Exception as e:  # noqa: BLE001 — learning must never break a request
        log.debug("event_log: dropped %s (%s)", kind, e)


def record_public_view(token: str, report_kind: str, *, ip: str) -> None:
    """Dedup-and-record a public report view (Q3: were shared links read).

    One view per (report_kind, token, ip) per 10 minutes so refreshes and
    scrapers don't inflate the share-read metric while distinct viewers still
    count. The dedup key lives in the in-memory TTL cache and the IP is HASHED
    for it — no IP is ever persisted, consistent with the privacy contract.
    Best-effort: never raises into the request path.
    """
    try:
        from app.core.cache import get_cache
        from app.core.ip import hash_ip
        from app.storage.db import get_session

        cache = get_cache()
        key = f"prv:{report_kind}:{token}:{hash_ip(ip)}"
        if cache.get(key) is not None:
            return
        cache.set(key, 1, ttl_seconds=600)
        with get_session() as session:
            record(session, "public_report_view", token=token, report_kind=report_kind)
    except Exception as e:  # noqa: BLE001
        log.debug("event_log: public view dropped (%s)", e)
