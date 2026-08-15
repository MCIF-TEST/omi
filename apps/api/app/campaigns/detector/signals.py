"""The seven signals.

Each is a pure function taking the cohort plus the batch background and returning ``Edge`` records.
No I/O, no model call, no provider fetch. Every one carries an artifact the accounts themselves
produced.

Read the "REFUSES" line on each signal before changing its thresholds. Those are the documented
confusable shapes from the constitution (`_CONFUSABLE_ACCOUNTS`) promoted from prompt text into
code, and each one is pinned by a test. A signal that starts firing on its refusal case is wrong
even if it also catches more real campaigns, because a false positive here names a real person as
part of an operation.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime, timezone

from app.campaigns.detector import stats, textsim
from app.campaigns.detector.types import BatchBackground, Cohort, CohortAccount, Edge

# =============================================================================================
# Family TEXT
# =============================================================================================
#: A string repeated by more than this share of the thread's authors is a meme or a copypasta,
#: not a script handed to a group. Drawn from the FULL thread, cohort and non-cohort alike.
MAX_COPYPASTA_AUTHOR_SHARE = 0.25
ECHO_JACCARD = 0.80
BIO_ECHO_JACCARD = 0.85
MIN_BIO_CHARS = 30

#: Bios that are a platform default or a universal one-liner. Matching on these says nothing.
_BIO_DENYLIST = {
    "", "n/a", "na", "none", "no bio", "bio", "hi", "hello", "hey",
    "follow me", "follow back", "dm for promo", "link in bio",
    "just here", "living life", "god first", "proud mom", "proud dad",
}


def _echo_edges(
    docs: dict[str, list[tuple[str, str]]],
    *,
    method: str,
    threshold: float,
    background: BatchBackground | None,
    min_chars: int,
    describe: str,
) -> list[Edge]:
    """Shared near-duplicate machinery for `verbatim_echo` and `bio_echo`.

    ``docs`` maps an account id to ``(normalised_text, original_text)`` pairs. Candidate pairs come
    from LSH so this stays linear in practice; the exact Jaccard decides.
    """
    flat: dict[str, tuple[str, str, str]] = {}   # doc key -> (account, normalised, original)
    for account_id, items in sorted(docs.items()):
        for i, (norm, original) in enumerate(items):
            if len(norm) < min_chars:
                continue
            flat[f"{account_id}#{i}"] = (account_id, norm, original)
    if len(flat) < 2:
        return []

    sigs = {k: textsim.minhash(textsim.shingles(v[1])) for k, v in flat.items()}
    shingle_cache = {k: textsim.shingles(v[1]) for k, v in flat.items()}

    seen_pairs: dict[tuple[str, str], float] = {}
    out: list[Edge] = []
    for ka, kb in sorted(textsim.lsh_candidates(sigs)):
        acc_a, norm_a, orig_a = flat[ka]
        acc_b, norm_b, _ = flat[kb]
        if acc_a == acc_b:
            continue
        j = textsim.jaccard(shingle_cache[ka], shingle_cache[kb])
        if j < threshold:
            continue
        # Full-batch gate: if a large share of the thread's authors posted this same string, it is
        # a copypasta going around, and copypasta is the single most common way a text detector
        # invents a campaign out of a joke.
        if background is not None:
            share = max(
                background.text_author_share(norm_a),
                background.text_author_share(norm_b),
            )
            if share > MAX_COPYPASTA_AUTHOR_SHARE:
                continue

        pair = (acc_a, acc_b) if acc_a <= acc_b else (acc_b, acc_a)
        weight = min(0.95, 0.55 + 0.40 * (j - threshold) / max(1e-9, 1.0 - threshold))
        if norm_a == norm_b and len(norm_a) >= 80:
            weight = 1.0
        if seen_pairs.get(pair, 0.0) >= weight:
            continue
        seen_pairs[pair] = weight
        out.append(Edge(
            a=pair[0], b=pair[1], method=method, weight=weight,
            sentence=(
                f"{describe} match at {j:.0%} similarity between "
                f"{pair[0]} and {pair[1]}."
            ),
            artifact=textsim.excerpt(orig_a),
            statistic=("jaccard", round(j, 4)),
        ))
    # Keep only the strongest edge per pair.
    best: dict[tuple[str, str], Edge] = {}
    for e in out:
        if e.pair not in best or e.weight > best[e.pair].weight:
            best[e.pair] = e
    return sorted(best.values(), key=lambda e: (e.a, e.b))


def verbatim_echo(cohort: Cohort) -> list[Edge]:
    """Two accounts emitted the same 40+ characters.

    ABSOLUTE: the improbability is a fact about the size of the string space, not about this
    batch. The batch background is used only to *subtract* the one known confound.

    REFUSES: short reactions ("first!", "great video") via the length floor; anything a quarter of
    the thread's authors also posted, via the copypasta share gate.
    """
    docs: dict[str, list[tuple[str, str]]] = {}
    for acc in cohort.accounts:
        items: list[tuple[str, str]] = []
        for c in acc.thread_comments:
            items.append((textsim.normalize(c.text), c.text))
        for s in acc.activity:
            items.append((textsim.normalize(s.text), s.text))
        docs[acc.external_id] = items
    return _echo_edges(
        docs, method="verbatim_echo", threshold=ECHO_JACCARD,
        background=cohort.background, min_chars=textsim.MIN_ECHO_CHARS,
        describe="Posted text",
    )


def bio_echo(cohort: Cohort) -> list[Edge]:
    """Two accounts carry the same profile bio.

    ABSOLUTE: same reasoning as `verbatim_echo`.

    REFUSES: an absent bio. ``bio is None`` means the platform never told us and ``bio == ""``
    means the account has none; neither is a match, and treating them as one would link every
    account whose profile fetch failed.
    """
    docs: dict[str, list[tuple[str, str]]] = {}
    for acc in cohort.accounts:
        if acc.bio is None:
            continue
        norm = textsim.normalize(acc.bio)
        if not norm or norm in _BIO_DENYLIST:
            continue
        docs[acc.external_id] = [(norm, acc.bio)]
    return _echo_edges(
        docs, method="bio_echo", threshold=BIO_ECHO_JACCARD, background=None,
        min_chars=MIN_BIO_CHARS, describe="Profile bio",
    )


# =============================================================================================
# Family TIMING
# =============================================================================================
#: Windows tested for a co-arrival burst.
BURST_WINDOWS = (15.0, 60.0, 300.0)
#: Half-width of the neighbourhood used to estimate the local arrival rate, in seconds.
RATE_HALF_SPAN = 900.0
BURST_MIN_ACCOUNTS = 3
BURST_MAX_P = 1e-4


def _epoch(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def burst_lockstep(cohort: Cohort) -> list[Edge]:
    """Cohort accounts arrived together, against the thread's own arrival rate.

    NOT absolute, and honest about it: this is the one signal that cannot mean anything without a
    null, and the null comes from the FULL comment stream, which the 70 filter never touched. On a
    viral post two hundred comments land per minute and four accounts sharing a minute is nothing.
    On a quiet post four inside twenty seconds is p ~ 1e-9.

    REFUSES: a viral post (the local rate absorbs it); a thread too sparse to estimate a rate at
    all, where it returns nothing rather than treating an unmeasurable rate as zero; and any
    investigation whose persisted arrivals cover only the scanned accounts rather than every author,
    because a rate measured over a subset is lower than the real one and would make ordinary
    co-timing look damning.
    """
    if not cohort.background.arrivals_complete:
        return []
    times = sorted(t for t in (_epoch(x) for x in cohort.background.thread_comment_times) if t)
    if len(times) < 3:
        return []

    per_account: list[tuple[float, str]] = []
    for acc in cohort.accounts:
        for c in acc.thread_comments:
            ts = _epoch(c.created_at)
            if ts is not None:
                per_account.append((ts, acc.external_id))
    per_account.sort()
    if len(per_account) < BURST_MIN_ACCOUNTS:
        return []

    n_windows = max(1, len(BURST_WINDOWS) * len(per_account))
    # The whole thread's rate, used whenever the immediate neighbourhood is too sparse to measure
    # and as a floor besides. Taking the max of the two is conservative in both directions: a busy
    # post is judged against its busy local rate, and a quiet lull inside a busy post is still
    # judged against the busy thread rather than against its own silence.
    g_rate = stats.global_rate(times)
    if g_rate is None:
        return []
    # Scale back up when the persisted arrival list was capped: the sample preserves the span but
    # not the count, and a rate computed from the sample would make a busy thread look quiet, which
    # is the direction that invents findings.
    total = cohort.background.thread_arrival_total
    if total > len(times):
        g_rate *= total / len(times)
    best: dict[tuple[str, str], Edge] = {}

    for window in BURST_WINDOWS:
        for start in range(len(per_account)):
            t0 = per_account[start][0]
            j = start
            group: list[tuple[float, str]] = []
            while j < len(per_account) and per_account[j][0] - t0 <= window:
                group.append(per_account[j])
                j += 1
            distinct = sorted({aid for _, aid in group})
            if len(distinct) < BURST_MIN_ACCOUNTS:
                continue
            centre = t0 + window / 2.0
            # Exclude the candidate burst from its own background, or it inflates the rate it is
            # tested against and hides itself. See stats.local_rate.
            local = stats.local_rate(
                times, centre, RATE_HALF_SPAN, exclude=(t0, t0 + window),
            )
            rate = g_rate if local is None else max(local, g_rate)
            mu = rate * window
            p = stats.poisson_sf(len(distinct), mu)
            p_adj = stats.bonferroni(p, n_windows)
            if p_adj > BURST_MAX_P:
                continue
            weight = min(0.95, max(0.0, -_log10(p_adj) / 12.0))
            if weight <= 0:
                continue
            stamp = datetime.fromtimestamp(t0, tz=timezone.utc).isoformat()
            artifact = "; ".join(
                f"{aid} at {datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()}"
                for ts, aid in group[:8]
            )
            sentence = (
                f"{len(distinct)} accounts commented inside {int(window)}s from {stamp}, "
                f"against a local rate of {rate * 60.0:.2f} comments per minute "
                f"(p={p_adj:.2e})."
            )
            for x in range(len(distinct)):
                for y in range(x + 1, len(distinct)):
                    pair = (distinct[x], distinct[y])
                    prev = best.get(pair)
                    if prev is None or weight > prev.weight:
                        best[pair] = Edge(
                            a=pair[0], b=pair[1], method="burst_lockstep", weight=weight,
                            sentence=sentence, artifact=artifact,
                            statistic=("p_value", p_adj),
                        )
    return sorted(best.values(), key=lambda e: (e.a, e.b))


def _log10(x: float) -> float:
    if x <= 0:
        return -300.0
    return math.log10(x)


# =============================================================================================
# Family NETWORK
# =============================================================================================
CO_TARGET_MIN_SHARED = 3
#: A target engaged by more than this share of the scanned batch is a popular thing, not a
#: rendezvous. Everyone in a thread about a video has that video as a target.
MAX_TARGET_BATCH_SHARE = 0.20


def co_target(cohort: Cohort) -> list[Edge]:
    """Two accounts keep turning up at the same non-popular places.

    ABSOLUTE: the id space is enormous, so overlap on three specific unpopular targets is not
    coincidence. The batch share gate removes the only real confound. Direct precedent:
    `co_engagement` sits in the engine's own DISCRIMINATIVE set on identical reasoning.

    REFUSES: targets a fifth of the batch also engaged.
    """
    sets: dict[str, set[str]] = {}
    for acc in cohort.accounts:
        targets = set()
        for s in acc.activity:
            for t in s.targets():
                if cohort.background.batch_share(
                    cohort.background.target_counts, t
                ) <= MAX_TARGET_BATCH_SHARE:
                    targets.add(t)
        if targets:
            sets[acc.external_id] = targets

    out: list[Edge] = []
    ids = sorted(sets)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            shared = sorted(sets[a] & sets[b])
            if len(shared) < CO_TARGET_MIN_SHARED:
                continue
            weight = min(0.90, 0.30 + 0.15 * len(shared))
            out.append(Edge(
                a=a, b=b, method="co_target", weight=weight,
                sentence=(
                    f"{a} and {b} both engaged {len(shared)} of the same posts, none of which "
                    f"more than {MAX_TARGET_BATCH_SHARE:.0%} of the scanned batch touched."
                ),
                artifact=", ".join(shared[:8]),
                statistic=("shared_targets", float(len(shared))),
            ))
    return out


# =============================================================================================
# Family INFRASTRUCTURE
# =============================================================================================
MIN_CLIENT_POSTS = 5
CLIENT_DOMINANCE = 0.80
#: The clients essentially every real person uses. Sharing one of these is not evidence of
#: anything. This is the whole reason the signal can be discriminative: what is left after this
#: list is a third-party tool, and rarity here is a published property of the platform ecosystem
#: rather than a property of this batch.
_UBIQUITOUS_CLIENTS = {
    "twitter for iphone", "twitter for android", "twitter web app", "twitter for ipad",
    "tweetdeck", "twitter for mac", "x web app", "x for iphone", "x for android",
    "twitter web client", "web", "mobile web",
}


def _dominant_client(acc: CohortAccount) -> tuple[str, int, int] | None:
    counts: dict[str, int] = defaultdict(int)
    total = 0
    for s in acc.activity:
        if not s.source_client:
            continue
        counts[s.source_client.strip()] += 1
        total += 1
    if total < MIN_CLIENT_POSTS or not counts:
        return None
    client, n = max(sorted(counts.items()), key=lambda kv: kv[1])
    if n / total < CLIENT_DOMINANCE:
        return None
    if client.casefold() in _UBIQUITOUS_CLIENTS:
        return None
    return client, n, total


def client_signature(cohort: Cohort) -> list[Edge]:
    """Two accounts push most of their output through the same uncommon publishing tool.

    ABSOLUTE, and the cleanest of the seven. The client string is a machine fact the platform
    reports. Rarity is a property of the client ecosystem, not of this cohort.

    REFUSES: every ubiquitous first-party client. Abstains entirely on YouTube, which has no
    equivalent field, rather than inventing one.
    """
    dominant: dict[str, tuple[str, int, int]] = {}
    for acc in cohort.accounts:
        d = _dominant_client(acc)
        if d:
            dominant[acc.external_id] = d

    out: list[Edge] = []
    ids = sorted(dominant)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            ca, na, ta = dominant[a]
            cb, nb, tb = dominant[b]
            if ca.casefold() != cb.casefold():
                continue
            share = cohort.background.batch_share(cohort.background.client_counts, ca)
            weight = 0.92 if share <= (2.0 / max(1, cohort.background.scanned_total)) else 0.85
            out.append(Edge(
                a=a, b=b, method="client_signature", weight=weight,
                sentence=(
                    f"{a} ({na}/{ta} posts) and {b} ({nb}/{tb} posts) both publish through "
                    f"\"{ca}\", which is not a standard first-party client."
                ),
                artifact=ca,
                statistic=("batch_share", round(share, 4)),
            ))
    return out


# =============================================================================================
# Family IDENTITY
# =============================================================================================
PROVISION_MAX_WINDOW = 6 * 3600.0
PROVISION_TIGHT_WINDOW = 600.0
PROVISION_MIN_ACCOUNTS = 3
PROVISION_MAX_P = 1e-3
#: Neighbourhood used to estimate the local creation-date density, in seconds (60 days). Wide
#: enough to contain real points when a batch's accounts are years apart, narrow enough that a
#: genuine signup wave still raises the local density and absorbs itself.
PROVISION_BANDWIDTH = 60 * 24 * 3600.0


def provisioning_window(cohort: Cohort) -> list[Edge]:
    """Cohort accounts were created within minutes or hours of each other.

    PARTIALLY absolute: creation timestamps carry second resolution and spread over a platform's
    whole history. The batch's empirical distribution supplies the null, because platform growth
    is famously non-uniform and a theoretical uniform prior would fire on every signup wave.

    REFUSES: date-only timestamps. Some providers hand back a bare date, and a date-only cohort is
    exactly the `age_cohort` false positive this product has already paid for once. If the
    resolution is not there, the signal says nothing.
    """
    usable: list[tuple[float, str]] = []
    for acc in cohort.accounts:
        ts = _epoch(acc.account_created_at)
        if ts is None:
            continue
        # Sub-day resolution check: a bare date lands exactly on midnight.
        if acc.account_created_at is not None and (
            acc.account_created_at.hour == 0
            and acc.account_created_at.minute == 0
            and acc.account_created_at.second == 0
        ):
            continue
        usable.append((ts, acc.external_id))
    if len(usable) < PROVISION_MIN_ACCOUNTS:
        return []
    usable.sort()

    batch = sorted(t for t in (_epoch(x) for x in cohort.background.batch_created_at) if t)
    if len(batch) < PROVISION_MIN_ACCOUNTS:
        return []

    best: dict[tuple[str, str], Edge] = {}
    for start in range(len(usable)):
        t0 = usable[start][0]
        group = [(t, a) for t, a in usable[start:] if t - t0 <= PROVISION_MAX_WINDOW]
        distinct = sorted({a for _, a in group})
        if len(distinct) < PROVISION_MIN_ACCOUNTS:
            continue
        span = group[-1][0] - t0
        # The window's background mass, excluding the candidate cluster and floored at the uniform
        # rate over the batch's whole span. See stats.window_mass: counting the cluster in its own
        # background hides it, and a raw empirical count has no resolution at this width.
        mass = stats.window_mass(
            batch, t0, t0 + max(span, 1.0), bandwidth=PROVISION_BANDWIDTH,
        )
        if mass is None:
            continue
        p = stats.scan_statistic_p(len(batch), len(distinct), mass)
        if p is None or p > PROVISION_MAX_P:
            continue
        tight = span <= PROVISION_TIGHT_WINDOW
        weight = 0.80 if tight else 0.35 + 0.45 * (1.0 - min(1.0, span / PROVISION_MAX_WINDOW))
        artifact = "; ".join(
            f"{a} created {datetime.fromtimestamp(t, tz=timezone.utc).isoformat()}"
            for t, a in group[:8]
        )
        sentence = (
            f"{len(distinct)} accounts were created inside {_human_span(span)} of each other "
            f"(p={p:.2e} against the {len(batch)} creation dates in this scan)."
        )
        for x in range(len(distinct)):
            for y in range(x + 1, len(distinct)):
                pair = (distinct[x], distinct[y])
                prev = best.get(pair)
                if prev is None or weight > prev.weight:
                    best[pair] = Edge(
                        a=pair[0], b=pair[1], method="provisioning_window", weight=weight,
                        sentence=sentence, artifact=artifact, statistic=("p_value", p),
                    )
    return sorted(best.values(), key=lambda e: (e.a, e.b))


def _human_span(seconds: float) -> str:
    if seconds < 90:
        return f"{int(seconds)} seconds"
    if seconds < 5400:
        return f"{seconds / 60.0:.0f} minutes"
    return f"{seconds / 3600.0:.1f} hours"


_DIGIT_RUN = re.compile(r"\d+")
_LETTER_RUN = re.compile(r"[^\W\d_]+", re.UNICODE)
#: Shapes platforms generate themselves. The constitution is explicit that digits appended to a
#: handle are auto-generated on signup collision and are NEVER a tell; this is that rule promoted
#: from prompt text into code. Forget it and this signal fires on half of any platform.
MAX_SKELETON_BATCH_SHARE = 0.20


def handle_skeleton(handle: str) -> str | None:
    """``john_smith8412`` -> ``L4_L5####``. Separators are kept; that is what makes a template a
    template rather than a name with numbers stuck on the end."""
    if not handle:
        return None
    out: list[str] = []
    i = 0
    while i < len(handle):
        ch = handle[i]
        m = _DIGIT_RUN.match(handle, i)
        if m:
            out.append("#" * min(8, len(m.group(0))))
            i = m.end()
            continue
        m = _LETTER_RUN.match(handle, i)
        if m:
            out.append(f"L{min(9, len(m.group(0)))}")
            i = m.end()
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _is_auto_append(skeleton: str) -> bool:
    """One letter run followed by digits and nothing else. That is the signup-collision shape."""
    return bool(re.fullmatch(r"L\d#+", skeleton))


def handle_template(cohort: Cohort) -> list[Edge]:
    """Two handles came out of the same generator.

    SUPPORTING only. A multi-part template (``L4_L5_####``) is a generator artifact and the shape
    space is large, but handles are also just names and this is the signal most easily produced by
    accident.

    REFUSES: the auto-append shape (letters then digits, no separator), unconditionally; and any
    skeleton a fifth of the batch shares.
    """
    by_skeleton: dict[str, list[str]] = defaultdict(list)
    for acc in cohort.accounts:
        sk = handle_skeleton(acc.handle or "")
        if not sk or _is_auto_append(sk):
            continue
        share = cohort.background.batch_share(cohort.background.handle_skeleton_counts, sk)
        if share > MAX_SKELETON_BATCH_SHARE:
            continue
        by_skeleton[sk].append(acc.external_id)

    handles = {a.external_id: a.handle for a in cohort.accounts}
    out: list[Edge] = []
    for sk, members in sorted(by_skeleton.items()):
        if len(members) < 2:
            continue
        segments = len(re.findall(r"L\d|#+|[^L#\d]", sk))
        weight = 0.30 + (0.20 if segments >= 3 else 0.0)
        members = sorted(members)
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                out.append(Edge(
                    a=a, b=b, method="handle_template", weight=weight,
                    sentence=(
                        f"{handles.get(a, a)} and {handles.get(b, b)} share the handle "
                        f"template {sk}, held by under "
                        f"{MAX_SKELETON_BATCH_SHARE:.0%} of the scanned batch."
                    ),
                    artifact=f"{handles.get(a, a)} / {handles.get(b, b)} -> {sk}",
                    statistic=("segments", float(segments)),
                ))
    return out


#: Registry. `run.py` iterates this, so adding a signal is one entry plus a family in
#: `types.METHOD_FAMILY`.
SIGNALS = (
    verbatim_echo,
    bio_echo,
    burst_lockstep,
    co_target,
    client_signature,
    provisioning_window,
    handle_template,
)
