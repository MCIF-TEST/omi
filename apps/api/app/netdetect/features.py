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
    FAMILY_NARRATIVE,
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


#: An @mention, lowercased, without the sigil. Handles are 1-15 alphanumerics/underscore on X and
#: similar elsewhere; the leading boundary stops an email address being read as a mention.
_MENTION_RE = re.compile(r"(?:^|[^\w@])@([A-Za-z0-9_]{2,30})\b")

#: A hashtag. Requires a letter somewhere so "#1" and "#2026" are not tags, and allows the digits
#: real campaign tags carry ("#budget2026").
_HASHTAG_RE = re.compile(r"(?:^|[^\w#])#([A-Za-z0-9_]*[A-Za-z][A-Za-z0-9_]*)\b")

#: Mentions kept per account, sampled deterministically. An account that @s hundreds of people is
#: usually a reply-guy rather than an operation, and letting it contribute hundreds of features
#: would skew the degree sequence the null holds fixed.
MAX_MENTIONS_PER_ACCOUNT = 40


def mentions_in(texts: Iterable[str]) -> set[str]:
    """Lowercased handles mentioned across these texts."""
    out: set[str] = set()
    for t in texts:
        if not t:
            continue
        out.update(m.lower() for m in _MENTION_RE.findall(t))
    return out


def hashtags_in(texts: Iterable[str]) -> set[str]:
    """Lowercased hashtags across these texts."""
    out: set[str] = set()
    for t in texts:
        if not t:
            continue
        out.update(h.lower() for h in _HASHTAG_RE.findall(t))
    return out


def network_features(
    parents: Iterable[str | None],
    reply_targets: Iterable[str | None],
    *,
    exclude: set[str],
    reposts: Iterable[str | None] = (),
) -> set[Feature]:
    """What the account engaged with.

    ``exclude`` carries the scanned post's own ids. EVERY commenter shares those by construction, so
    counting them would hand a perfect feature to every account in the investigation and report the
    comment section as one enormous operation. This is the same reasoning as the older detector's
    "a distinct post" rule, and it is the single most important exclusion in this file.

    REPOSTS ARE THE THIRD KIND OF ENGAGEMENT, and they were being dropped. The scan has always
    collected ``repost_of_id`` and the cohort detector has always used it; this reader took only
    parents and replies, so an operation whose members amplify the same outside post left no
    network evidence at all. That is the family weighted 1.00 and one of the two whose sharing is
    implausibly innocent, so losing it is losing the difference between a publishable finding and
    one that needs a human.

    A repost is if anything the CLEANEST of the three. A reply can be an argument and a parent can
    be a thread somebody wandered into, but choosing to rebroadcast a specific post is an act of
    amplification, which is what an operation is for.

    The other half of this rule is in ``significance.score_candidate``, which drops a network
    feature whose target is itself a member of the group: rebroadcasting each other is a community
    talking, not a formation converging on an outside target. ``repost_of`` is named there alongside
    ``reply_to`` and ``target_post`` for exactly that reason.
    """
    out: set[Feature] = set()
    for p in parents:
        if p and p not in exclude:
            out.add(Feature(FAMILY_NETWORK, "target_post", str(p)))
    for r in reply_targets:
        if r and r not in exclude:
            out.add(Feature(FAMILY_NETWORK, "reply_to", str(r)))
    for rp in reposts:
        # Kept in its OWN kind rather than folded into `target_post`. Two accounts that both
        # reposted X and two accounts that both replied under X are different claims, and the
        # evidence sentence a reader sees has to be able to say which.
        if rp and rp not in exclude:
            out.add(Feature(FAMILY_NETWORK, "repost_of", str(rp)))
    return out



def subject_features(texts: Iterable[str], *, exclude: set[str]) -> set[Feature]:
    """WHO the account talks about and WHAT TAG it posts under. Both narrative, and neither hard.

    ---------------------------------------------------------------------------------------------
    A MENTION IS NOT A REPOST, AND MEASURING THAT SAVED A FALSE POSITIVE
    ---------------------------------------------------------------------------------------------

    Mentions were first written into ``network_features`` beside ``reply_to`` / ``target_post`` /
    ``repost_of``, on the reasoning that converging on an outside target is the operator's own act.
    `network` is weighted 1.00 and sits in ``HARD_FAMILIES``, so that made a shared @ enough to
    clear ``MIN_HARD_EVIDENCE``.

    Measured immediately, the professional-beat control went from flagged-for-adjudication to
    **publishable**: hard evidence 7.50 against a floor of 3.0, on the strength of ten reporters
    all naming ``@stadiumauthority``. That is the exact accusation about real journalists this
    package exists to refuse, and no threshold anywhere would have caught it, because the finding
    was statistically real.

    The modelling error is the interesting part. A repost or a reply target is a STRUCTURAL act the
    platform recorded: an account chose to rebroadcast a specific post. A mention is a NAME INSIDE
    A SENTENCE. Reporters on a beat name the officials on that beat, fans name the artist, and
    critics name the person they are criticising. Naming somebody is about SUBJECT, which is what
    NARRATIVE means, and narrative is weighted 0.45 and deliberately not hard for exactly this
    reason.

    ---------------------------------------------------------------------------------------------
    WHY THIS FAMILY WAS EMPTY UNTIL NOW
    ---------------------------------------------------------------------------------------------

    ``topic_features`` below is the only other thing that fills ``FAMILY_NARRATIVE``, and only the
    cross-investigation pass can call it, because only that pass has embedded anything. So an
    ordinary scan ran with five families while ``MIN_FAMILIES`` counts families, and the weight map
    has carried ``narrative`` since the module was written.

    Mentions and tags fill it with no model, no network call and no vendor. They are also the only
    handle this package has on "what are these accounts talking about" that survives paraphrase:
    two accounts pushing one tag in completely different sentences share no shingle at all.

    Deliberately NOT the text family. Text means "these accounts emitted the same string" and its
    job is catching copy-paste; folding a tag in there would let one shared tag stand in for the
    copy-paste evidence that family is weighted for.

    ``exclude`` carries anything the group was SELECTED by, the same rule as the scanned post in
    ``network_features``: whatever you assembled the group by cannot also be evidence about it.
    """
    out: set[Feature] = set()
    texts = list(texts)
    for tag in hashtags_in(texts):
        if tag and tag not in exclude:
            out.add(Feature(FAMILY_NARRATIVE, "hashtag", tag))
    # Sampled so a reply-guy who names hundreds of accounts cannot contribute hundreds of features
    # and skew the degree sequence the null holds fixed.
    for handle in _stable_sample(sorted(mentions_in(texts)), MAX_MENTIONS_PER_ACCOUNT):
        if handle and handle not in exclude:
            out.add(Feature(FAMILY_NARRATIVE, "mentions", handle))
    return out


def topic_features(
    topic_ids: Iterable[object],
    *,
    exclude: set[str],
) -> set[Feature]:
    """Which emergent topics the account has spoken on.

    THE FAMILY THIS FILLS WAS DECLARED AND EMPTY. ``FAMILY_NARRATIVE`` has been in the weight map
    at 0.45 since the module was written, with a comment saying "once real embeddings land". They
    landed, so this is that.

    Topic ids are PASSED IN, never computed here, and that is deliberate rather than lazy. This
    package is pure and offline: no model call, no network, no provider quota. An embedder inside
    the detector would put a paid network call on a path that runs inside a scan and would make the
    same corpus score differently depending on whether a vendor answered. The cross-investigation
    pass has already embedded and assigned; it hands the answers over.

    ``exclude`` carries the topic the cohort was assembled ON. Every member spoke on it by
    construction, so counting it would hand a perfect feature to the whole cohort and report the
    topic's whole population as one operation. This is the same trap as the scanned post in
    ``network_features``, and it is worth stating twice because the shape recurs: whatever you
    selected the group BY cannot also be evidence about the group.

    What survives the exclusion is the interesting part: not "these accounts talked about water",
    which is why they were assembled, but "these accounts ALSO co-occur on three unrelated
    subjects". Weighted soft on purpose, because a shared topic is the most innocently shared thing
    there is, so this can add to convergence and can never carry a finding alone.
    """
    out: set[Feature] = set()
    for tid in topic_ids:
        if tid is None:
            continue
        token = str(tid)
        if not token or token in exclude:
            continue
        out.add(Feature(FAMILY_NARRATIVE, "topic", token))
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


def profile_from_commenter(
    row: dict,
    *,
    exclude_context: set[str] | None = None,
    topic_ids: Iterable[object] = (),
    exclude_topics: set[str] | None = None,
) -> AccountProfile:
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
        reposts=(i.get("repost_of_id") for i in all_items),
    )
    feats |= infrastructure_features((i.get("source_client") for i in all_items), texts)
    feats |= identity_features(_parse_ts(row.get("account_created_at")), row.get("handle"))
    # The narrative family, on the per-scan path, from what the account NAMES and TAGS rather than
    # from embeddings. It used to be empty here: `topic_features` needs assignments only the
    # cross-investigation pass produces, so an ordinary scan ran with five families while
    # `MIN_FAMILIES` counts families.
    #
    # `exclude` is passed as well as `exclude_topics`, because it carries the scanned post's ids and
    # a mention or tag matching one of them is the same self-referential trap.
    feats |= subject_features(texts, exclude=set(exclude_topics or ()) | exclude)
    feats |= topic_features(topic_ids, exclude=set(exclude_topics or ()))

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
