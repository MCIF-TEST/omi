"""Synthetic corpora for the network detector.

Written to be ARGUED WITH rather than to pass. Each generator is a claim about what a real
population looks like, and the controls exist because each one has, somewhere, been mistaken for a
bot network by a real detector.

The generators produce persisted-scan-shaped dicts, so the tests exercise the real extraction path
rather than hand-built feature sets. A test that constructs features directly cannot catch a bug in
the thing that builds them, which is where most of the false positives live.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
BASE = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)

_TOPICS = [
    "the new transit plan will not fix downtown congestion at all",
    "watched the debate last night and nobody answered the housing question",
    "our local council keeps approving these developments without any parking",
    "the stadium deal is a terrible use of public money in my honest opinion",
    "school board meeting ran four hours and resolved absolutely nothing again",
    "third power outage this month and the utility keeps blaming the weather",
    "grocery prices here have gone up more than wages for three years running",
    "the bike lane pilot actually seems to be working better than expected",
]

_WORDS = (
    "honestly really quite frankly clearly obviously apparently seriously actually genuinely "
    "somewhat rather fairly pretty absolutely completely totally utterly"
).split()


def _sentence(rng: random.Random) -> str:
    """A human-ish comment: a topic with idiosyncratic filler, so no two are identical."""
    base = rng.choice(_TOPICS)
    words = base.split()
    for _ in range(rng.randint(1, 3)):
        words.insert(rng.randrange(len(words)), rng.choice(_WORDS))
    return " ".join(words)


def _post(text: str, when: datetime, *, client=None, parent=None, reply=None,
          repost=None) -> dict:
    return {
        "text": text,
        "created_at": when.isoformat(),
        "parent_id": parent,
        "reply_to_id": reply,
        "source_client": client,
        "repost_of_id": repost,
    }


def _account(
    ext: str, *, posts: list[dict], bio: str = "", created: datetime | None = None,
    handle: str | None = None, score: float = 20.0, tier: str = "low",
) -> dict:
    return {
        "external_id": ext,
        "handle": handle or ext,
        "platform": "x",
        "bio": bio,
        "account_created_at": (created or BASE - timedelta(days=900)).isoformat(),
        "recent_activity": posts,
        "thread_comments": [],
        "omi_score": score,
        "tier": tier,
    }


def organic_population(n: int = 60, *, seed: int = 7) -> list[dict]:
    """Ordinary people. Different phrasing, different rhythms, different signup dates.

    This is the background every control needs and the corpus the falsification test shuffles.
    """
    rng = random.Random(seed)
    out = []
    for i in range(n):
        # A human rhythm: irregular gaps, a real sleep window, an individual signup date.
        wake = rng.randint(6, 10)
        t = BASE - timedelta(days=rng.randint(1, 30)) + timedelta(hours=wake)
        posts = []
        for _ in range(rng.randint(12, 26)):
            t = t + timedelta(minutes=rng.randint(20, 600))
            if t.hour < wake or t.hour > wake + 13:      # sleep
                t = t.replace(hour=wake) + timedelta(days=1)
            posts.append(_post(_sentence(rng), t, client=rng.choice(
                ["Twitter for iPhone", "Twitter Web App", "Twitter for Android"])))
        out.append(_account(
            f"org{i:03d}",
            posts=posts,
            bio=f"{rng.choice(['dad', 'nurse', 'teacher', 'engineer', 'retired'])} in the city",
            created=BASE - timedelta(days=rng.randint(200, 3000)),
            handle=f"{rng.choice(['sam', 'alex', 'jo', 'kim', 'pat'])}{rng.randint(1, 999)}",
        ))
    return out


#: The behavioural signature of ONE operator: the things a formation keeps doing across runs.
#:
#: THE SEED DOES NOT VARY ANY OF THIS, AND THAT MATTERED. Every one of these was hardcoded, so
#: `planted_operation(seed=6)` and `planted_operation(seed=99)` produced two account sets running
#: the SAME operation: same script, same publishing tool, same signup week, same campaign targets,
#: same bio, same handle factory. The seed varied only filler text and jitter.
#:
#: Nothing noticed, because every test asked "was the operation found" and none asked "was it told
#: apart from a different one". That is unaskable without this parameter, and it is exactly the
#: question `app/netdetect/assign.py` has to answer: an account belongs to THIS formation, not to
#: some other one that also happens to be automated.
OPERATORS: dict[str, dict] = {
    # The original, kept byte-identical so every existing corpus and every pinned measurement in
    # `test_netdetect.py` stays exactly what it was.
    "stadium": {
        "script": "the stadium deal is a terrible use of public money in my honest opinion",
        "client": "SocialPilot",
        "bio": "views my own | follow for updates",
        "handle": lambda i: f"news_watch_{1000 + i * 7}",
        "signup_days_ago": 40,
        "target": lambda j: f"campaign_post_{j % 3}",
        "interval_minutes": 62,
    },
    # A genuinely different operator: different script, tool, factory, provisioning window and
    # targets. Shares only the fact of being automated, which is the whole point.
    "clinic": {
        "script": "the new clinic closure leaves this whole district without any urgent care",
        "client": "BulkPoster Studio",
        "bio": "health advocate | opinions are mine alone",
        "handle": lambda i: f"care_voice{4200 + i * 3}",
        "signup_days_ago": 300,
        "target": lambda j: f"health_thread_{j % 4}",
        "interval_minutes": 37,
    },
}


def planted_operation(
    size: int = 8, *, seed: int = 99, discipline: float = 0.0, prefix: str = "op",
    operator: str = "stadium",
) -> list[dict]:
    """An operation, with a dial for how well run it is.

    ``discipline`` from 0 (sloppy: shared copy, one scheduler, one signup week, template handles)
    to 1 (competent: individually written posts, ordinary clients, aged accounts, human handles).
    The dilution curve over this dial IS the honest product claim, so the dial is the point of the
    generator rather than a convenience.

    ``operator`` selects WHICH operation this is. Two calls with different operators are two
    different adversaries; two calls with the same operator and different seeds are two runs of one
    adversary, which is what makes rotation and cross-run assignment testable at all.
    """
    rng = random.Random(seed)
    op = OPERATORS[operator]
    shared_line = op["script"]
    signup = BASE - timedelta(days=op["signup_days_ago"])
    out = []

    for i in range(size):
        sloppy = rng.random() >= discipline
        t = BASE - timedelta(days=rng.randint(1, 20))
        posts = []
        for j in range(rng.randint(14, 22)):
            # A scheduler: near-constant interval, no sleep window.
            t = t + (timedelta(minutes=op["interval_minutes"]) if sloppy
                     else timedelta(minutes=rng.randint(30, 500)))
            text = shared_line if (sloppy and j % 5 == 0) else _sentence(rng)
            posts.append(_post(
                text, t,
                client=op["client"] if sloppy else rng.choice(
                    ["Twitter for iPhone", "Twitter Web App"]),
                parent=op["target"](j) if sloppy else None,
            ))
        out.append(_account(
            f"{prefix}{i:03d}",
            posts=posts,
            bio=op["bio"] if sloppy else "just here for the local news",
            created=(signup + timedelta(hours=i * 3)) if sloppy
            else BASE - timedelta(days=rng.randint(400, 2500)),
            handle=(op["handle"](i) if sloppy
                    else f"{rng.choice(['chris', 'dana', 'rob'])}{rng.randint(1, 999)}"),
            score=30.0, tier="moderate",
        ))
    return out


# --------------------------------------------------------------------------------------------- #
# The controls. Each one is a real population that a naive detector calls a bot network.
# --------------------------------------------------------------------------------------------- #

def professional_beat(n: int = 10, *, seed: int = 21) -> list[dict]:
    """Reporters covering one story. Same topic, same working hours, same publishing tools.

    The shape that once scored unrelated journalists at 1.0 in this codebase's own history.
    """
    rng = random.Random(seed)
    out = []
    for i in range(n):
        t = BASE - timedelta(days=14) + timedelta(hours=9)
        posts = []
        for _ in range(rng.randint(18, 28)):
            t = t + timedelta(minutes=rng.randint(25, 180))
            if t.hour > 19:
                t = t.replace(hour=9) + timedelta(days=1)
            posts.append(_post(
                "the stadium deal " + _sentence(rng), t, client="TweetDeck"))
        out.append(_account(
            f"press{i:03d}", posts=posts,
            bio="city hall reporter at the local paper",
            created=BASE - timedelta(days=rng.randint(1500, 4000)),
            handle=f"{rng.choice(['j', 'm', 'r'])}{rng.choice(['smith', 'lopez', 'chen'])}",
        ))
    return out


def fan_community(n: int = 12, *, seed: int = 33) -> list[dict]:
    """A fandom. Shared vocabulary, shared targets, and they all joined when the thing launched.

    Real communities also talk TO each other, which is the property that should keep them apart from
    a broadcast array.
    """
    rng = random.Random(seed)
    launch = BASE - timedelta(days=60)
    out = []
    ids = [f"fan{i:03d}" for i in range(n)]
    for i in range(n):
        t = BASE - timedelta(days=rng.randint(1, 25))
        posts = []
        for _ in range(rng.randint(15, 30)):
            t = t + timedelta(minutes=rng.randint(15, 400))
            posts.append(_post(
                f"the new season is {rng.choice(['incredible', 'so good', 'unreal'])} " + _sentence(rng),
                t,
                client=rng.choice(["Twitter for iPhone", "Twitter for Android"]),
                reply=rng.choice([x for x in ids if x != ids[i]]),
            ))
        out.append(_account(
            f"fan{i:03d}", posts=posts,
            bio="she/her | fan account | dms open",
            created=launch + timedelta(days=rng.randint(0, 20)),
            handle=f"{rng.choice(['stan', 'luvs', 'daily'])}_{rng.choice(['ari', 'mika', 'zed'])}",
        ))
    return out


def amplifier_ring(size: int = 8, *, seed: int = 61, targets: int = 3,
                   reposts: bool = True) -> list[dict]:
    """An operation whose tell is WHAT IT REBROADCASTS, plus one shared tool.

    Deliberately clean on every other axis: individually written posts, signup dates spread over
    years, plain handles, human rhythms. Two things are shared, and the pairing is the point:

    * a publishing client (infrastructure, weight 0.55) - soft, because a shared tool can simply be
      a shared profession, and on its own it is one family and cannot be reported at all;
    * the specific outside posts they amplify (network, weight 1.00) - one of the two families whose
      innocent sharing is implausible.

    ``reposts=False`` builds the identical corpus with the amplification not recorded, which is the
    counterfactual: same accounts, same text, same timing, same tool, and nothing to find.
    """
    rng = random.Random(seed)
    amplified = [f"outside_post_{i}" for i in range(targets)]
    rows: list[dict] = []
    for i in range(size):
        posts = []
        for j in range(6):
            when = BASE - timedelta(hours=rng.randrange(1, 900))
            target = amplified[j] if (reposts and j < targets) else None
            posts.append(_post(_sentence(rng), when, client="amplifyhub", repost=target))
        rows.append(_account(
            f"amp{i}",
            posts=posts,
            bio=_sentence(rng),
            created=BASE - timedelta(days=rng.randrange(400, 3000)),
            handle=rng.choice(["quietfern", "marchbird", "oldpier", "stonewell",
                               "lanterns", "cedarpath", "riverkiln", "duskmoor"]) + str(i),
        ))
    return rows
