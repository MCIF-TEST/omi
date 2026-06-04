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
    days_since,
    label_hint_from_filename,
    parse_bool_label,
    parse_datetime,
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
# Per-tweet timeline files (Cresci-2017 genuine/bot tweets, Known-Mixed
# timelines): a user-id column + a tweet-text column, one row per tweet.
_TWEET_TEXT_COLS = ("tweet_text", "full_text", "text", "tweet", "content")
_USER_ID_COLS = ("user_id", "userid", "author_id", "tweet_user_id")


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
    # A handful of rows captured an API failure ("Error: 400 Client Error ...")
    # instead of generated text. Skip just those so the file no longer has to be
    # quarantined wholesale for ~1% poisoned rows.
    if text.startswith("Error:") or "Client Error:" in text:
        return None
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


def _parse_io_disclosure(row: dict, filename: str, row_id: str) -> PublicRecord | None:
    """State-backed information-operation disclosure (e.g. the Twitter/X
    Transparency releases, Stanford Internet Observatory mirrors).

    Every account in these archives was attributed to a coordinated influence
    operation by the platform itself — the highest-confidence inauthentic
    ground truth that exists. We label them ``political_coord`` / ``high``
    rather than the generic ``bot`` so the corpus distinguishes coordinated
    amplification from lone automation. The campaign is taken from the file
    stem so multiple disclosure files stay attributable.
    """
    user_id = str(row.get("userid") or row.get("user_id") or "").strip()
    if not user_id:
        return None
    text = str(row.get("tweet_text") or row.get("text") or "").strip()
    handle = str(row.get("user_screen_name") or row.get("user_display_name") or user_id).strip()
    campaign = filename.rsplit(".", 1)[0]
    # Real per-tweet time (kept aligned with texts) + real account age, so the
    # temporal and profile detectors see genuine cadence/age instead of the
    # synthetic 1-hour spread. The richer coordination columns (retweet/mention/
    # hashtag graphs) are deliberately left for the Phase-2 coordination path.
    when = parse_datetime(row.get("tweet_time"))
    return PublicRecord(
        external_id=user_id,                     # collapses a user's tweets to one account
        texts=[text] if text else [],
        post_times=[when] if text else [],
        is_bot=True,
        follower_count=to_count(row.get("follower_count")),
        following_count=to_count(row.get("following_count")),
        account_age_days=days_since(row.get("account_creation_date")),
        handle=handle or user_id,
        label="political_coord",
        expected_tier="high",
        campaign_id=campaign,
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
    name="io_disclosure", kind="accounts",
    match=lambda h, f: 15 if (
        ("userid" in h or "user_id" in h)
        and ("tweet_text" in h or "text" in h)
        and _any_in(h, ("follower_count", "following_count", "account_creation_date"))
    ) else 0,
    parse_row=_parse_io_disclosure,
    description="State-backed IO disclosure (Twitter/X Transparency); labels accounts political_coord/high.",
))


def _tweet_label_from_filename(filename: str) -> str | None:
    """Resolve the ground-truth label of a per-tweet timeline file from its name.

    Returns ``"bot"`` / ``"human"`` / ``None``. Known-Mixed timelines
    (legitimate-but-coordination-shaped: journalists, brands, ...) are named
    ``*mixed*`` and treated as ``human`` — the directive is explicit that the
    goal is *not* to label them bad, only to measure behavior. Their category is
    preserved via ``campaign_id`` (the file stem) for cohort evaluation.
    """
    f = filename.lower()
    if "mixed" in f:
        return "human"
    hint = label_hint_from_filename(filename)  # True=inauthentic, False=authentic
    if hint is True:
        return "bot"
    if hint is False:
        return "human"
    return None


def _parse_labeled_tweets(row: dict, filename: str, row_id: str) -> PublicRecord | None:
    """Per-tweet timeline with the label in the FILENAME (not a column).

    Covers Cresci-2017 ``genuine_accounts``/spambot tweet exports and the
    Known-Mixed timelines. One row per tweet → one record per tweet sharing the
    account's ``user_id``; :func:`coalesce_records` then merges them so the
    engine sees the account's whole text corpus (the win over the profile-only
    ``twitter_user_features`` adapter, which carries no text). Unlike
    ``io_disclosure`` this does NOT hard-label coordination — genuine accounts
    stay ``human``/``low``.
    """
    label = _tweet_label_from_filename(filename)
    if label is None:
        return None
    uid = str(_first(row, *_USER_ID_COLS) or "").strip()
    text = str(_first(row, *_TWEET_TEXT_COLS) or "").strip()
    if not uid or not text:
        return None
    is_bot = label == "bot"
    return PublicRecord(
        external_id=uid,                 # collapses a user's tweets to one account
        texts=[text],
        is_bot=is_bot,
        handle=uid,
        label=label,
        expected_tier=("high" if is_bot else "low"),
        campaign_id=filename.rsplit(".", 1)[0],
    )


def _strip_bytes_repr(s: str) -> str:
    """Unwrap a Python ``str(bytes)`` artifact: ``b'text'`` / ``b"text"`` → ``text``.
    Twitter_Data.csv was written this way; the FE/Joined variants are clean."""
    if len(s) >= 3 and s[:2] in ("b'", 'b"') and s[-1] == s[1]:
        return s[2:-1]
    return s


def _parse_twitterdata(row: dict, filename: str, row_id: str) -> PublicRecord | None:
    """TwitterData_* — per-tweet rows for 96 deep-timeline accounts.

    Two corrections the audit identified are applied here:
    * **Inverted polarity** — ``Label 1 = human``, ``0 = bot`` (verified:
      @MuseumBot=0, @SadiqKhan=1). The generic account adapter would read ``1``
      as inauthentic and mislabel every account, so this dedicated adapter owns
      the mapping.
    * **Corrupted text** — strip the ``b'...'`` bytes-repr wrapper.

    Account identity (``Twitter_Account``) and the real per-tweet timestamp are
    preserved, so the rows collapse to one account scored on its genuine
    timeline. Verified legitimate accounts are tagged as a Known-Mixed cohort.
    """
    acct = str(row.get("twitter_account") or row.get("twitter_user_name") or "").strip()
    text = _strip_bytes_repr(str(row.get("tweet_text") or "").strip())
    raw = str(row.get("label") or "").strip()
    if not acct or not text or raw not in ("0", "1"):
        return None
    is_human = raw == "1"
    verified = str(row.get("verified") or "").strip().lower() in ("1", "true")
    when = parse_datetime(row.get("tweet_created_at"))
    return PublicRecord(
        external_id=acct,                # collapses a user's tweets to one account
        texts=[text],
        post_times=[when],
        is_bot=not is_human,
        follower_count=to_count(row.get("followers")),
        following_count=to_count(row.get("following")),
        handle=acct,
        label=("human" if is_human else "bot"),
        expected_tier=("low" if is_human else "high"),
        # High-profile authentic accounts that may *look* coordinated → the
        # Known-Mixed FPR cohort. Tagged only for verified humans.
        campaign_id=("twitterdata_verified_mixed" if (is_human and verified) else None),
    )


def _parse_astroturf(row: dict, filename: str, row_id: str) -> PublicRecord | None:
    """OSoMe astroturf set — headerless `account_id<TAB>label` (label is
    'political_Bot'). Confirmed automated political accounts → bot ground truth.
    Text lives elsewhere, so these are label-only accounts (useful for the ML /
    memory tracks + bot recall)."""
    uid = str(row.get("_0") or "").strip()
    if not uid.isdigit():
        return None
    return PublicRecord(external_id=uid, texts=[], is_bot=True, handle=uid, label="bot")


def _parse_cresci(row: dict, filename: str, row_id: str) -> PublicRecord | None:
    """Cresci RTbust-2019 — headerless `account_id<TAB>label` (human|bot). The
    tweet text is in the sibling `_tweets.json` (joinable later); label-only for
    now."""
    uid = str(row.get("_0") or "").strip()
    if not uid.isdigit():
        return None
    label = str(row.get("_1") or "").strip().lower()
    is_bot = label in ("bot", "1", "true")
    return PublicRecord(
        external_id=uid, texts=[], is_bot=is_bot, handle=uid,
        label=("bot" if is_bot else "human"),
    )


register_adapter(DatasetAdapter(
    name="astroturf", kind="accounts", has_header=False,
    match=lambda h, f: 16 if "astroturf" in f.lower() else 0,
    parse_row=_parse_astroturf,
    description="OSoMe astroturf political bots (headerless id+label TSV) → bot.",
))

def _is_headerless_id_label(h: set) -> bool:
    """The headerless id+label signature: the 'header' is really the first data
    row, so it has no recognizable column names (no user_id / text / follower /
    screen_name columns). Distinguishes the RTbust TSV from a headered
    Cresci-2017 tweets/users export that merely has 'cresci' in its name."""
    known = set(_USER_ID_COLS) | set(_TWEET_TEXT_COLS) | set(_FOLLOWER_COLS) \
        | set(_FOLLOWING_COLS) | {"screen_name", "id", "name", "statuses_count"}
    return not (h & known)


register_adapter(DatasetAdapter(
    name="cresci_rtbust", kind="accounts", has_header=False,
    match=lambda h, f: 16 if (
        "cresci" in f.lower() and f.lower().endswith((".tsv", ".csv"))
        and "rtbust" in f.lower() and _is_headerless_id_label(h)
    ) else 0,
    parse_row=_parse_cresci,
    description="Cresci RTbust-2019 human/bot labels (headerless id+label TSV).",
))

register_adapter(DatasetAdapter(
    name="labeled_tweets", kind="accounts",
    match=lambda h, f: 16 if (
        _any_in(h, _USER_ID_COLS) and _any_in(h, _TWEET_TEXT_COLS)
        and _tweet_label_from_filename(f) is not None
        # Stay disjoint from io_disclosure: any of its column triad means this is
        # a state-IO disclosure file, which it owns (and labels political_coord)
        # regardless of a spurious filename token like "ai" inside "campaign".
        and not _any_in(h, ("follower_count", "following_count", "account_creation_date"))
    ) else 0,
    parse_row=_parse_labeled_tweets,
    description="Per-tweet timeline + filename label (Cresci-2017 genuine/bot, "
                "Known-Mixed); collapses to accounts WITH text.",
))

register_adapter(DatasetAdapter(
    name="twitterdata", kind="accounts",
    match=lambda h, f: 15 if _subset(h, "twitter_account", "tweet_text", "label") else 0,
    parse_row=_parse_twitterdata,
    description="TwitterData human/bot timelines (Label 1=human/0=bot, inverted; "
                "b''-text stripped); per-tweet text+time -> deep-timeline accounts.",
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
