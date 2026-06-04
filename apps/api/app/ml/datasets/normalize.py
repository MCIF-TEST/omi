"""Tolerant value/label parsing shared by every adapter.

Public datasets are messy: booleans show up as ``1``/``True``/``yes``/``fake``,
counts arrive as floats or z-scored negatives, headers vary in case and
spacing. These helpers absorb that variation in one place so the adapters stay
declarative.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

# Tokens that, appearing in a label/column value, mean "inauthentic"
# (bot / fake / AI-generated). Order doesn't matter; matched as substrings on
# the lowercased value.
_INAUTHENTIC_TOKENS = (
    "fake", "bot", "ai", "spam", "generated", "machine", "synthetic",
    "automated", "troll", "inauthentic",
)
_AUTHENTIC_TOKENS = (
    "real", "human", "genuine", "authentic", "legit", "organic",
)

_TRUE_TOKENS = {"1", "true", "t", "yes", "y"}
_FALSE_TOKENS = {"0", "false", "f", "no", "n", "none"}


def norm_key(key: str) -> str:
    """Normalize a header cell for signature matching: lowercase, trimmed,
    spaces and dashes collapsed to underscores."""
    return "_".join(key.strip().lower().replace("-", " ").split())


def normalize_header(header: Iterable[str]) -> set[str]:
    return {norm_key(h) for h in header if h is not None}


def to_float(value: object) -> float | None:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# Timestamp formats seen across the corpus, tried in order after ISO-8601.
# IO disclosures: "2019-10-23 06:05" / "2019-10-21". TwitterData: day-first
# "27-11-2016 06:15". Twitter_Data.csv: ISO with seconds "2016-11-27 06:15:03".
_DT_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d-%m-%Y",
    "%a %b %d %H:%M:%S %z %Y",   # Twitter API "Wed May 15 16:00:19 +0000 2019"
)


def parse_datetime(value: object) -> datetime | None:
    """Parse a real timestamp from a dataset cell into a tz-aware UTC datetime.

    Returns ``None`` when the value is empty or unrecognized, so callers can
    fall back rather than fabricate a time. Naive timestamps are treated as UTC
    (the platform archives — Twitter/X Transparency, the TwitterData export —
    are UTC). This is the helper that lets *real* tweet cadence reach the
    temporal detector instead of the synthetic 1-hour spacing."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        dt = None
    if dt is None:
        for fmt in _DT_FORMATS:
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def days_since(value: object) -> int | None:
    """Days between a creation timestamp and now (UTC), or ``None`` if
    unparseable. Lets an adapter turn an ``account_creation_date`` column into a
    real ``account_age_days`` instead of leaving the profile detector blind."""
    dt = parse_datetime(value)
    if dt is None:
        return None
    return max(0, (datetime.now(timezone.utc) - dt).days)


def to_count(value: object, *, allow_negative: bool = False) -> int | None:
    """Parse a count-like field. Many public account datasets ship z-scored or
    otherwise anonymized numerics where a "follower count" can be negative or
    fractional; feeding those to the engine as raw counts is garbage, so by
    default we drop negatives to ``None`` (the metadata block degrades
    gracefully) and round the rest."""
    f = to_float(value)
    if f is None:
        return None
    if f < 0 and not allow_negative:
        return None
    return int(round(f))


def parse_bool_label(value: object) -> bool | None:
    """Interpret a free-text / numeric label as inauthentic (True) vs
    authentic (False). Returns ``None`` when the value carries no signal."""
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    if s in _TRUE_TOKENS:
        return True
    if s in _FALSE_TOKENS:
        return False
    # Substring match: "AI-generated", "Human-written", "None (Human)" etc.
    has_bad = any(tok in s for tok in _INAUTHENTIC_TOKENS)
    has_good = any(tok in s for tok in _AUTHENTIC_TOKENS)
    if has_bad and not has_good:
        return True
    if has_good and not has_bad:
        return False
    # Ambiguous (e.g. "None (Human)" contains neither cleanly, or both) — fall
    # back to the authentic token winning only if it's the dominant phrase.
    if has_good:
        return False
    if has_bad:
        return True
    return None


def label_hint_from_filename(filename: str) -> bool | None:
    """Some datasets encode the label in the *filename* (``fake_users.csv`` vs
    ``real_users.csv``) rather than a column. Derive the binary label from the
    name when it is unambiguous."""
    return parse_bool_label(filename)
