"""Synthetic ground-truth corpus — known-answer cases the engine is measured against.

Public archives give us real *inauthentic* accounts (bot datasets, influence-
operation disclosures), but they are weak on the cases that actually break a
naive detector: legitimate accounts that *look* suspicious. A genuine non-native
English speaker, a real person who runs every comment through a grammar tool, a
fan community that all posts within the same five minutes around a premiere —
these are organic, yet the surface features (templated-looking phrasing, tight
timing, low personal-voice scores) resemble coordination. If the only "human"
examples in our corpus are tidy native-English essays, we will calibrate the
engine to flag the very users we must protect.

This module manufactures a deterministic, labeled corpus covering both sides:

  inauthentic (expected tier high)        authentic (expected tier low)
  ────────────────────────────────        ──────────────────────────────
  coordinated_io   political_coord        organic_human       human
  engagement_farm  engagement_farm        esl_human           human   ← FP guard
  commercial_spam  commercial_spam        ai_assisted_human   human   ← FP guard

Every record is a :class:`~app.ml.public_import.PublicRecord` carrying an
explicit ``label`` / ``expected_tier``, so it flows through the *same*
``ingest_records`` path as live scans and public imports — no train/serve skew.
Generation is seeded, so the corpus is reproducible and diffable: the same seed
always yields the same accounts, which makes it usable as a regression fixture
in CI as well as a DB-resident ground-truth set.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

from app.ml.public_import import PublicRecord


@dataclass(frozen=True)
class Persona:
    """A behavioral archetype the generator can mint accounts for."""

    name: str
    label: str            # schemas.LABEL_KINDS value
    expected_tier: str    # low | moderate | elevated | high
    is_bot: bool          # binary back-compat flag (inauthentic?)
    description: str
    build: "Callable[[random.Random, int], PublicRecord]"


# ---------------------------------------------------------------------------
# Text banks. Kept deliberately small and varied — the goal is realistic
# *shape* (template reuse vs. organic variety, native vs. non-native phrasing),
# not volume.
# ---------------------------------------------------------------------------

_IO_TEMPLATES = [
    "The {actor} will never tell you the truth about {topic}.",
    "Wake up — {topic} is exactly what {actor} wants you distracted from.",
    "Why is no one talking about {topic}? {actor} is hiding it.",
    "They call it {topic} but real patriots know what {actor} is doing.",
    "Share this before {actor} takes it down. {topic} affects us all.",
]
_IO_ACTORS = ["the mainstream media", "the establishment", "big tech", "the elites", "the regime"]
_IO_TOPICS = ["the election", "the new policy", "the economy", "the border", "the vaccine rollout"]

_FARM_POSTS = [
    "Great video!! 🔥🔥", "Love this so much ❤️", "First!!", "Who's here in 2026?",
    "Amazing content keep it up 👏", "This deserves more views!", "Wow just wow",
    "Subbed! check out my channel too", "Best video ever 💯", "Notification squad where you at",
]

_SPAM_POSTS = [
    "Make $5000/week from home — link in my bio 💸",
    "Use code SAVE20 at checkout for 20% off, dont miss out!!",
    "I made 3x my money on $PEPE this week, DM me how",
    "Check out my channel for free giveaways 🎁🎁",
    "Best VPN deal of the year, click here: bit.ly/xxxxx",
    "Grow your followers fast — 10k for $9.99, guaranteed",
]

# Organic native-English commenters: casual, typo-prone, varied topics, opinions.
_ORGANIC_POSTS = [
    "honestly the second half lost me a bit but the intro was great",
    "wait did anyone else notice the audio cut out around 4:12?",
    "ok the bit about the supply chain actually changed my mind lol",
    "been following this channel for 3 years and this is your best one",
    "idk i disagree, my experience renting in that city was way worse",
    "the editing on this is insane, how long did it take you",
    "came back to rewatch after the news today, holds up",
    "my dog started barking at the music part 😂 anyway good vid",
]

# Genuine non-native English: real opinions, but article drops, tense slips,
# direct translations. These MUST be labeled human/low — they are the primary
# false-positive class the engine has to learn to leave alone.
_ESL_POSTS = [
    "I am watching from Brazil, this video help me very much for understand the topic",
    "In my country we have same problem since long time, is not easy to fix",
    "Thank you for explain, my english is not perfect but i understand all what you say",
    "I think you are right but also is more complicated than this in real life situation",
    "First time i see your channel, i will subscribe because the information is very useful",
    "Where i live the price is much higher, maybe is different because of the import tax",
    "My friend send me this video and now i watch all the time, greeting from Indonesia",
    "This is interesting but i want to know more about how it work in the practice",
]

# Real person who polishes with an AI/grammar tool: clean, structured, but the
# content is personal and the topics vary. Labeled human/low — the second
# false-positive class (clean prose != automation).
_AI_ASSISTED_POSTS = [
    "Thank you for such a clear explanation. I've struggled with this concept for years, and your breakdown finally made it click.",
    "I appreciate the nuance here. As someone who works in this field, I can confirm that the second point is especially underrated.",
    "This resonated with me. I went through something similar last year, and I wish I'd had this perspective at the time.",
    "Well argued, though I'd gently push back on the third example — the data in my region tells a slightly different story.",
    "Saving this to share with my team on Monday. The framework you outlined maps almost perfectly onto a problem we're facing.",
    "A thoughtful video as always. It prompted me to reconsider an assumption I hadn't questioned in a long while.",
]


def _pick_some(rng: random.Random, bank: list[str], lo: int, hi: int) -> list[str]:
    k = rng.randint(lo, min(hi, len(bank)))
    return rng.sample(bank, k)


def _build_coordinated_io(rng: random.Random, i: int) -> PublicRecord:
    # A cell account: a handful of slot-filled variations on a fixed narrative,
    # near-zero personal content, fresh account, follows many / followed by few.
    actor = rng.choice(_IO_ACTORS)
    topic = rng.choice(_IO_TOPICS)
    templates = _pick_some(rng, _IO_TEMPLATES, 3, 5)
    texts = [t.format(actor=actor, topic=topic) for t in templates]
    campaign = f"synthetic-io-{abs(hash((actor, topic))) % 97:02d}"
    return PublicRecord(
        external_id=f"coordinated_io_{i}",
        texts=texts,
        is_bot=True,
        follower_count=rng.randint(0, 25),
        following_count=rng.randint(400, 3000),
        account_age_days=rng.randint(1, 30),
        handle=f"patriot{rng.randint(1000, 9999)}",
        label="political_coord",
        expected_tier="high",
        campaign_id=campaign,
    )


def _build_engagement_farm(rng: random.Random, i: int) -> PublicRecord:
    return PublicRecord(
        external_id=f"engagement_farm_{i}",
        texts=_pick_some(rng, _FARM_POSTS, 4, 7),
        is_bot=True,
        follower_count=rng.randint(50, 400),
        following_count=rng.randint(2000, 8000),
        account_age_days=rng.randint(15, 200),
        handle=f"sub4sub_{rng.randint(100, 999)}",
        label="engagement_farm",
        expected_tier="high",
    )


def _build_commercial_spam(rng: random.Random, i: int) -> PublicRecord:
    return PublicRecord(
        external_id=f"commercial_spam_{i}",
        texts=_pick_some(rng, _SPAM_POSTS, 3, 6),
        is_bot=True,
        follower_count=rng.randint(0, 100),
        following_count=rng.randint(100, 1500),
        account_age_days=rng.randint(1, 90),
        handle=f"deals_{rng.randint(1000, 9999)}",
        label="commercial_spam",
        expected_tier="high",
    )


def _build_organic_human(rng: random.Random, i: int) -> PublicRecord:
    return PublicRecord(
        external_id=f"organic_human_{i}",
        texts=_pick_some(rng, _ORGANIC_POSTS, 3, 6),
        is_bot=False,
        follower_count=rng.randint(20, 1500),
        following_count=rng.randint(30, 800),
        account_age_days=rng.randint(180, 3500),
        handle=f"user_{rng.randint(1000, 99999)}",
        label="human",
        expected_tier="low",
    )


def _build_esl_human(rng: random.Random, i: int) -> PublicRecord:
    return PublicRecord(
        external_id=f"esl_human_{i}",
        texts=_pick_some(rng, _ESL_POSTS, 3, 6),
        is_bot=False,
        follower_count=rng.randint(5, 600),
        following_count=rng.randint(40, 1200),
        account_age_days=rng.randint(90, 2500),
        handle=f"viewer{rng.randint(100, 9999)}",
        label="human",
        expected_tier="low",
    )


def _build_ai_assisted_human(rng: random.Random, i: int) -> PublicRecord:
    return PublicRecord(
        external_id=f"ai_assisted_human_{i}",
        texts=_pick_some(rng, _AI_ASSISTED_POSTS, 3, 5),
        is_bot=False,
        follower_count=rng.randint(50, 5000),
        following_count=rng.randint(60, 1000),
        account_age_days=rng.randint(200, 4000),
        handle=f"prof_{rng.randint(100, 999)}",
        label="human",
        expected_tier="low",
    )


PERSONAS: tuple[Persona, ...] = (
    Persona(
        name="coordinated_io", label="political_coord", expected_tier="high", is_bot=True,
        description="State-style amplifier: slot-filled narrative variations, fresh account, lopsided follow ratio.",
        build=_build_coordinated_io,
    ),
    Persona(
        name="engagement_farm", label="engagement_farm", expected_tier="high", is_bot=True,
        description="Sub-for-sub / like-farm: generic praise, emoji spam, huge following-to-follower ratio.",
        build=_build_engagement_farm,
    ),
    Persona(
        name="commercial_spam", label="commercial_spam", expected_tier="high", is_bot=True,
        description="Dropshipping / crypto / promo-code spam with outbound links.",
        build=_build_commercial_spam,
    ),
    Persona(
        name="organic_human", label="human", expected_tier="low", is_bot=False,
        description="Baseline native-English commenter: casual, typo-prone, varied topics and opinions.",
        build=_build_organic_human,
    ),
    Persona(
        name="esl_human", label="human", expected_tier="low", is_bot=False,
        description="FALSE-POSITIVE GUARD: genuine non-native English speaker — real opinions, non-native grammar.",
        build=_build_esl_human,
    ),
    Persona(
        name="ai_assisted_human", label="human", expected_tier="low", is_bot=False,
        description="FALSE-POSITIVE GUARD: real person who polishes comments with a grammar/AI tool.",
        build=_build_ai_assisted_human,
    ),
)

PERSONAS_BY_NAME: dict[str, Persona] = {p.name: p for p in PERSONAS}


def generate_corpus(
    n_per_persona: int = 25,
    *,
    seed: int = 1729,
    personas: tuple[Persona, ...] = PERSONAS,
) -> list[PublicRecord]:
    """Mint a deterministic, labeled synthetic corpus.

    The same ``seed`` always produces the same records, so the corpus is a
    stable regression fixture as well as a DB-resident ground-truth set. Each
    persona is generated from its own derived sub-seed so that adding or
    reordering personas does not perturb the others' output.
    """
    if n_per_persona < 0:
        raise ValueError("n_per_persona must be >= 0")
    records: list[PublicRecord] = []
    for persona in personas:
        # Derive a per-persona seed so personas are independent and stable.
        rng = random.Random(f"{seed}:{persona.name}")
        for i in range(n_per_persona):
            records.append(persona.build(rng, i))
    return records


def corpus_label_distribution(records: list[PublicRecord]) -> dict[str, int]:
    """Count records by their asserted ground-truth label — for a quick
    "what did we just generate?" summary."""
    dist: dict[str, int] = {}
    for r in records:
        key = r.label or ("bot" if r.is_bot else "human")
        dist[key] = dist.get(key, 0) + 1
    return dist
