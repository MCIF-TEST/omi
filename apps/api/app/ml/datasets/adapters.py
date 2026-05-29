"""Concrete dataset adapters.

Each adapter recognizes one family of dataset by its (normalized) column
signature and maps rows to a canonical record. Specific adapters score >= 10;
the two generic sniffers score 1 so they only win when nothing more precise
claims the file. Rows arrive with normalized keys (see
:func:`app.ml.datasets.normalize.norm_key`).

Adding support for a new upload is usually a ~15-line adapter here. If the new
file uses recognizable column names, the generic sniffers may already handle it
with no code at all.
"""

from __future__ import annotations

from app.ml.datasets.normalize import (
    label_hint_from_filename,
    parse_bool_label,
    to_count,
)
from app.ml.datasets.records import PublicRecord, TextRecord
from app.ml.datasets.registry import DatasetAdapter, register_adapter

# Column-name vocabularies for the generic sniffers.
_TEXT_COLS = ("text", "text_content", "content", "comment", "body", "message", "post", "tweet")
_TEXT_LABEL_COLS = ("label", "human_or_ai", "is_ai", "ai_generated", "generated", "class", "target", "type")
_ACCOUNT_LABEL_COLS = ("is_fake", "is_bot", "is_bot_flag", "fake", "bot", "account_type", "label", "class", "target")
_FOLLOWER_COLS = ("followers", "follower_count", "followers_count")
_FOLLOWING_COLS = ("following", "following_count", "friends_count", "friends")


def _first(row: dict, *keys: str) -> object | None:
    for k in keys:
        if k in row and str(row.get(k) or "").strip():
            return row[k]
    return None


def _subset(header: set, *cols: str) -> bool:
    return all(c in header for c in cols)


def _any_in(header: set, cols) -> bool:
    return any(c in header for c in cols)


# ---------------------------------------------------------------------------
# Text adapters
# ---------------------------------------------------------------------------

def _parse_text_v1(row: dict, filename: str, row_id: str) -> TextRecord | None:
    text = str(row.get("text") or "").strip()
    is_ai = parse_bool_label(row.get("label"))
    if not text or is_ai is None:
        return None
    return TextRecord(
        external_id=str(row.get("id") or row_id),
        text=text, is_ai=is_ai,
        source_model=(str(row.get("model")) or None),
    )


def _parse_text_2026(row: dict, filename: str, row_id: str) -> TextRecord | None:
    text = str(row.get("text_content") or "").strip()
    is_ai = parse_bool_label(row.get("label"))
    if not text or is_ai is None:
        return None
    return TextRecord(
        external_id=str(row.get("text_id") or row_id),
        text=text, is_ai=is_ai,
        source_model=(str(row.get("source_model")) or None),
        domain=(str(row.get("domain")) or None),
    )


def _parse_text_detection_v1(row: dict, filename: str, row_id: str) -> TextRecord | None:
    text = str(row.get("text") or "").strip()
    is_ai = parse_bool_label(row.get("human_or_ai"))
    if not text or is_ai is None:
        return None
    return TextRecord(
        external_id=str(row.get("id") or row_id),
        text=text, is_ai=is_ai,
        source_model=(str(row.get("source_model")) or None),
        domain=(str(row.get("domain")) or None),
        language=(str(row.get("language")) or None),
    )


def _parse_text_generic(row: dict, filename: str, row_id: str) -> TextRecord | None:
    text_val = _first(row, *_TEXT_COLS)
    label_val = _first(row, *_TEXT_LABEL_COLS)
    if text_val is None or label_val is None:
        return None
    is_ai = parse_bool_label(label_val)
    if is_ai is None:
        return None
    return TextRecord(external_id=row_id, text=str(text_val).strip(), is_ai=is_ai)


# ---------------------------------------------------------------------------
# Account adapters
# ---------------------------------------------------------------------------

def _parse_fake_social_media(row: dict, filename: str, row_id: str) -> PublicRecord | None:
    is_bot = parse_bool_label(row.get("is_fake"))
    if is_bot is None:
        return None
    return PublicRecord(
        external_id=row_id,
        texts=[],  # behavioral-only dataset: no raw post text
        is_bot=is_bot,
        follower_count=to_count(row.get("followers")),
        following_count=to_count(row.get("following")),
        account_age_days=to_count(row.get("account_age_days")),
        handle=f"fsm_{row_id.split(':')[-1]}",
    )


def _parse_twitter_user(row: dict, filename: str, row_id: str) -> PublicRecord | None:
    # Label lives in the filename (fake_users.csv vs real_users.csv).
    is_bot = label_hint_from_filename(filename)
    if is_bot is None:
        return None
    handle = str(row.get("screen_name") or row.get("name") or row_id).strip() or row_id
    return PublicRecord(
        external_id=str(row.get("id") or row_id),
        texts=[],
        is_bot=is_bot,
        follower_count=to_count(row.get("followers_count")),
        following_count=to_count(row.get("friends_count")),
        handle=handle,
    )


def _parse_reddit(row: dict, filename: str, row_id: str) -> PublicRecord | None:
    is_bot = parse_bool_label(row.get("is_bot_flag"))
    if is_bot is None:
        return None
    return PublicRecord(
        external_id=str(row.get("comment_id") or row_id),
        texts=[],
        is_bot=is_bot,
        account_age_days=to_count(row.get("account_age_days")),
        handle=f"rdt_{row_id.split(':')[-1]}",
    )


def _parse_accounts_generic(row: dict, filename: str, row_id: str) -> PublicRecord | None:
    label_val = _first(row, *_ACCOUNT_LABEL_COLS)
    is_bot = parse_bool_label(label_val) if label_val is not None else None
    if is_bot is None:
        is_bot = label_hint_from_filename(filename)
    if is_bot is None:
        return None
    text_val = _first(row, *_TEXT_COLS)
    texts = [str(text_val).strip()] if text_val else []
    return PublicRecord(
        external_id=row_id,
        texts=texts,
        is_bot=is_bot,
        follower_count=to_count(_first(row, *_FOLLOWER_COLS)),
        following_count=to_count(_first(row, *_FOLLOWING_COLS)),
        account_age_days=to_count(row.get("account_age_days")),
        handle=row_id,
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register_adapter(DatasetAdapter(
    name="ai_vs_human_text_v1", kind="text",
    match=lambda h, f: 12 if _subset(h, "text", "label", "prompt", "model") else 0,
    parse_row=_parse_text_v1,
    description="id,text,label(AI-generated/Human-written),prompt,model,date",
))

register_adapter(DatasetAdapter(
    name="ai_vs_human_text_2026", kind="text",
    match=lambda h, f: 14 if _subset(h, "text_content", "label", "source_model", "generation_method") else 0,
    parse_row=_parse_text_2026,
    description="text_id,label(ai/human),source_model,domain,text_content,...",
))

register_adapter(DatasetAdapter(
    name="ai_human_detection_v1", kind="text",
    match=lambda h, f: 13 if _subset(h, "text", "human_or_ai", "source_model") else 0,
    parse_row=_parse_text_detection_v1,
    description="id,text,human_or_ai(human/ai),source_model,domain,language,...",
))

register_adapter(DatasetAdapter(
    name="text_generic", kind="text",
    match=lambda h, f: 1 if (_any_in(h, _TEXT_COLS) and _any_in(h, _TEXT_LABEL_COLS)) else 0,
    parse_row=_parse_text_generic,
    description="Fallback: any text column + any AI/human label column.",
))

register_adapter(DatasetAdapter(
    name="fake_social_media", kind="accounts",
    match=lambda h, f: 14 if _subset(h, "is_fake", "followers", "following", "account_age_days") else 0,
    parse_row=_parse_fake_social_media,
    description="Behavioral fake-account features + is_fake label.",
))

register_adapter(DatasetAdapter(
    name="twitter_user_features", kind="accounts",
    match=lambda h, f: 13 if _subset(h, "screen_name", "followers_count", "friends_count", "statuses_count") else 0,
    parse_row=_parse_twitter_user,
    needs_filename_label=True,
    description="Twitter account features; label from filename (fake_/real_).",
))

register_adapter(DatasetAdapter(
    name="reddit_dead_internet", kind="accounts",
    match=lambda h, f: 13 if _subset(h, "is_bot_flag", "account_age_days", "user_karma") else 0,
    parse_row=_parse_reddit,
    description="Reddit comment-level bot flags + account age.",
))

register_adapter(DatasetAdapter(
    name="accounts_generic", kind="accounts",
    match=lambda h, f: 1 if _any_in(h, _ACCOUNT_LABEL_COLS) and (
        _any_in(h, _FOLLOWER_COLS) or _any_in(h, _FOLLOWING_COLS)
        or "account_age_days" in h or _any_in(h, _TEXT_COLS)
    ) else 0,
    parse_row=_parse_accounts_generic,
    description="Fallback: a bot/fake label column + a behavioral or text column.",
))
