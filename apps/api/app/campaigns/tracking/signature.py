"""Operation identity that survives burning every account.

A serious operation does not reuse accounts. It runs a campaign, the accounts get suspended or
retired, and the next campaign runs on entirely new ones. Matching by shared members therefore fails
in exactly the case that matters most: ``CampaignService._match_or_create`` sees no overlap, mints a
fresh random key, and the system reports a brand-new operation it has actually seen three times.

What an operation does keep is its **behaviour**: the script it hands out, the factory its handles
come from, the batch its accounts were provisioned in, the tool it publishes with, the links it
pushes. This module sketches that, and only that.

**No account ids, ever.** A signature must be comparable across deployments and across time without
revealing who was scanned, and a sketch containing ids would leak the membership of one customer's
investigation into a match against another's. Pinned by
``test_a_signature_reveals_nothing_about_who_was_scanned``.

---------------------------------------------------------------------------------------------------
ON THE HASH FAMILY, WHICH IS NOT A DETAIL
---------------------------------------------------------------------------------------------------

``verdict_coordination._minhash`` derives its permutations by XOR-ing one base hash with a constant
per permutation. That is not a universal hash family: the permutations are strongly correlated, so
the estimator is biased and the banding arithmetic (which assumes independent draws) does not hold.
At one-investigation scale nobody noticed. At deployment scale, where band collisions decide which
operations get compared at all, it would produce a match rate nothing in the design predicts.

This module uses independently salted BLAKE2b instead, the same construction as
``detector/textsim._hash64``, where each permutation gets its own salt and is genuinely independent.
"""

from __future__ import annotations

import hashlib
import re

from app.campaigns.detector import textsim

#: 128 permutations in 32 bands of 4. The band count sets the S-curve: two operations sharing ~40%
#: of their behavioural tokens collide in at least one band with high probability, which is the
#: recall we want given a rotated operation never reproduces its previous run exactly.
SIGNATURE_PERMUTATIONS = 128
SIGNATURE_BANDS = 32
SIGNATURE_ROWS = SIGNATURE_PERMUTATIONS // SIGNATURE_BANDS

#: Estimated Jaccard required to accept a band collision as the same operation. Bands generate
#: candidates cheaply and are allowed to be noisy; this is the decision.
SIGNATURE_MATCH_THRESHOLD = 0.40

#: Below this many behavioural tokens an operation has not shown enough of itself to be identified
#: later, and a sketch built from two tokens will collide with everything. Such an operation simply
#: has no signature, which is honest: it can still be matched by member overlap.
MIN_SIGNATURE_TOKENS = 6

_MASK64 = (1 << 64) - 1
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _hash64(value: str, seed: int) -> int:
    """Independently salted BLAKE2b. See the module docstring for why this matters."""
    return int.from_bytes(
        hashlib.blake2b(
            value.encode("utf-8"), digest_size=8, salt=seed.to_bytes(8, "little"),
        ).digest(),
        "little",
    )


def _minhash(tokens: frozenset[str], num_perm: int = SIGNATURE_PERMUTATIONS) -> tuple[int, ...]:
    if not tokens:
        return tuple([_MASK64] * num_perm)
    sig = [_MASK64] * num_perm
    for token in tokens:
        for i in range(num_perm):
            h = _hash64(token, i)
            if h < sig[i]:
                sig[i] = h
    return tuple(sig)


def behavioural_tokens(
    *,
    scripts: list[str] | None = None,
    handles: list[str] | None = None,
    creation_buckets: list[str] | None = None,
    clients: list[str] | None = None,
    link_domains: list[str] | None = None,
) -> frozenset[str]:
    """The operation's behaviour, as a set of namespaced tokens.

    Each input is namespaced so a client string can never accidentally equal a handle skeleton, and
    each is normalised so trivial variation does not split a token.
    """
    tokens: set[str] = set()

    for text in scripts or []:
        normalised = textsim.normalize(text)
        if len(normalised) >= textsim.MIN_ECHO_CHARS:
            # Shingles rather than whole strings: an operation that lightly edits its script between
            # runs keeps most of its shingles and none of its exact strings.
            for shingle in textsim.shingles(normalised):
                tokens.add(f"q:{shingle}")

    for handle in handles or []:
        skeleton = _handle_skeleton(handle)
        if skeleton:
            tokens.add(f"h:{skeleton}")

    for bucket in creation_buckets or []:
        if bucket:
            tokens.add(f"c:{bucket}")

    for client in clients or []:
        cleaned = _NON_ALNUM.sub("-", (client or "").strip().casefold()).strip("-")
        if cleaned:
            tokens.add(f"t:{cleaned}")

    for domain in link_domains or []:
        cleaned = (domain or "").strip().casefold().lstrip(".")
        if cleaned:
            tokens.add(f"d:{cleaned}")

    return frozenset(tokens)


def _handle_skeleton(handle: str) -> str | None:
    """Delegates to the detector so the two never drift apart."""
    from app.campaigns.detector.signals import handle_skeleton

    return handle_skeleton(handle or "")


def build_signature(tokens: frozenset[str]) -> tuple[list[int], list[str]] | None:
    """``(sketch, band_keys)``, or ``None`` when the operation has not shown enough of itself.

    Returning ``None`` rather than a degenerate sketch is deliberate: a sketch over two tokens
    collides with half the deployment, and a match rule that fires on everything is worse than no
    match rule at all.
    """
    if len(tokens) < MIN_SIGNATURE_TOKENS:
        return None
    sketch = _minhash(tokens)
    return list(sketch), band_keys(sketch)


def band_keys(sketch: tuple[int, ...] | list[int]) -> list[str]:
    """The LSH band keys for a sketch, one per band."""
    out: list[str] = []
    for band in range(SIGNATURE_BANDS):
        chunk = tuple(sketch[band * SIGNATURE_ROWS:(band + 1) * SIGNATURE_ROWS])
        out.append(
            hashlib.blake2b(repr(chunk).encode("utf-8"), digest_size=8).hexdigest()
        )
    return out


def signature_similarity(a: list[int] | None, b: list[int] | None) -> float:
    """Estimated Jaccard between two sketches: the fraction of positions that agree."""
    if not a or not b or len(a) != len(b):
        return 0.0
    matches = sum(1 for x, y in zip(a, b) if x == y)
    return matches / len(a)


def signature_for_members(members: list[str], accounts_by_id: dict) -> tuple[list[int], list[str]] | None:
    """Build an operation's signature from the accounts it is made of.

    Reads only behaviour: what they wrote, the shape of their handles, the month they were created,
    what they publish with, where they link. Never an id, never a handle verbatim.
    """
    scripts: list[str] = []
    handles: list[str] = []
    buckets: list[str] = []
    clients: list[str] = []
    domains: list[str] = []

    for member in members:
        account = accounts_by_id.get(member)
        if account is None:
            continue
        if account.handle:
            handles.append(account.handle)
        created = getattr(account, "account_created_at", None)
        if created is not None:
            # Month granularity: a provisioning batch shares a month, and finer resolution would
            # stop two runs of one operation from sharing the token at all.
            buckets.append(f"{created.year:04d}-{created.month:02d}")
        for comment in getattr(account, "thread_comments", []) or []:
            if comment.text:
                scripts.append(comment.text)
        for sample in getattr(account, "activity", []) or []:
            if sample.text:
                scripts.append(sample.text)
            if sample.source_client:
                clients.append(sample.source_client)
        for url in _domains_in(scripts[-8:]):
            domains.append(url)

    return build_signature(behavioural_tokens(
        scripts=scripts[:60], handles=handles, creation_buckets=buckets,
        clients=clients, link_domains=domains,
    ))


_URL_HOST = re.compile(r"https?://([^/\s]+)", re.I)
#: Domains everybody links. Sharing one is not a signature of anything.
_COMMON_DOMAINS = {
    "twitter.com", "x.com", "youtube.com", "youtu.be", "t.co", "instagram.com",
    "facebook.com", "tiktok.com", "reddit.com", "wikipedia.org", "google.com",
}


def _domains_in(texts: list[str]) -> list[str]:
    out: list[str] = []
    for text in texts:
        for host in _URL_HOST.findall(text or ""):
            host = host.strip().casefold().removeprefix("www.")
            if host and host not in _COMMON_DOMAINS:
                out.append(host)
    return out
