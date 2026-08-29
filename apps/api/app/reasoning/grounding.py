"""Check the analyst's per-account prose against the evidence it was given. Deterministically.

WHY THIS EXISTS. Every per-account paragraph this product generates is a published claim about a
named real person, and the product owner posts them into comment sections. Until now the only thing
holding that prose to the evidence was the protocol asking it to: the Governor's S9 lint sees the
investigation-level ``headline`` and ``assessment`` but NOT ``commenter_assessments[].assessment``,
and the comprehensive path runs ``adjudication="schema_only"``, so on the live route nothing at all
inspected the sentences that actually get screenshotted.

Asking a model nicely is not a control. This is the control.

The join point is where it belongs, because that is the one place holding BOTH sides: the model's
prose, and the account's ground truth (``recent_activity``, ``bio``, ``follower_count``,
``following_count``, ``account_created_at``, ``history_size``). Everything here is a comparison
between those two. No model call, no network, no heuristics about what "sounds" wrong.

WHAT IS CHECKED, and why each one earns its place:

* **Quotes.** The protocol's rule is "if you cannot quote it, you cannot claim it". So a quotation is
  the strongest thing in the paragraph and the most damaging if invented: it asserts a named person
  wrote words they never wrote. Every quoted span is matched against what that account actually
  posted. This is the check worth having if you only have one.
* **Figures.** ``_CHECKABLE_CLAIMS`` exists because LLMs are unreliable at ratio and date arithmetic
  and will cheerfully describe an imbalance that is not there. Forcing the number into the sentence
  made the error auditable; this makes it caught.
* **Banned phrasing**, now reaching the text it was always aimed at.
* **Boilerplate.** The schema says "never a boilerplate sentence repeated across accounts" and
  nothing measured it. A paragraph reused across five accounts is not five findings.
* **Readability.** The audience is a creator, not an analyst. Measurable, so measured.

SEVERITY. A HARD violation means the paragraph asserts something the evidence contradicts or cannot
support, so the paragraph does not get published: the caller replaces it and keeps the original for
an admin to inspect. SOFT violations are quality signals that inform confidence and the operator's
view of model health, and never suppress anything.

Deliberately NOT here: judging whether the score is right. That is the model's job and this module
has no opinion on it. This only asks whether the sentences describe the evidence that exists.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.governor.governor import BANNED_PHRASES

# A quotation shorter than this many WORDS is rhetorical ("engagement farming", "link in bio"), not
# an excerpt of a post. Words rather than characters, because character length does not separate the
# two: "engagement farming" is 18 characters and quotes no one. Five words is long enough that
# ordinary scare-quoting falls below it and a real excerpt does not.
MIN_CHECKABLE_QUOTE_WORDS = 5
# ...unless the quote is introduced as speech ("it wrote X"), which is an explicit claim about what
# the account said and is checkable however short it is. Three words, so "buy my course" is caught
# while a one-word emphasis is not.
MIN_ATTRIBUTED_QUOTE_WORDS = 3
# Counts are stated as figures, so they should match. The tolerance absorbs "about 4,200" for 4,210
# and nothing more.
COUNT_TOLERANCE = 0.05
# Age arithmetic runs against a clock that moved between the scan and this check.
AGE_TOLERANCE = 0.12
RATIO_TOLERANCE = 0.15
# Word 5-shingle overlap above which two per-account paragraphs are the same paragraph.
BOILERPLATE_JACCARD = 0.72
# Share of a batch that may open (or close) on one sentence shape before it is a template.
# A third is generous: some convergence is natural when every account is described from the
# same fields, and the rule is aimed at the runs where it was nearly all of them.
REPEATED_SENTENCE_SHARE = 0.34
# Mean words per sentence above which prose stops being readable by the person it is about.
MAX_MEAN_SENTENCE_WORDS = 30

#: Words that make a sentence sound authoritative to an analyst and opaque to everyone else. Kept
#: short and specific on purpose: this is not a style police, it is a list of terms a creator reading
#: about their own comment section will not know. "Probabilistic" is deliberately absent, since the
#: constitution requires probabilistic hedging and fighting it here would be incoherent.
JARGON = (
    "heuristic", "n-gram", "entropy", "corpus", "vector", "orthogonal", "provenance",
    "anomalous", "cadence", "signal-to-noise", "posterior", "prior probability",
    "feature space", "distributional",
)

_QUOTE_RE = re.compile(r'["“]([^"“”]{4,400})["”]')
#: A speech verb immediately before a quotation makes it an attributed claim about the account.
_SPEECH_VERB_RE = re.compile(
    r"\b(?:wrote|writes|written|posted|posts|posting|said|says|reads|replied|replies|"
    r"commented|comments|repeats|repeated|quoting)\b[^\w]*$", re.I)
_SENTENCE_SPLIT = re.compile(r"[.!?]+(?:\s|$)")
_WORD_RE = re.compile(r"[a-z0-9']+")

HARD = "hard"
SOFT = "soft"


@dataclass
class Violation:
    code: str
    severity: str
    detail: str


@dataclass
class GroundingReport:
    ref: str | None
    ok: bool
    violations: list[Violation] = field(default_factory=list)
    checked: dict = field(default_factory=dict)

    @property
    def hard(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == HARD]

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "hard": [{"code": v.code, "detail": v.detail} for v in self.hard],
            "soft": [{"code": v.code, "detail": v.detail}
                     for v in self.violations if v.severity == SOFT],
            "checked": self.checked,
        }


# --------------------------------------------------------------------------------------------- #
# Normalisation
# --------------------------------------------------------------------------------------------- #
def _norm(text: str) -> str:
    """Fold to a form where a quotation and its source match despite punctuation and spacing."""
    t = (text or "").lower()
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = re.sub(r"[^a-z0-9']+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _account_corpus(account: dict | None) -> str:
    """Everything this account actually wrote, as one normalised string."""
    if not isinstance(account, dict):
        return ""
    parts: list[str] = []
    for post in account.get("recent_activity") or []:
        if isinstance(post, dict) and post.get("text"):
            parts.append(str(post["text"]))
    if account.get("bio"):
        parts.append(str(account["bio"]))
    if account.get("handle"):
        parts.append(str(account["handle"]))
    return _norm(" \n ".join(parts))


# --------------------------------------------------------------------------------------------- #
# Quotes
# --------------------------------------------------------------------------------------------- #
def check_quotes(assessment: str, account: dict | None) -> list[Violation]:
    """Every quoted excerpt must appear in what the account actually posted.

    A quote the corpus cannot produce is the single most damaging output this system can generate: it
    puts words in a named person's mouth, and the reader has no way to know it is invented. It is
    also the easiest thing in the world to check, which is why it was worth building this module for
    on its own.

    Truncated quotes ("first half of the sentence…") are matched on the part before the ellipsis, so
    the honest shortening the protocol encourages is not punished.
    """
    corpus = _account_corpus(account)
    # "We collected nothing this account wrote" is a different fact from "we collected things and
    # this is not among them", and it deserves its own code. The handle is in the corpus for matching
    # but does not count as something the account WROTE.
    wrote_anything = bool(
        (account or {}).get("recent_activity") or (account or {}).get("bio")
    )
    out: list[Violation] = []
    for m in _QUOTE_RE.finditer(assessment or ""):
        raw = m.group(1)
        # Match on the portion before any ellipsis: the model is allowed to shorten.
        head = re.split(r"\.\.\.|…", raw)[0]
        needle = _norm(head)
        words = len(_WORD_RE.findall(needle))
        # Length alone is a weak discriminator between an excerpt and scare-quoting. A speech verb
        # just before the quote is a strong one: "it wrote X" is a claim about what the account said
        # whatever X's length, while "classic 'engagement farming' behaviour" is not. So a short
        # quote is checked when it is introduced as speech, and ignored otherwise.
        introduced_as_speech = bool(_SPEECH_VERB_RE.search(assessment[max(0, m.start() - 44):m.start()]))
        floor = MIN_ATTRIBUTED_QUOTE_WORDS if introduced_as_speech else MIN_CHECKABLE_QUOTE_WORDS
        if words < floor:
            continue  # rhetorical quoting, not an excerpt
        if not wrote_anything or not corpus:
            out.append(Violation(
                "quote_without_evidence", HARD,
                f'quoted "{raw[:60]}" but no posts or bio were collected for this account',
            ))
            continue
        if needle not in corpus:
            out.append(Violation(
                "quote_not_found", HARD,
                f'quoted "{raw[:60]}" does not appear in anything this account posted',
            ))
    return out


# --------------------------------------------------------------------------------------------- #
# Figures
# --------------------------------------------------------------------------------------------- #
_NUM = r"([0-9][0-9,]*(?:\.[0-9]+)?)"
# Word boundaries are load-bearing here, not tidiness. Without the trailing \b, `follows?` matches
# inside "followers", so "1,200 followers" was read as a FOLLOWING count and compared against the
# wrong ground truth. Every clean paragraph in the test fixture failed on it.
_FOLLOWERS_RE = re.compile(_NUM + r"\s+followers\b", re.I)
#: Only a phrase that actually says "follows N" counts as a following claim. A bare "N accounts" was
#: here once and was a false-positive machine: "one of 4 accounts in this batch", "3 accounts posted
#: the same line" are ordinary sentences that got compared against the following count and withheld a
#: true paragraph. The live contamination this check exists to catch ("following 1,281 people while
#: only 505 follow back") is caught by the verb form, so nothing is lost by dropping the bare one.
#:
#: BOTH WORD ORDERS, and the second one is why a real contamination reached a customer. The verb-first
#: form ("follows 2,263") was the only one matched, so the NUMBER-FIRST form ("2,263 following") was
#: never checked at all -- and number-first is what the model actually writes, on most rows: "384
#: followers and 782 following", "103 followers vs 9 following". `jamesthatcher_` (really 322/349)
#: was published as "337 followers and 2,263 following", figures belonging to another account in the
#: same batch, and nothing fired. The trailing `(?!\s*followers)` on the verb form stays: without it
#: `follows?` matches inside "followers" and a follower count gets compared against the wrong truth.
_HEDGE = r"(?:about\s+|around\s+|roughly\s+|~\s*|just\s+|only\s+|over\s+|under\s+)?"
_FOLLOWING_RE = re.compile(
    r"follow(?:s|ing)\s+" + _HEDGE + _NUM + r"\b(?!\s*followers)"
    r"|" + _NUM + r"\s+following\b", re.I)

#: THE CREATION DATE, in the forms the model actually writes it.
#:
#: `_DAYS_RE` / `_YEARS_RE` below check "N days old" and "N years old". The model almost never writes
#: either. It writes "(created 2023-07-04)" or "A 2009 account" or "This 2016 account", on nearly
#: every row, and none of those were checked in any form. CLAUDE.md already records a live
#: contamination on exactly this field -- `JohnWSavio`, created 2014-02-07, published as "created on
#: 2024-08-03", which was a different account's date -- and it was still reachable.
#:
#: A full date is checked to the day; a bare year only to the year, because "a 2009 account" is a
#: true statement about any account created in 2009 and pinning it tighter would flag honest prose.
_CREATED_DATE_RE = re.compile(
    r"(?:created|joined|registered|opened|since)\D{0,12}?(\d{4})-(\d{2})-(\d{2})", re.I)
#: "A 2009 account", "This 2016 account", "created 2009", "(created in 2023)". The year must be
#: adjacent to a creation word or to the word "account", so an ordinary year in a quote or a topic
#: ("the 2020 election", "since 2016 the platform") is not read as a claim about the profile.
_CREATED_YEAR_RE = re.compile(
    r"(?:created|joined|registered|opened)\D{0,12}?(\d{4})\b"
    r"|\b(?:a|an|this|the)\s+(\d{4})[- ]?(?:created\s+)?account\b"
    # "account (2009)" -- the year in parentheses AFTER the noun. This is the form the live
    # contamination took: "A long-running account (2009) with 337 followers".
    r"|\baccount\s*\((\d{4})\)", re.I)
_POSTS_RE = re.compile(
    _NUM + r"\s+(?:posts?|tweets?|replies)\b|posted\s+" + _HEDGE + _NUM + r"\s+times?\b", re.I)
_DAYS_RE = re.compile(_NUM + r"\s*days?\s*old", re.I)
_YEARS_RE = re.compile(_NUM + r"\s*years?\s*old", re.I)
#: A ratio may be written as a decimal ("a ratio of 1.19") or as a pair ("a ratio of 600:505"). Both
#: are true statements about the same account, so both are accepted and the pair is divided out.
_RATIO_RE = re.compile(
    r"ratio\s+(?:of\s+)?" + _NUM + r"(?:\s*[:/]\s*" + _NUM + r")?", re.I)


def _f(raw: str) -> float | None:
    try:
        return float(raw.replace(",", ""))
    except (TypeError, ValueError):
        return None


def _off_by(stated: float, actual: float, tol: float) -> bool:
    if actual == 0:
        return stated != 0
    return abs(stated - actual) / abs(actual) > tol


def _age_days(account: dict | None) -> float | None:
    created = (account or {}).get("account_created_at")
    if not created:
        return None
    if isinstance(created, str):
        try:
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(created, datetime):
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - created).total_seconds() / 86400.0)


def check_figures(assessment: str, account: dict | None) -> list[Violation]:
    """Every stated figure must match the account's real metadata.

    Only figures with a known ground truth are checked. A number this account has no value for is
    left alone rather than guessed at: silence in the evidence is not a licence to accuse, and it is
    not a licence to flag either.

    Post counts are compared in ONE DIRECTION, and that is the important subtlety. The protocol
    *requires* the model to name subsets of the history ("near-identical text on two of its own
    posts", "six posts inside one hour"), and every one of those is legitimately smaller than the
    total. Flagging them cost real paragraphs. A number BELOW the history is consistent with the
    evidence; only a number above it describes posts that do not exist.
    """
    if not isinstance(account, dict):
        return []
    text = assessment or ""
    out: list[Violation] = []

    def compare(pattern: re.Pattern, actual, label: str, tol: float,
                over_only: bool = False) -> None:
        if actual is None:
            return
        for m in pattern.finditer(text):
            raw = next((g for g in m.groups() if g), None)
            stated = _f(raw) if raw else None
            if stated is None:
                continue
            if over_only and stated <= float(actual) * (1.0 + tol):
                continue
            if _off_by(stated, float(actual), tol):
                out.append(Violation(
                    "figure_mismatch", HARD,
                    f"said {label} {stated:g}, evidence says {float(actual):g}",
                ))

    followers = account.get("follower_count")
    following = account.get("following_count")
    posts = account.get("history_size") or len(account.get("recent_activity") or []) or None

    compare(_FOLLOWERS_RE, followers, "followers", COUNT_TOLERANCE)
    compare(_FOLLOWING_RE, following, "following", COUNT_TOLERANCE)
    compare(_POSTS_RE, posts, "posts", COUNT_TOLERANCE, over_only=True)

    age = _age_days(account)
    compare(_DAYS_RE, age, "age in days", AGE_TOLERANCE)
    if age is not None:
        compare(_YEARS_RE, age / 365.25, "age in years", AGE_TOLERANCE)
    out.extend(_check_created(text, account))

    if followers not in (None, 0) and following is not None:
        out.extend(_check_ratio(text, float(following) / float(followers)))
    return out


def _check_created(text: str, account: dict) -> list[Violation]:
    """A stated creation date must be the account's own.

    This is the second half of the cross-account contamination the figure checks exist to stop, and
    it was unguarded. The date is the single most-repeated fact in a verdict (the protocol asks for
    the age in every one), and a batch of 25 accounts gives the model 25 nearly identical dates to
    pick the wrong one from.

    A FULL DATE is held to the day. A BARE YEAR is held only to the year, deliberately: "a 2009
    account" is a true statement about anything created in 2009, and demanding more would withhold
    honest prose over a rounding the protocol never forbade.
    """
    created = (account or {}).get("account_created_at")
    if isinstance(created, str):
        try:
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except ValueError:
            return []
    if not isinstance(created, datetime):
        return []

    out: list[Violation] = []
    for m in _CREATED_DATE_RE.finditer(text):
        y, mo, d = (int(g) for g in m.groups())
        if (y, mo, d) != (created.year, created.month, created.day):
            out.append(Violation(
                "figure_mismatch", HARD,
                f"said created {y:04d}-{mo:02d}-{d:02d}, evidence says "
                f"{created.year:04d}-{created.month:02d}-{created.day:02d}",
            ))
    # A full date already reported is not reported again as a bare year. One wrong date is one
    # error, and a violation list that says the same thing twice reads to an operator as two.
    year_text = _CREATED_DATE_RE.sub(" ", text)
    for m in _CREATED_YEAR_RE.finditer(year_text):
        raw = next((g for g in m.groups() if g), None)
        if raw is None:
            continue
        year = int(raw)
        # A four-digit number that is not a plausible account year is not a claim about the profile.
        if not 2006 <= year <= created.year + 1:
            continue
        if year != created.year:
            out.append(Violation(
                "figure_mismatch", HARD,
                f"said created in {year}, evidence says {created.year}",
            ))
    return out


def _decimals(raw: str) -> int:
    """How many decimal places a number was WRITTEN to. `"0.01"` -> 2, `"156"` -> 0."""
    _, _, frac = raw.partition(".")
    return len(frac)


def _matches_at_stated_precision(raw: str, stated: float, actual: float) -> bool:
    """Is the written figure the true one, rounded to the precision it was written at?

    A RELATIVE TOLERANCE IS THE WRONG TEST FOR A SMALL RATIO, and it made an entire account shape
    unwritable. Take 1,249 followers against 8 following: the true following-to-followers ratio is
    0.0064, and a 15% band around it is 0.0054 to 0.0074. The only two-decimal number in that band
    does not exist, so "a ratio of 0.01" -- which is 0.0064 correctly rounded, and the most natural
    way to write it -- was withheld as a fabricated figure. Three decimals passed and the inverted
    form passed; the obvious form failed.

    That is not a rare corner. v14 added the ACQUIRED-AUDIENCE shape (many followers, follows almost
    nobody) to PROFILE as an equally elevated signal, so the protocol actively steers the model
    toward the accounts whose ratios this rejected, and the withholds would arrive in clusters.

    "0.01" is a claim about the ratio TO TWO DECIMAL PLACES, and 0.0064 rounds to 0.01, so the claim
    is true. Checking at the stated precision is what the sentence actually asserts. It stays tight:
    a contaminated "4.0" against a true 0.0064 rounds to 0.0 and is still refused.
    """
    d = _decimals(raw)
    return round(actual, d) == round(stated, d)


def _check_ratio(text: str, actual: float) -> list[Violation]:
    """A ratio is accepted in either direction, at the precision it was stated, and as a pair.

    ``_CHECKABLE_CLAIMS`` asks for following-to-followers, but a model that writes the inverse and
    labels it correctly has stated a TRUE figure about the account. Withholding that paragraph
    punishes the model for naming the same fact the other way up, which is a checker bug rather than
    a fabrication. So both orientations pass, and a pair ("a ratio of 600:505") is divided out first.
    """
    out: list[Violation] = []
    if actual <= 0:
        return out
    inverse = 1.0 / actual
    for m in _RATIO_RE.finditer(text):
        raw_left, raw_right = m.group(1), m.group(2)
        left, right = _f(raw_left), _f(raw_right) if raw_right else None
        if left is None:
            continue
        stated = left if right is None else (left / right if right else None)
        if stated is None:
            continue
        if (not _off_by(stated, actual, RATIO_TOLERANCE)
                or not _off_by(stated, inverse, RATIO_TOLERANCE)):
            continue
        # A pair ("600:505") states two exact counts rather than a rounded quotient, so the
        # precision rule applies only to the single-number form.
        if right is None and (_matches_at_stated_precision(raw_left, stated, actual)
                              or _matches_at_stated_precision(raw_left, stated, inverse)):
            continue
        out.append(Violation(
            "figure_mismatch", HARD,
            f"said the ratio {stated:g}, evidence says {actual:g} (or {inverse:g} inverted)",
        ))
    return out


# --------------------------------------------------------------------------------------------- #
# Phrasing, boilerplate, readability
# --------------------------------------------------------------------------------------------- #
#: Words that flip a banned phrase into the opposite claim. See `_is_negated`.
_NEGATORS = ("no", "not", "never", "nothing", "cannot", "without", "nor", "n't")
#: How far back to look for one. Deliberately tight: only an IMMEDIATE negation excuses the phrase.
#: "there is no proof that" is a hedge; "it is not a coincidence that this account was hired" is an
#: accusation with a negator elsewhere in the sentence, and it stays banned.
_NEGATION_WINDOW = 16


def _is_negated(low: str, start: int) -> bool:
    """Does a negator sit immediately before the banned phrase?"""
    window = low[max(0, start - _NEGATION_WINDOW):start]
    return any(re.search(rf"(?:^|\W){re.escape(n)}\W*$", window) for n in _NEGATORS)


def check_phrasing(assessment: str) -> list[Violation]:
    """The banned-phrase lint, finally reaching the text it was written for.

    The difference between "is a bot" and "behaves consistently with automation" is the difference
    between an accusation and a finding, and this prose is what gets quoted.

    A NEGATED PHRASE IS NOT THE CLAIM THE BAN EXISTS TO STOP, and matching the bare substring made
    the rule fire on its own opposite. "There is no proof that the account is automated" and "this
    is not obviously a bot" are HEDGES, and both were withheld as assertions of certainty. On a
    corpus where most accounts are ordinary people, and where the constitution requires the innocent
    explanation to be stated in every verdict, those sentences are common.

    The window is tight on purpose. Only an immediate negation excuses the phrase, so "it is not a
    coincidence that this account was hired" keeps its violation.

    Note what is deliberately NOT excused. "no doubt" is itself a certainty phrase rather than a
    negated one: the negator is part of the banned string, so the look-behind never sees it. And
    "this person" stays banned in every context, because asserting the account is a person is an
    identity claim the evidence cannot support; the protocol says "a real person" (a category) nine
    times and "this person" never.
    """
    low = (assessment or "").lower()
    out: list[Violation] = []
    for p in BANNED_PHRASES:
        for m in re.finditer(re.escape(p), low):
            if _is_negated(low, m.start()):
                continue
            out.append(Violation("banned_phrase", HARD, f'asserts identity or certainty: "{p}"'))
            break
    return out


def _shingles(text: str, k: int = 5) -> frozenset:
    words = _WORD_RE.findall(_norm(text))
    if len(words) < k:
        return frozenset([" ".join(words)] if words else [])
    return frozenset(" ".join(words[i:i + k]) for i in range(len(words) - k + 1))


def check_boilerplate(assessments: dict[str, str]) -> dict[str, list[Violation]]:
    """Near-identical paragraphs across accounts in one batch.

    A paragraph reused across five accounts is one finding presented five times, and it reads to a
    customer as the product not really having looked. Batch-level, so it lives here rather than in
    the per-account pass.
    """
    out: dict[str, list[Violation]] = {ref: [] for ref in assessments}
    refs = [r for r, a in assessments.items() if a and len(a) > 80]
    shingled = {r: _shingles(assessments[r]) for r in refs}
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            a, b = shingled[refs[i]], shingled[refs[j]]
            if not a or not b:
                continue
            inter = len(a & b)
            jac = inter / float(len(a) + len(b) - inter)
            if jac >= BOILERPLATE_JACCARD:
                msg = f"{jac:.0%} identical to the paragraph written for {{other}}"
                out[refs[i]].append(Violation("boilerplate", SOFT, msg.format(other=refs[j])))
                out[refs[j]].append(Violation("boilerplate", SOFT, msg.format(other=refs[i])))

    # THE OPENING AND CLOSING SENTENCES, COUNTED SEPARATELY FROM THE PARAGRAPH.
    #
    # Whole-paragraph Jaccard cannot see this and never fired on it: twenty-five verdicts can share
    # one opening skeleton and one closing sentence while their middles differ enough to stay well
    # under the threshold. That is exactly what the live runs did. Every verdict began "This account
    # (created DATE) has N followers and follows M", and a clear majority closed on "the one
    # observation that would most change this read is finding identical templated text repeated
    # across its own posts" -- a template, on a product whose whole claim is that templates are a
    # tell.
    #
    # Banning the specific sentence is what produced the second one: the model substituted rather
    # than varied. So this counts SHAPES across the batch and reports the repetition itself, which is
    # the thing that is actually wrong and cannot be worked around by picking new words.
    for position, pick in (("opening", _first_sentence), ("closing", _last_sentence)):
        buckets: dict[tuple, list[str]] = {}
        for r in refs:
            shape = _sentence_shape(pick(assessments[r]))
            if shape:
                buckets.setdefault(shape, []).append(r)
        for shape, group in buckets.items():
            if len(group) < max(3, int(len(refs) * REPEATED_SENTENCE_SHARE)):
                continue
            for r in group:
                out[r].append(Violation(
                    "repeated_" + position, SOFT,
                    f"{len(group)} of {len(refs)} accounts share this {position} sentence shape",
                ))
    return out


def _first_sentence(text: str) -> str:
    parts = [p for p in _SENTENCE_SPLIT.split(text or "") if p.strip()]
    return parts[0] if parts else ""


def _last_sentence(text: str) -> str:
    parts = [p for p in _SENTENCE_SPLIT.split(text or "") if p.strip()]
    return parts[-1] if parts else ""


def _sentence_shape(sentence: str) -> tuple:
    """The reusable skeleton of a sentence, with the account-specific parts removed.

    Two sentences have the same SHAPE when they would be the same sentence with different numbers,
    dates and handles filled in. That is the thing being measured: "This account (created 2019-04-02)
    has 400 followers and follows 900" and "This account (created 2023-11-18) has 51 followers and
    follows 2,204" are one template used twice, and no word-level comparison catches them because
    almost every word already matches. Digits collapse to a single marker, then the first several
    remaining words are the key -- enough to identify the skeleton, short enough that a genuinely
    different sentence sharing an opening preposition does not collide.
    """
    norm = _norm(sentence or "")
    if not norm:
        return ()
    norm = re.sub(r"[0-9][0-9,.:\-]*", " 0 ", norm)
    words = _WORD_RE.findall(norm)
    return tuple(words[:8]) if len(words) >= 5 else ()


def check_readability(assessment: str) -> list[Violation]:
    """The audience is the creator whose comment section this is, not an analyst."""
    text = (assessment or "").strip()
    if not text:
        return []
    out: list[Violation] = []
    sentences = [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    if sentences:
        lengths = [len(_WORD_RE.findall(_norm(s))) for s in sentences]
        mean = statistics.mean(lengths)
        if mean > MAX_MEAN_SENTENCE_WORDS:
            out.append(Violation(
                "long_sentences", SOFT,
                f"averages {mean:.0f} words per sentence, which reads as a wall of text",
            ))
    low = text.lower()
    found = [j for j in JARGON if j in low]
    if found:
        out.append(Violation("jargon", SOFT, "uses analyst jargon: " + ", ".join(found[:4])))
    return out


# Account (A1..) and cluster (C1..) aliases. Narrative aliases (N1..) are deliberately NOT matched:
# they are vanishingly rare in per-account prose, while "N95" is not rare at all in the kind of
# comment section this product reads, and a false withhold costs a customer a paragraph they paid for.
# "A1" and "C4" can still collide with ordinary words; that trade is worth it, because aliases opened
# essentially every verdict in the live export and a withheld paragraph still shows its score, its
# breakdown, and an honest notice.
_ALIAS_RE = re.compile(r"\b[AC]\d{1,3}\b")
# Phrases that narrate the scoring instead of describing the account, or swap one label for another.
# SOFT on purpose: a paragraph can be perfectly true and still be written this way, and withholding a
# correct assessment over a stylistic tic would be a worse outcome than printing it. HARD is reserved
# for claims the evidence contradicts.
#: Closing sentences that ask the reader for more data. The constitution bans these outright, and they
#: are still being written verbatim: "More posts would be needed to change the read" appeared in a live
#: export and is almost word for word one of the three strings the rule names. The batch-level shape
#: check cannot catch a dozen scattered leaks, because it only fires when a third of the batch shares
#: one shape, so this looks at a single paragraph's last sentence.
#:
#: SOFT, like every other writing rule here. Ending badly is not a false claim about a person, and
#: withholding a true paragraph over its last sentence is the trade this file has already settled.
_MORE_DATA_CLOSERS = (
    "more posts would", "collecting more", "more of its posts would", "additional posts would",
    "a larger sample would", "would increase confidence", "would raise confidence",
    "would improve confidence", "would be needed to change", "would clarify",
    "would materially change this read", "would settle this", "would allow a", "would enable a",
    "would permit a", "more data would", "further posts would", "sampling its posts",
)

_STYLE_TICS = ("i settled on", "rather than one", "more like a ", "more like an ",
               "reads more like", "i landed on")


def check_alias_in_prose(assessment: str) -> list[Violation]:
    """An internal alias must never reach the reader.

    Aliases (A1, A7, C2, N3) are batch-local labels for the model's own bookkeeping: they resolve
    through the legend, they mean DIFFERENT accounts in different batches of the same investigation,
    and the customer has never seen one. Live output opened essentially every verdict with "A17 is a
    2009 account...", and several referred across to other accounts ("near-identical to A23's
    reposts"), which is both meaningless after the merge and the contagion the protocol forbids.

    HARD, unlike the style check below, because this is not a matter of taste: the sentence is about
    an entity the reader cannot resolve, so as published prose it is unverifiable by construction.

    QUOTED TEXT IS EXCLUDED, and that exclusion is the difference between this rule working and this
    rule destroying good assessments. `[AC]\\d{1,3}` matches plenty of things real people write:
    "C4" (the broadcaster), "C19", "the A1" (the road), model and part numbers. Those arrive inside a
    verbatim quote of the account's OWN post, where they are the account's words, not our label
    leaking. Scanning them withheld correct paragraphs for quoting accurately, which is the opposite
    of what this is for. An alias leaks in NARRATION ("A17 is a 2009 account"), so narration is what
    is scanned.
    """
    narration = _QUOTE_RE.sub(" ", assessment or "")
    found = sorted(set(_ALIAS_RE.findall(narration)))
    if not found:
        return []
    return [Violation(
        "alias_in_prose", HARD,
        f"names internal alias(es) {', '.join(found[:4])} that the reader cannot resolve",
    )]


def check_closing_ask(assessment: str) -> list[Violation]:
    """The last sentence must not ask the reader for more data.

    The last line is the one a reader remembers, and ending on the analysis being insufficient tells
    somebody who just paid for it that they received nothing. The constitution bans it by name; this
    is the check that notices when the ban is ignored.
    """
    parts = [p for p in _SENTENCE_SPLIT.split(assessment or "") if p.strip()]
    if not parts:
        return []
    last = _norm(parts[-1])
    hit = next((c for c in _MORE_DATA_CLOSERS if c in last), None)
    if not hit:
        return []
    return [Violation("closing_ask_for_data", SOFT,
                      f'closes on a request for more data: "{parts[-1].strip()[:90]}"')]


def check_style(assessment: str) -> list[Violation]:
    """The formulaic tics, flagged for the operator and never suppressed.

    "I settled on 72 rather than 57" appeared in roughly 90% of one live export and is worthless to a
    reader: it names a number the account did NOT get, which reads as though it nearly was accused.
    It came from the output contract, which used to ask for it explicitly.
    """
    low = (assessment or "").lower()
    hits = [t for t in _STYLE_TICS if t in low]
    return [Violation("style_formula", SOFT, f"formulaic phrasing: {', '.join(hits)}")] if hits else []


def check_coherence(row: dict) -> list[Violation]:
    """The score has to be explainable by the dimensions underneath it.

    Dossier Loop step 3c says so and nothing enforced it. A high number over dimensions that are all
    low or all null is the shape of a guess, and a reader who opens the breakdown sees the
    contradiction immediately.
    """
    out: list[Violation] = []
    score = row.get("omi_score")
    signals = [s for s in (row.get("signals") or []) if isinstance(s, dict)]
    scored = [s["score"] for s in signals if isinstance(s.get("score"), (int, float))]
    if score is None:
        return out
    if score >= 75 and scored and max(scored) < 50:
        out.append(Violation(
            "score_not_explained", SOFT,
            f"omi_score {score} sits above every dimension it is supposed to follow from "
            f"(highest is {max(scored)})",
        ))
    if score >= 50 and len(scored) <= 2:
        out.append(Violation(
            "thin_basis", SOFT,
            f"omi_score {score} rests on {len(scored)} scored dimensions; the rest were left null",
        ))
    tier = (row.get("suspicion_tier") or "").lower()
    expected = ("low" if score < 25 else "moderate" if score < 50
                else "elevated" if score < 75 else "high")
    if tier and tier != expected:
        out.append(Violation(
            "tier_mismatch", SOFT, f"tier '{tier}' does not match omi_score {score} ('{expected}')",
        ))
    return out


# --------------------------------------------------------------------------------------------- #
# The pass
# --------------------------------------------------------------------------------------------- #
WITHHELD_NOTICE = (
    "This account's written summary was withheld. Our automated checks could not match part of it "
    "against the evidence we actually collected, so we do not publish it. The score and the "
    "breakdown below are unaffected, and you can ask us to review this account."
)


def verify_row(row: dict, account: dict | None) -> GroundingReport:
    """Check one joined per-account row against that account's collected evidence."""
    assessment = row.get("assessment") or ""
    violations: list[Violation] = []
    violations += check_quotes(assessment, account)
    violations += check_figures(assessment, account)
    violations += check_phrasing(assessment)
    violations += check_alias_in_prose(assessment)
    violations += check_style(assessment)
    violations += check_closing_ask(assessment)
    violations += check_readability(assessment)
    violations += check_coherence(row)
    quotes = [m for m in _QUOTE_RE.finditer(assessment)
              if len(_WORD_RE.findall(_norm(re.split(r"\.\.\.|…", m.group(1))[0])))
              >= MIN_ATTRIBUTED_QUOTE_WORDS]
    report = GroundingReport(
        ref=row.get("ref"),
        ok=not any(v.severity == HARD for v in violations),
        violations=violations,
        checked={
            "quotes": len(quotes),
            "posts_available": len((account or {}).get("recent_activity") or []),
            "chars": len(assessment),
        },
    )
    return report


def verify_batch(rows: list[dict], accounts_by_ref: dict) -> dict:
    """Verify every row, withhold what fails hard, and return a batch summary.

    Mutates each row in place: adds ``grounding``, and on a hard failure moves the prose to
    ``assessment_unverified`` and replaces ``assessment`` with an honest notice. Nothing is deleted,
    so an operator can always see exactly what the model said and why it was refused.

    The replacement is applied HERE rather than at serve time, unlike the admin-only signal gate, and
    the difference is deliberate: that gate hides a finished feature and must stay reversible, while
    this removes a claim the evidence does not support. There is no viewer who should be shown that.
    """
    reports: dict[str, GroundingReport] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ref = row.get("ref")
        account = accounts_by_ref.get(ref) if ref else None
        reports[ref] = verify_row(row, account)

    boiler = check_boilerplate({
        r.get("ref"): (r.get("assessment") or "") for r in rows if isinstance(r, dict) and r.get("ref")
    })
    for ref, extra in boiler.items():
        if ref in reports:
            reports[ref].violations.extend(extra)

    withheld = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        rep = reports.get(row.get("ref"))
        if rep is None:
            continue
        row["grounding"] = rep.to_dict()
        if not rep.ok:
            withheld += 1
            row["assessment_unverified"] = row.get("assessment")
            row["assessment"] = WITHHELD_NOTICE
            # An unsupported paragraph is also a reason to trust the rest of the row less.
            if isinstance(row.get("confidence"), int):
                row["confidence"] = max(0, min(row["confidence"], 40))

    total = len([r for r in rows if isinstance(r, dict)])
    soft = sum(len([v for v in rep.violations if v.severity == SOFT]) for rep in reports.values())
    return {
        "accounts": total,
        "withheld": withheld,
        "soft_flags": soft,
        "withheld_rate": round(withheld / total, 4) if total else 0.0,
        "codes": sorted({v.code for rep in reports.values() for v in rep.violations}),
    }


__all__ = [
    "GroundingReport", "Violation", "HARD", "SOFT", "WITHHELD_NOTICE",
    "check_quotes", "check_figures", "check_phrasing", "check_boilerplate",
    "check_readability", "check_coherence", "check_alias_in_prose", "check_style",
    "verify_row", "verify_batch",
]


# --------------------------------------------------------------------------------------------- #
# Aliases in the INVESTIGATION-LEVEL prose
#
# `check_alias_in_prose` is HARD and guards `commenter_assessments[].assessment`. It never saw the
# investigation-level `headline` / `assessment` / evidence claims, which go through the Governor's
# S9 lint instead, and that lint has no alias rule. So this shipped to a live page:
#
#   "A small number of accounts belong to style-match clusters (C4, C6, C1, C5, C3, C7)"
#   "Several accounts had few or no collected posts (A24, A20, A19)"
#
# Meaningless to a reader who has never seen the legend, and this is the paragraph that gets
# screenshotted. Withholding the whole investigation summary over it would be far too blunt, so the
# fix is to RESOLVE rather than refuse: an account alias becomes the real handle, which is strictly
# more useful than what the model wrote. Cluster aliases have no public name at all, so they are
# removed, and a parenthetical left empty by that removal goes with them.
# --------------------------------------------------------------------------------------------- #
_ACCOUNT_ALIAS_RE = re.compile(r"\bA\d{1,3}\b")
_ANY_ALIAS_RE = re.compile(r"\b[AC]\d{1,3}\b")
#: A parenthetical holding nothing but aliases and separators, e.g. "(C4, C6, C1)".
_ALIAS_ONLY_PAREN_RE = re.compile(r"\s*\(\s*(?:[AC]\d{1,3})(?:\s*(?:,|and|&)\s*[AC]\d{1,3})*\s*\)")


def resolve_aliases_in_prose(text: str, handles: dict) -> str:
    """Rewrite internal aliases out of reader-facing prose.

    ``handles`` maps alias -> display handle (already @-prefixed or bare; both are accepted).
    Anything that cannot be resolved is removed rather than printed, because an unresolved label is
    strictly worse than no label: it looks like a defect and tells the reader nothing.
    """
    if not text or not isinstance(text, str):
        return text

    def _sub_known(m: re.Match) -> str:
        h = handles.get(m.group(0))
        if not h:
            return m.group(0)
        h = str(h)
        return h if h.startswith("@") else f"@{h}"

    out = _ACCOUNT_ALIAS_RE.sub(_sub_known, text)
    # Drop parentheticals that are now nothing but unresolved labels.
    out = _ALIAS_ONLY_PAREN_RE.sub("", out)
    # Any stragglers in running text, plus the separator that would be left dangling.
    out = re.sub(r"\s*,\s*(?=[AC]\d{1,3}\b)", ", ", out)
    out = _ANY_ALIAS_RE.sub("", out)
    # Tidy the punctuation the removals leave behind.
    out = re.sub(r"\(\s*[,;\s]*\)", "", out)
    out = re.sub(r"\s+([,.;:])", r"\1", out)
    out = re.sub(r"([,;])\s*\1+", r"\1", out)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip()
