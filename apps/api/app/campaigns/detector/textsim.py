"""Near-duplicate text detection: normalise, shingle, MinHash, LSH, verify.

Pure stdlib plus numpy. No model, no embedding, no network. The whole point of this module is
that "these two accounts posted the same thing" is checkable arithmetic rather than a judgement.

Why shingles and not semantic similarity: under a single post everyone is on-topic, so a semantic
score measures the topic and not the coordination, and there is no background here to subtract the
topic out against. Character-level near-duplication has no such confound. Two accounts emitting the
same forty characters is improbable as a fact about the size of the string space, which is exactly
the kind of claim that survives losing the batch background.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

#: Below this many characters after normalisation, a repeat is not evidence. "great video" and
#: "first!!" are posted by unrelated people on every video ever made. Forty is chosen to sit
#: comfortably above every common short reaction while still catching a one-line script.
MIN_ECHO_CHARS = 40
SHINGLE_K = 5
NUM_PERM = 128
#: b * r must equal NUM_PERM. Banding at 32x4 puts the S-curve inflection near J ~ 0.76, just
#: under the 0.80 verification threshold, so candidates are generated slightly liberally and the
#: exact check does the deciding.
LSH_BANDS = 32
LSH_ROWS = 4

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
_WS_RE = re.compile(r"\s+")
#: Zero-width and variation selectors. Padding a copy-pasted script with these is the cheapest
#: possible evasion, so they come out before anything is compared.
_INVISIBLE_RE = re.compile(r"[​-‏‪-‮⁠-⁯︀-️﻿]")

_MASK64 = (1 << 64) - 1


def normalize(text: str, *, strip_urls: bool = True) -> str:
    """Casefold to the form two copies of one script share.

    NFKC first, so a fullwidth or styled-unicode copy of a string collapses onto the plain one.
    """
    if not text:
        return ""
    out = unicodedata.normalize("NFKC", text)
    out = _INVISIBLE_RE.sub("", out)
    if strip_urls:
        out = _URL_RE.sub(" ", out)
    out = out.casefold()
    out = _WS_RE.sub(" ", out).strip()
    return out


def shingles(text: str, k: int = SHINGLE_K) -> frozenset[str]:
    if len(text) < k:
        return frozenset({text} if text else ())
    return frozenset(text[i:i + k] for i in range(len(text) - k + 1))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / len(a | b)


def _hash64(value: str, seed: int) -> int:
    """Stable across processes and Python versions, unlike ``hash()``.

    ``hash()`` is randomised per process by PYTHONHASHSEED, which would make the detector produce
    a different answer on every worker. These findings name real accounts; the same input has to
    give the same output.
    """
    digest = hashlib.blake2b(
        value.encode("utf-8"), digest_size=8, salt=seed.to_bytes(8, "little"),
    ).digest()
    return int.from_bytes(digest, "little")


def minhash(sh: frozenset[str], num_perm: int = NUM_PERM) -> tuple[int, ...]:
    if not sh:
        return tuple([_MASK64] * num_perm)
    sig = [_MASK64] * num_perm
    for token in sh:
        for i in range(num_perm):
            h = _hash64(token, i)
            if h < sig[i]:
                sig[i] = h
    return tuple(sig)


def lsh_candidates(
    signatures: dict[str, tuple[int, ...]],
    *,
    bands: int = LSH_BANDS,
    rows: int = LSH_ROWS,
    max_bucket: int = 400,
) -> set[tuple[str, str]]:
    """Candidate pairs whose signatures collide in at least one band.

    ``max_bucket`` drops a bucket that has swallowed a large share of the input. A bucket that
    size means the "shared" text is something everyone posted, and expanding it costs O(n^2) pairs
    to then reject them all one at a time.
    """
    out: set[tuple[str, str]] = set()
    for band in range(bands):
        lo, hi = band * rows, (band + 1) * rows
        buckets: dict[tuple[int, ...], list[str]] = {}
        for key in sorted(signatures):
            slice_ = signatures[key][lo:hi]
            buckets.setdefault(slice_, []).append(key)
        for members in buckets.values():
            if len(members) < 2 or len(members) > max_bucket:
                continue
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    a, b = members[i], members[j]
                    out.add((a, b) if a <= b else (b, a))
    return out


def excerpt(text: str, limit: int = 220) -> str:
    """A quotable artifact. Truncation is marked so nobody reads a cut string as the whole one."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."
