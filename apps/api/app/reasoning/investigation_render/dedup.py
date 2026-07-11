"""Lossless collapse of repetitive evidence — near-duplicate comments and repeated relationships.

A coordinated campaign is, by nature, repetitive: the same copy-paste comment across dozens of
accounts, the same relationship type between the same pair. Rendered verbatim, that repetition inflates
the token budget without adding investigative signal — and worse, lets one repetitive domain crowd out
another. Both collapses here are **lossless**: they preserve an exemplar, the exact member count, every
member ref, the time range, and the measured similarity — so the model still sees *that* N accounts
posted the same text (a coordination signal), just not N verbatim copies. Nothing is discarded; the
group IS the evidence.

Determinism: grouping is by a normalized-text signature (case/whitespace/punctuation-folded), so it is
reproducible; the reported similarity is the minimum token-set Jaccard of each member's ORIGINAL text
against the exemplar (1.0 when the originals are identical, <1.0 across surface variants).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]")
_WORD = re.compile(r"\w+")


def _signature(text: str) -> str:
    """A normalized signature for near-duplicate grouping: lowercase, punctuation stripped, whitespace
    collapsed. Two texts share a signature iff they are the same up to surface noise."""
    t = _PUNCT.sub(" ", (text or "").lower())
    return _WS.sub(" ", t).strip()


def _jaccard(a: str, b: str) -> float:
    """Token-set Jaccard similarity of two original texts (order-independent, deterministic)."""
    sa, sb = set(_WORD.findall(a.lower())), set(_WORD.findall(b.lower()))
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


@dataclass(frozen=True)
class CommentGroup:
    """A near-duplicate comment group — lossless: exemplar + exact count + every member ref + the time
    range + the measured intra-group similarity. A singleton group is a normal, non-repeated comment."""

    exemplar: str
    count: int
    author_refs: tuple[str, ...]         # aliased author handles, deduplicated + sorted
    earliest: str | None
    latest: str | None
    similarity: float                    # min original-vs-exemplar Jaccard (1.0 if identical)
    is_duplicate_group: bool             # True when count > 1 (a coordination signal in itself)


def group_near_duplicate_comments(comments, alias) -> tuple[CommentGroup, ...]:
    """Group a bundle's comments into near-duplicate groups (lossless). ``comments`` is the Comment
    bundle's ``comments`` tuple; ``alias`` maps ``author_ref`` to a short handle. Groups are ordered by
    descending size then exemplar text (deterministic); group size — NOT suspicion — is the only order
    key, because a larger identical-text group is a stronger coordination signal."""
    buckets: dict[str, list] = {}
    order: list[str] = []
    for c in comments:
        sig = _signature(c.text)
        if sig not in buckets:
            buckets[sig] = []
            order.append(sig)
        buckets[sig].append(c)
    groups: list[CommentGroup] = []
    for sig in order:
        members = buckets[sig]
        exemplar = members[0].text
        times = sorted(m.created_at for m in members if m.created_at)
        refs = tuple(sorted({alias.account_alias(m.author_ref) for m in members}))
        sim = min((_jaccard(m.text, exemplar) for m in members), default=1.0)
        groups.append(CommentGroup(
            exemplar=exemplar, count=len(members), author_refs=refs,
            earliest=(times[0] if times else None), latest=(times[-1] if times else None),
            similarity=round(sim, 4), is_duplicate_group=len(members) > 1,
        ))
    groups.sort(key=lambda g: (-g.count, g.exemplar))
    return tuple(groups)


@dataclass(frozen=True)
class RelationshipGroup:
    """A collapsed set of identical relationships — lossless: type + endpoints (aliased) + exact
    count."""

    type: str
    from_ref: str
    to_ref: str
    count: int


def collapse_relationships(graph_edges, alias) -> tuple[RelationshipGroup, ...]:
    """Collapse repeated graph edges of the same type between the same (aliased) endpoints into one
    row with an exact count. Lossless (the count preserves multiplicity); deterministic order."""
    counts: dict[tuple[str, str, str], int] = {}
    for e in graph_edges:
        key = (e.type, alias.account_alias(e.from_ref), alias.account_alias(e.to_ref))
        counts[key] = counts.get(key, 0) + 1
    rows = [RelationshipGroup(type=t, from_ref=f, to_ref=to, count=n)
            for (t, f, to), n in counts.items()]
    rows.sort(key=lambda r: (-r.count, r.type, r.from_ref, r.to_ref))
    return tuple(rows)


__all__ = [
    "CommentGroup", "group_near_duplicate_comments",
    "RelationshipGroup", "collapse_relationships",
]
