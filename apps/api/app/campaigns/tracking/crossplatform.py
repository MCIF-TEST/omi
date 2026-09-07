"""Recognising one operation running on two platforms.

An X account id and a YouTube channel id never match, and nothing in this system links a person's
accounts across platforms. So a cross-platform claim can only ever rest on **what the accounts did**,
never on who they are.

THE RULE, and it is short on purpose:

    A cross-platform edge may only be created by a platform-neutral family.

Text, network and timing are platform-neutral: the same script, the same referral link, the same
arrival minute mean the same thing wherever they happen. Infrastructure and identity are not.
``client_signature`` reads an X-only field that YouTube does not expose, so "both accounts publish
through the same client" cannot even be evaluated across platforms. ``handle_template`` is worse
than unavailable: handle conventions differ per platform, so a shared skeleton across two platforms
is evidence of the platforms' naming rules rather than of the accounts.

The consequence is that every cross-platform finding rests on evidence a reader can check on both
sides, which is the standard a claim about a person on two services has to meet.
"""

from __future__ import annotations

from app.campaigns.detector.types import (
    FAMILY_NETWORK,
    FAMILY_TEXT,
    FAMILY_TIMING,
)

#: The families whose evidence means the same thing on any platform. Anything not in here may only
#: link two accounts on the SAME platform.
PLATFORM_NEUTRAL_FAMILIES: frozenset[str] = frozenset({
    FAMILY_TEXT, FAMILY_NETWORK, FAMILY_TIMING,
})

_SEP = ":"


def global_key(platform: str, external_id: str) -> str:
    """The deployment-wide identifier for one account.

    Namespaced by platform because ``UC123`` on YouTube and ``UC123`` on X are different accounts
    and every global table in this codebase is already keyed ``(platform, external_id)``. Collapsing
    them would silently merge two strangers.
    """
    return f"{(platform or 'unknown').strip().lower()}{_SEP}{external_id}"


def split_key(key: str) -> tuple[str, str]:
    """Inverse of `global_key`. An unnamespaced id is treated as unknown-platform rather than
    raising, so a value written before namespacing still reads."""
    platform, sep, external = key.partition(_SEP)
    if not sep:
        return "unknown", key
    return platform, external


def may_link(platform_a: str, platform_b: str, family: str) -> bool:
    """Whether this family is allowed to connect these two accounts."""
    if (platform_a or "").lower() == (platform_b or "").lower():
        return True
    return family in PLATFORM_NEUTRAL_FAMILIES


def filter_cross_platform(edges: list, platform_of) -> list:
    """Drop edges that a platform-specific family tried to draw across platforms.

    ``platform_of`` maps an account id to its platform. Applied as a filter rather than inside each
    signal so the rule lives in exactly one place: seven signals each remembering it is seven
    chances to forget.

    NOTHING CALLS THIS WRAPPER, and that is safe rather than a latent drift. The live path is
    `detector/run.py::_drop_illegal_cross_platform`, which applies `may_link` over the same edges in
    the same way. Both sides call the SAME predicate, so the rule really does live in one place and
    the duplicate here is a spelling of it rather than a second copy of it. Were the rule itself
    inlined into either caller, this repo's usual drift would apply; it is not.
    """
    kept = []
    for e in edges:
        if may_link(platform_of(e.a), platform_of(e.b), e.family):
            kept.append(e)
    return kept
