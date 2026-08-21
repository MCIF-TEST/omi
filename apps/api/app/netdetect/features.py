"""Turning an account into features.

This file is where most of the false positives in a detector like this are either created or
prevented, so nearly every function here is shaped by a way of being wrong.

THE THREE RULES

1. **A feature must be something an account CHOSE.** The scanned post is shared by every commenter
   by construction, so it is not evidence of anything and is excluded by name. The same goes for a
   platform's own templated text.

2. **Deduplicate within an account before counting.** An account that used a phrase forty times
   supplies one observation of that phrase, not forty. Without this a single prolific account
   dominates every statistic downstream.

3. **Bucket continuous quantities coarsely, then let rarity decide.** A creation *week* is a real
   coincidence; a creation *second* is a spurious one that would look infinitely rare. The bucket
   width is a prior about what a coincidence means, and it belongs here rather than in the scorer.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable

from app.netdetect.types import (
    FAMILY_IDENTITY,
    FAMILY_INFRASTRUCTURE,
    FAMILY_NETWORK,
    FAMILY_TEXT,
    FAMILY_TIMING,
    AccountProfile,
    Feature,
)

# --------------------------------------------------------------------------------------------- #
# Tunables. Each is a decision about what counts as a coincidence.
# --------------------------------------------------------------------------------------------- #

#: Words per text shingle. Five is long enough that a shared shingle is not ordinary English and
#: short enough to survive light spinning ("great video" vs "this is a really great video here").
SHINGLE_N = 5

#: Most shingles kept per account. A long history would otherwise contribute thousands of features
#: and dominate the degree sequence. Sampled deterministically by hash so the choice is stable
#: across runs, which matters because a verdict that changes between runs is not a verdict.
MAX_SHINGLES_PER_ACCOUNT = 120

#: Ceiling on features from one account across all families, applied last. A pathological history
#: cannot be allowed to pin a worker or skew the null.
MAX_FEATURES_PER_ACCOUNT = 400

#: Inter-post gaps are bucketed on a log scale: the difference between 60s and 70s is noise, the
#: difference between 60s and 6000s is a different machine. Base-2 log buckets.
GAP_LOG_BASE = 2.0

#: Posting-hour features use the account's ACTIVE HOUR SET, not individual timestamps. Two accounts
#: posting at 14:03 and 14:47 on unrelated days is not a coincidence; two accounts that are both
#: active in exactly the same eight hours of the day and silent in the other sixteen is.
MIN_POSTS_FOR_HOUR_PROFILE = 10

#: Creation-time bucket. A week is the resolution at which "provisioned together" is a real claim.
CREATION_BUCKET_DAYS = 7

_WORD_RE = re.compile(r"[a-z0-9']+")
_URL_RE = re.compile(r"https?://([^\s/]+)", re.I)
_DIGITS_RE = re.compile(r"\d+")

#: Text a PLATFORM generates, which clusters perfectly and means nothing. Rarity would eventually
#: learn these are common, but only once the corpus is large; until then they are the most likely
#: source of a confident false positive, so they are named.
_PLATFORM_BOILERPLATE = (
    "i just earned", "i just unlocked", "check out my", "i just got",
    "shared via", "posted via", "automatically generated", "this tweet is unavailable",
    "sent from my", "watch this video", "subscribe to my channel",
)


def _norm_words(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").lower())


def _is_boilerplate(text: str) -> bool:
    low = (text or "").lower()
    return any(b in low for b in _PLATFORM_BOILERPLATE)


def _stable_sample(items: list[str], limit: int) -> list[str]:
    """Keep at most ``limit`` items, chosen by hash rather than by position.

    Deterministic on purpose. Truncating to the first N would bias toward whatever order the
    provider returned, and sampling randomly would make the same input produce different findings on
    different runs. These are published claims about named people; the verdict has to be a function
    of the evidence alone.
    """
    if len(items) <= limit:
        return items
    scored = sorted(items, key=lambda s: hashlib.blake2b(s.encode(), digest_size=8).digest())
    return scored[:limit]


# --------------------------------------------------------------------------------------------- #
# Per-family extractors
# --------------------------------------------------------------------------------------------- #

def text_features(texts: Iterable[str]) -> set[Feature]:
    """Word-shingles of what the account wrote, plus its own repeated-line habit.

    Deduplicated across the account's whole history before anything is counted, so one copy-pasted
    post does not become forty observations.
    """
    shingles: set[str] = set()
    for t in texts:
        if not t or _is_boilerplate(t):
            continue
        w = _norm_words(t)
        if len(w) < SHINGLE_N:
            continue
        for i in range(len(w) - SHINGLE_N + 1):
            shingles.add(" ".join(w[i:i + SHINGLE_N]))

    kept = _stable_sample(sorted(shingles), MAX_SHINGLES_PER_ACCOUNT)
    return {Feature(FAMILY_TEXT, "shingle", s) for s in kept}


def bio_features(bio: str | None) -> set[Feature]:
    """Shingles of the profile text.

    A bio is written once and rarely changed, so a shared bio phrase is a stronger coincidence than
    a shared post phrase. It is still the TEXT family: both are "these accounts emitted the same
    string", and counting them as independent would let one copy-paste clear a bar meant to need two
    separate kinds of evidence.
    """
    if not bio or _is_boilerplate(bio):
        return set()
    w = _norm_words(bio)
    if len(w) < 3:
        return set()
    n = min(SHINGLE_N, len(w))
    return {
        Feature(FAMILY_TEXT, "bio_shingle", " ".join(w[i:i + n]))
        for i in range(len(w) - n + 1)
    }


def timing_features(timestamps: list[datetime]) -> set[Feature]:
    """When the account acts, as coincidences rather than as instants.

    Three shapes, each a different claim:

    * **gap class** — the log-bucketed interval between consecutive posts. A scheduler produces one
      dominant class; a person produces a spread.
    * **active-hour set** — which hours of the day the account uses at all. This is the strongest of
      the three because it is a fingerprint of a *routine*, and it needs enough posts to be real
      (``MIN_POSTS_FOR_HOUR_PROFILE``) or a handful of posts would manufacture one.
    * **quiet signature** — the longest daily silence, bucketed. Humans sleep. An account with no
      multi-hour quiet period is either automated or shared, and a *shared* quiet window across
      accounts is a coincidence about their operators' working day.
    """
    ts = sorted(t for t in timestamps if t is not None)
    if len(ts) < 3:
        return set()

    out: set[Feature] = set()

    gaps = [(b - a).total_seconds() for a, b in zip(ts, ts[1:]) if (b - a).total_seconds() > 0]
    if gaps:
        classes = Counter()
        for g in gaps:
            bucket = int(_log_bucket(g))
            classes[bucket] += 1
        # Only the account's DOMINANT rhythm. Every account has some short gaps and some long ones;
        # what identifies it is the one it does most.
        top, count = classes.most_common(1)[0]
        if count >= max(2, len(gaps) // 4):
            out.add(Feature(FAMILY_TIMING, "gap_class", str(top)))

    if len(ts) >= MIN_POSTS_FOR_HOUR_PROFILE:
        hours = sorted({t.astimezone(timezone.utc).hour for t in ts})
        out.add(Feature(FAMILY_TIMING, "active_hours", ",".join(str(h) for h in hours)))

        quiet = _longest_daily_quiet_hours(ts)
        if quiet is not None:
            out.add(Feature(FAMILY_TIMING, "quiet_hours", str(int(quiet))))

    return out


def _log_bucket(seconds: float) -> float:
    import math

    return math.floor(math.log(max(1.0, seconds), GAP_LOG_BASE))


def _longest_daily_quiet_hours(ts: list[datetime]) -> float | None:
    """Longest stretch of the 24-hour clock the account never uses, in whole hours."""
    hours = {t.astimezone(timezone.utc).hour for t in ts}
    if not hours or len(hours) >= 24:
        return 0.0
    best = run = 0
    # Two laps so a quiet stretch spanning midnight is measured as one run rather than two.
    for h in list(range(24)) * 2:
        if h in hours:
            run = 0
        else:
            run += 1
            best = max(best, run)
    return float(min(best, 24))


def network_features(
    parents: Iterable[str | None],
    reply_targets: Iterable[str | None],
    *,
    exclude: set[str],
) -> set[Feature]:
    """What the account engaged with.

    ``exclude`` carries the scanned post's own ids. EVERY commenter shares those by construction, so
    counting them would hand a perfect feature to every account in the investigation and report the
    comment section as one enormous operation. This is the same reasoning as the older detector's
    "a distinct post" rule, and it is the single most important exclusion in this file.
    """
    out: set[Feature] = set()
    for p in parents:
        if p and p not in exclude:
            out.add(Feature(FAMILY_NETWORK, "target_post", str(p)))
    for r in reply_targets:
        if r and r not in exclude:
            out.add(Feature(FAMILY_NETWORK, "reply_to", str(r)))
    return out


def infrastructure_features(clients: Iterable[str | None], texts: Iterable[str]) -> set[Feature]:
    """What the account publishes with, and where it points.

    A shared third-party scheduler is infrastructure rather than style, and a shared link domain is
    what an operation is usually FOR. Both are only available on some platforms, and going silent
    where they are absent is correct behaviour rather than a gap to fill.
    """
    out: set[Feature] = set()
    for c in clients:
        c = (c or "").strip()
        if c:
            out.add(Feature(FAMILY_INFRASTRUCTURE, "client", c.lower()))
    for t in texts:
        for host in _URL_RE.findall(t or ""):
            host = host.lower().lstrip("www.")
            if host:
                out.add(Feature(FAMILY_INFRASTRUCTURE, "link_domain", host))
    return out


def identity_features(created_at: datetime | None, handle: str | None) -> set[Feature]:
    """How the account itself was made.

    The handle SKELETON, never the handle: letters collapse to a run marker and digits to a count,
    so ``crypto_mike_8821`` and ``crypto_dave_4417`` share a template. Two guards, both from
    mistakes this class of signal has already made elsewhere in the codebase:

    * a bare single-word skeleton is refused. Letter runs cap at 9, so ``marchingfern``,
      ``quietwaterbird`` and ``brightpennylane`` all reduce to ``L9`` and would be reported as
      sharing a template when they share nothing.
    * the platform's OWN auto-append shape (a word followed by digits) is the default handle a
      platform hands out when the one you asked for is taken. It is a fact about the platform.
    """
    out: set[Feature] = set()

    if created_at is not None:
        epoch_days = int(created_at.timestamp() // 86400)
        bucket = epoch_days // CREATION_BUCKET_DAYS
        out.add(Feature(FAMILY_IDENTITY, "creation_week", str(bucket)))

    skel = handle_skeleton(handle)
    if skel:
        out.add(Feature(FAMILY_IDENTITY, "handle_template", skel))
    return out


def handle_skeleton(handle: str | None) -> str | None:
    """``crypto_mike_8821`` -> ``L6_L4_D4``. None when the shape is not a template."""
    h = (handle or "").strip().lstrip("@")
    if not h:
        return None
    parts = re.split(r"[._\-]+", h)
    shape: list[str] = []
    for p in parts:
        if not p:
            continue
        if p.isdigit():
            shape.append(f"D{len(p)}")
        else:
            letters = len(_DIGITS_RE.sub("", p))
            digits = len(p) - letters
            token = f"L{min(letters, 9)}"
            if digits:
                token += f"D{digits}"
            shape.append(token)
    if len(shape) < 2:
        # One part is not a template. See the docstring.
        return None
    if len(shape) == 2 and shape[0].startswith("L") and shape[1].startswith("D"):
        # word + digits is the platform's own auto-append, not the operator's convention.
        return None
    return "_".join(shape)


# --------------------------------------------------------------------------------------------- #
# The account
# --------------------------------------------------------------------------------------------- #

def _parse_ts(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if not isinstance(raw, str) or not raw:
        return None
    try:
        d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def profile_from_commenter(row: dict, *, exclude_context: set[str] | None = None) -> AccountProfile:
    """Build one account's feature bag from a persisted ``CommenterScanResult`` dict.

    Reads only fields the scan already stores. Anything absent simply produces fewer features, which
    is the honest outcome: an account we know less about is one we can say less about, and inventing
    a feature to fill the gap is how a detector starts reporting its own defaults as coincidences.
    """
    exclude = set(exclude_context or ())

    activity = [a for a in (row.get("recent_activity") or []) if isinstance(a, dict)]
    thread = [c for c in (row.get("thread_comments") or []) if isinstance(c, dict)]
    all_items = activity + thread

    texts = [str(i.get("text") or "") for i in all_items]
    stamps = [t for t in (_parse_ts(i.get("created_at")) for i in all_items) if t is not None]

    feats: set[Feature] = set()
    feats |= text_features(texts)
    feats |= bio_features(row.get("bio"))
    feats |= timing_features(stamps)
    feats |= network_features(
        (i.get("parent_id") for i in activity),
        (i.get("reply_to_id") for i in all_items),
        exclude=exclude,
    )
    feats |= infrastructure_features((i.get("source_client") for i in all_items), texts)
    feats |= identity_features(_parse_ts(row.get("account_created_at")), row.get("handle"))

    if len(feats) > MAX_FEATURES_PER_ACCOUNT:
        ordered = sorted(feats, key=lambda f: hashlib.blake2b(
            f.token().encode(), digest_size=8).digest())
        feats = set(ordered[:MAX_FEATURES_PER_ACCOUNT])

    return AccountProfile(
        external_id=str(row.get("external_id") or ""),
        platform=str(row.get("platform") or "unknown"),
        features=feats,
        handle=str(row.get("handle") or ""),
        score=row.get("omi_score") if isinstance(row.get("omi_score"), (int, float))
        else row.get("overall_probability"),
        tier=row.get("tier"),
    )
