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
_FOLLOWING_RE = re.compile(
    r"follow(?:s|ing)\s+" + _NUM + r"\b(?!\s*followers)|" + _NUM + r"\s+accounts?\b", re.I)
_POSTS_RE = re.compile(_NUM + r"\s+(?:posts?|tweets?|replies)\b", re.I)
_DAYS_RE = re.compile(_NUM + r"\s*days?\s*old", re.I)
_YEARS_RE = re.compile(_NUM + r"\s*years?\s*old", re.I)
_RATIO_RE = re.compile(r"ratio\s+(?:of\s+)?" + _NUM, re.I)


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
    """
    if not isinstance(account, dict):
        return []
    text = assessment or ""
    out: list[Violation] = []

    def compare(pattern: re.Pattern, actual, label: str, tol: float) -> None:
        if actual is None:
            return
        for m in pattern.finditer(text):
            raw = next((g for g in m.groups() if g), None)
            stated = _f(raw) if raw else None
            if stated is None:
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
    compare(_POSTS_RE, posts, "posts", COUNT_TOLERANCE)

    age = _age_days(account)
    compare(_DAYS_RE, age, "age in days", AGE_TOLERANCE)
    if age is not None:
        compare(_YEARS_RE, age / 365.25, "age in years", AGE_TOLERANCE)

    if followers not in (None, 0) and following is not None:
        compare(_RATIO_RE, float(following) / float(followers), "the ratio", RATIO_TOLERANCE)
    return out


# --------------------------------------------------------------------------------------------- #
# Phrasing, boilerplate, readability
# --------------------------------------------------------------------------------------------- #
def check_phrasing(assessment: str) -> list[Violation]:
    """The banned-phrase lint, finally reaching the text it was written for.

    The difference between "is a bot" and "behaves consistently with automation" is the difference
    between an accusation and a finding, and this prose is what gets quoted.
    """
    low = (assessment or "").lower()
    return [
        Violation("banned_phrase", HARD, f'asserts identity or certainty: "{p}"')
        for p in BANNED_PHRASES if p in low
    ]


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
    return out


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
    "check_readability", "check_coherence", "verify_row", "verify_batch",
]
