"""Coordinated-campaign detection from omi scores and analyst verdicts alone.

The engine's existing coordination detectors (``app/detection/coordination/``) need timestamps,
engagement edges and post bodies. This module answers a harder, narrower question: given only a list
of ``(profile_id, omi_score, verdict_text)``, which of those profiles are running together?

That input is far richer than it looks, because the verdicts are not free prose. They are written
under the Master Analyst Protocol (constitution v10), which *forces* structure into them: a computed
following-to-followers ratio as a figure, an age in days or years, a post count as a number, and a
verbatim quote for any claim about what an account wrote ("if you cannot quote it, you cannot claim
it"). So every verdict carries a small structured record of the account, embedded in prose, and the
quotes carry the account's own words. That is what this module mines.

---------------------------------------------------------------------------------------------------
THE CENTRAL TRAP, AND THE PRINCIPLE THAT AVOIDS IT
---------------------------------------------------------------------------------------------------

One model wrote every verdict in the batch. So raw lexical similarity between two verdicts is
dominated by the *analyst's* template, not by the accounts: a naive TF-IDF cosine over verdicts
clusters on "both verdicts contain the word 'ratio'", which is a fingerprint of the protocol and
evidence of nothing. Worse, the vocabulary is *conditioned on the score* ("converging", "elevated",
"thin evidence"), so a naive method would cluster every 80-scoring account together and report a
campaign that is really just a score band.

Every view in this module therefore obeys one rule:

    **Agreement is evidence only in proportion to how improbable that agreement is under the
    batch's own background distribution, holding the omi score band fixed.**

Concretely that means document-frequency subtraction of protocol boilerplate, score-band-conditional
centring of the text vectors (a background-subtraction / common-component-removal step), rarity
weighting on every categorical match, and a band-preserving permutation test on every finished
cluster. A group that is no more mutually similar than a random group with the same score
composition is not a campaign, however high its scores.

---------------------------------------------------------------------------------------------------
COORDINATION AND BOTNESS ARE ORTHOGONAL AXES
---------------------------------------------------------------------------------------------------

This module never multiplies coordination by mean omi score. A tight cluster of *low*-scoring
accounts is a real and interesting finding (a well-camouflaged network, or a fan community), and
collapsing the two axes would hide it and would also let a pile of unrelated high scorers masquerade
as an operation. The two numbers are measured separately and only combined at the labelling step,
which is where the ``coordinated_authentic`` class lives: a genuine community of real people shares
vocabulary and joins a platform in cohorts, and calling that a bot campaign is the single most
damaging mistake this product can make.
"""
from __future__ import annotations

import hashlib
import math
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field

from app.detection.coordination._types import CoordinationCluster

# --------------------------------------------------------------------------------------------------
# Tunables. Every one of these is a decision; see the design doc for the reasoning.
# --------------------------------------------------------------------------------------------------
MIN_CLUSTER_SIZE = 3            # two accounts agreeing is a coincidence, not an operation
BOILERPLATE_DF = 0.45           # a token in >45% of verdicts is protocol scaffolding, not evidence
SCORE_BAND_WIDTH = 20           # bands: 1-20, 21-40, ... the conditioning variable for every null
QUOTE_SHINGLE_K = 5             # character shingles for near-duplicate quote detection
QUOTE_DUP_THRESHOLD = 0.62      # Jaccard over shingles above which two quotes are "the same script"
RESIDUAL_COSINE_THRESHOLD = 0.34
NUMERIC_COHORT_EPS = 0.55       # DBSCAN eps in robust-z space
MAX_COHORT_SHARE = 0.40         # a numeric blob larger than this share of the batch IS the batch
PERMUTATIONS = 300              # band-preserving null resamples per cluster
MAX_EXPLANATION_ITEMS = 6

# Which views may support a strong verdict alone, mirroring the corroboration gate the engine's
# aggregate.py already applies. A view is DISCRIMINATIVE if agreement on it is hard to produce by
# accident among unrelated real people. Shared verbatim text, a shared account-creation cohort AND
# size profile, and a shared handle template are all hard to produce accidentally. Shared reasoning
# vocabulary is not: the analyst produces that, and so do genuinely similar-looking real accounts.
DISCRIMINATIVE_VIEWS: frozenset[str] = frozenset({
    "quote_echo", "numeric_cohort", "handle_morphology",
})
SUPPORTING_VIEWS: frozenset[str] = frozenset({
    "verdict_residual", "rationale_shape", "score_quantization",
})
SUPPORTING_ONLY_CEILING = 0.49  # top of MODERATE for a cluster with no discriminative support

VIEW_RELIABILITY: dict[str, float] = {
    "quote_echo": 1.0,          # the account's own words, repeated. The strongest single signal.
    "numeric_cohort": 0.85,     # profile shape agreement, robust-z tested against the batch
    "handle_morphology": 0.70,  # strong in farms, but platforms auto-append digits (see below)
    "verdict_residual": 0.45,   # post-template, post-band residual. Suggestive only.
    "rationale_shape": 0.40,
    "score_quantization": 0.25, # weakest: an artifact of model rounding as often as anything real
}


# --------------------------------------------------------------------------------------------------
# Input / output types
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ProfileResult:
    """One row of the bot detector's output. ``handle`` defaults to the id when not given."""

    profile_id: str
    omi_score: int
    verdict: str
    handle: str | None = None

    @property
    def name(self) -> str:
        return self.handle or self.profile_id


@dataclass
class ProfileFeatures:
    profile_id: str
    omi_score: int
    band: int
    quotes: list[str] = field(default_factory=list)
    quote_shingles: frozenset[str] = frozenset()
    numerics: dict[str, float] = field(default_factory=dict)
    cohort: str | None = None
    handle_skeleton: str | None = None
    claim_types: frozenset[str] = frozenset()
    tokens: Counter = field(default_factory=Counter)


@dataclass
class Edge:
    a: str
    b: str
    view: str
    weight: float
    reason: str


@dataclass
class ClusterVerdict:
    members: list[str]
    coordination: float          # 0..1, how coordinated
    botness: float               # 0..1, robust central tendency of member omi scores
    confidence: float            # 0..1, how much evidence backed the estimate
    p_value: float | None        # permutation test; None when the batch was too small to test
    significance: 'Significance'
    label: str
    views: list[str]             # which views supported it, strongest first
    components: dict[str, float]
    evidence: list[str]
    per_member: dict[str, list[str]]
    signature: tuple[int, ...]   # MinHash sketch for cross-investigation linkage
    signature_bands: list[str]


@dataclass
class CampaignAnalysis:
    clusters: list[ClusterVerdict]
    lone_wolves: list[str]
    unclustered: list[str]
    batch_notes: list[str]

    def to_coordination_clusters(self) -> list[CoordinationCluster]:
        """Adapt to the engine's existing cluster shape so ``CampaignService.record_clusters``
        persists these exactly like a detector-produced cluster, with no second code path."""
        return [
            CoordinationCluster(
                method="verdict_coordination",
                members=list(c.members),
                score=float(c.coordination),
                evidence=list(c.evidence),
            )
            for c in self.clusters
            if c.label in ("coordinated_bot_campaign", "coordinated_authentic")
        ]


# --------------------------------------------------------------------------------------------------
# 1. Feature extraction
# --------------------------------------------------------------------------------------------------
_QUOTE_RE = re.compile(r'["“‘]([^"“”‘’]{4,300})["”’]')
_WORD_RE = re.compile(r"[a-z][a-z'\-]{1,}")

_NUMERIC_PATTERNS: dict[str, re.Pattern] = {
    # The protocol requires the ratio be stated as a computed figure, which is what makes this
    # parseable at all. Both "ratio of 18.4" and "18.4:1" are accepted.
    "ratio": re.compile(r"ratio(?:\s+of)?\s+([0-9]+(?:\.[0-9]+)?)|([0-9]+(?:\.[0-9]+)?)\s*:\s*1"),
    "followers": re.compile(r"([0-9][0-9,]*)\s+followers?"),
    "following": re.compile(r"following\s+([0-9][0-9,]*)|([0-9][0-9,]*)\s+following"),
    "posts": re.compile(r"([0-9][0-9,]*)\s+(?:posts?|tweets?)"),
}
_AGE_DAYS_RE = re.compile(r"([0-9][0-9,]*)\s*days?\s*old")
_AGE_YEARS_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*years?\s*old")
_AGE_MONTHS_RE = re.compile(r"([0-9]+)\s*months?\s*old")
_ISO_DATE_RE = re.compile(r"(20[0-9]{2})-([01][0-9])(?:-[0-3][0-9])?")
_MONTH_YEAR_RE = re.compile(
    r"(january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+(20[0-9]{2})", re.I,
)
_MONTHS = {m: i + 1 for i, m in enumerate(
    "january february march april may june july august september october november december".split()
)}

# Claim types the protocol's vocabulary makes recoverable. Deliberately coarse: the point is which
# KINDS of evidence the analyst cited, as a set, not a topic model.
_CLAIM_LEXICON: dict[str, tuple[str, ...]] = {
    "no_bio": ("no bio", "empty bio", "blank bio", "bio is empty"),
    "unverified": ("unverified", "not verified"),
    "default_avatar": ("default avatar", "no avatar", "placeholder avatar", "egg avatar"),
    "new_account": ("recently created", "new account", "days old", "created in", "created on"),
    "ratio_imbalance": ("ratio", "follows far more", "following-to-follower"),
    "thin_history": ("few posts", "thin history", "little history", "no posting history",
                     "sparse history"),
    "repetition": ("repeats", "repetition", "identical", "near-identical", "verbatim",
                   "same phrasing", "boilerplate"),
    "promotional": ("promotional", "promotes", "advertis", "referral", "invite link", "sign up"),
    "burst_timing": ("burst", "within minutes", "same minute", "seconds apart", "clustered in time"),
    "template_language": ("template", "formulaic", "generated text", "ai-generated", "scripted"),
    "engagement_only": ("only replies", "reply-only", "never posts", "no original"),
    "second_language": ("second language", "non-native", "translated"),
    "business": ("business", "brand", "shop", "storefront", "company account"),
    "fan_account": ("fan account", "fan page", "supporter", "hobby account", "enthusiast"),
    "news_feed": ("news", "aggregator", "headlines", "syndicat"),
}


def _band_of(score: int) -> int:
    return max(0, min(4, (int(score) - 1) // SCORE_BAND_WIDTH))


def _shingles(text: str, k: int = QUOTE_SHINGLE_K) -> frozenset[str]:
    norm = re.sub(r"[^a-z0-9 ]+", "", text.lower())
    norm = re.sub(r"\s+", " ", norm).strip()
    if len(norm) < k:
        return frozenset({norm} if norm else set())
    return frozenset(norm[i:i + k] for i in range(len(norm) - k + 1))


def handle_skeleton(handle: str) -> str | None:
    """Morphological template of a username: letters to 'a'/'A', digits to '9', runs collapsed.

    ``crypto_mike8837`` becomes ``a_a9``. Two accounts sharing a skeleton are only evidence when
    that skeleton is RARE IN THIS BATCH, which is what ``_handle_view`` weights on.

    A necessary caveat, and it is the constitution's, not a stylistic one: trailing digits on a
    handle are auto-appended by platforms at sign-up and are never a tell about an individual
    account. What is evidence here is different and much narrower: an improbable number of accounts
    in one comment section sharing one uncommon template. The individual-level claim stays forbidden.
    """
    h = (handle or "").strip().lstrip("@")
    if not h:
        return None
    out: list[str] = []
    for ch in h:
        if ch.isdigit():
            c = "9"
        elif ch.isupper():
            c = "A"
        elif ch.isalpha():
            c = "a"
        else:
            c = "_"
        if not out or out[-1] != c:
            out.append(c)
    return "".join(out)


def _parse_numerics(text: str) -> dict[str, float]:
    low = text.lower()
    out: dict[str, float] = {}
    for key, pat in _NUMERIC_PATTERNS.items():
        m = pat.search(low)
        if not m:
            continue
        raw = next((g for g in m.groups() if g), None)
        if raw is None:
            continue
        try:
            out[key] = float(raw.replace(",", ""))
        except ValueError:
            continue
    if (m := _AGE_DAYS_RE.search(low)):
        out["age_days"] = float(m.group(1).replace(",", ""))
    elif (m := _AGE_MONTHS_RE.search(low)):
        out["age_days"] = float(m.group(1)) * 30.44
    elif (m := _AGE_YEARS_RE.search(low)):
        out["age_days"] = float(m.group(1)) * 365.25
    # Derive the ratio when both sides are present but the figure was not stated.
    if "ratio" not in out and out.get("followers", 0) > 0 and "following" in out:
        out["ratio"] = out["following"] / max(1.0, out["followers"])
    return out


def _parse_cohort(text: str) -> str | None:
    """The account-creation month, as a bucket. Two accounts created in the same month is weak;
    twenty of them in a section whose other members span six years is not."""
    if (m := _ISO_DATE_RE.search(text)):
        return f"{m.group(1)}-{m.group(2)}"
    if (m := _MONTH_YEAR_RE.search(text)):
        return f"{m.group(2)}-{_MONTHS[m.group(1).lower()]:02d}"
    return None


def _parse_claims(text: str) -> frozenset[str]:
    low = text.lower()
    return frozenset(name for name, needles in _CLAIM_LEXICON.items()
                     if any(n in low for n in needles))


def extract_features(results: list[ProfileResult]) -> list[ProfileFeatures]:
    """Per-profile structured extraction. Pure parsing; no cross-profile information yet."""
    feats: list[ProfileFeatures] = []
    for r in results:
        text = r.verdict or ""
        quotes = [q.strip() for q in _QUOTE_RE.findall(text) if q.strip()]
        shingles: set[str] = set()
        for q in quotes:
            shingles |= _shingles(q)
        feats.append(ProfileFeatures(
            profile_id=r.profile_id,
            omi_score=int(r.omi_score),
            band=_band_of(r.omi_score),
            quotes=quotes,
            quote_shingles=frozenset(shingles),
            numerics=_parse_numerics(text),
            cohort=_parse_cohort(text),
            handle_skeleton=handle_skeleton(r.name),
            claim_types=_parse_claims(text),
            tokens=Counter(_WORD_RE.findall(text.lower())),
        ))
    return feats


# --------------------------------------------------------------------------------------------------
# 2. The views. Each returns edges, each weighted by improbability-under-the-batch.
# --------------------------------------------------------------------------------------------------
def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / float(len(a) + len(b) - inter)


def _quote_echo_view(feats: list[ProfileFeatures]) -> list[Edge]:
    """Near-duplicate quoted text: the account's OWN words repeating across accounts.

    This is the most discriminative signal available, because the protocol only permits a quote when
    the account actually wrote it. Two strangers independently writing the same 40 characters is
    vanishingly unlikely; a script producing it is the ordinary explanation.

    Candidate generation is LSH-banded MinHash over character shingles, so this stays near-linear on
    thousands of profiles instead of quadratic.
    """
    edges: list[Edge] = []
    have = [f for f in feats if f.quote_shingles]
    if len(have) < 2:
        return edges

    # Banded LSH: bucket by a handful of min-hashes so only plausible pairs are compared exactly.
    buckets: dict[tuple[int, int], list[ProfileFeatures]] = {}
    for f in have:
        sig = _minhash(f.quote_shingles, num_perm=32)
        for band_i in range(8):  # 8 bands of 4 rows
            key = (band_i, hash(sig[band_i * 4:(band_i + 1) * 4]))
            buckets.setdefault(key, []).append(f)

    seen: set[tuple[str, str]] = set()
    for members in buckets.values():
        if len(members) < 2 or len(members) > 400:
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                pair = tuple(sorted((a.profile_id, b.profile_id)))
                if pair in seen:
                    continue
                seen.add(pair)
                sim = _jaccard(a.quote_shingles, b.quote_shingles)
                if sim < QUOTE_DUP_THRESHOLD:
                    continue
                sample = (a.quotes[0] if a.quotes else "")[:70]
                edges.append(Edge(
                    a=a.profile_id, b=b.profile_id, view="quote_echo", weight=float(sim),
                    reason=f'quoted text {sim:.0%} identical, e.g. "{sample}"',
                ))
    return edges


def _minhash(shingles: frozenset[str], num_perm: int = 32) -> tuple[int, ...]:
    """A deterministic MinHash sketch. Pure stdlib hashing, no datasketch dependency."""
    if not shingles:
        return tuple([0] * num_perm)
    mins = [2 ** 64 - 1] * num_perm
    for sh in shingles:
        base = int.from_bytes(hashlib.blake2b(sh.encode(), digest_size=8).digest(), "big")
        for i in range(num_perm):
            # Cheap universal-ish family: mix the base with the permutation index.
            h = (base ^ (0x9E3779B97F4A7C15 * (i + 1))) & 0xFFFFFFFFFFFFFFFF
            if h < mins[i]:
                mins[i] = h
    return tuple(mins)


def _numeric_cohort_view(feats: list[ProfileFeatures]) -> list[Edge]:
    """Accounts whose extracted profile shape forms a TIGHT blob against the batch's own spread.

    Robust z-scores (median / MAD, not mean / sd, because a farm in the batch would corrupt the
    mean) put the numerics on a comparable scale, then DBSCAN finds dense regions. DBSCAN rather
    than k-means on purpose: it does not need a cluster count, and it leaves ordinary accounts
    unassigned as noise instead of forcing everyone into a group.

    Creation-month agreement is folded in as a categorical, weighted by its batch rarity.
    """
    import numpy as np
    from sklearn.cluster import DBSCAN

    keys = ("ratio", "age_days", "posts", "followers")
    usable = [f for f in feats if sum(1 for k in keys if k in f.numerics) >= 2]
    if len(usable) < MIN_CLUSTER_SIZE:
        return []

    cols: list[list[float]] = []
    for k in keys:
        vals = [f.numerics.get(k) for f in usable]
        present = [v for v in vals if v is not None]
        if len(present) < 3:
            cols.append([0.0] * len(usable))
            continue
        # log1p first: follower counts and post counts are heavy-tailed, and a raw-scale distance
        # would be dominated entirely by whichever account has the most followers.
        logged = [math.log1p(max(0.0, v)) if v is not None else None for v in vals]
        obs = [v for v in logged if v is not None]
        med = statistics.median(obs)
        mad = statistics.median([abs(v - med) for v in obs]) or 1e-6
        cols.append([((v - med) / (1.4826 * mad)) if v is not None else 0.0 for v in logged])

    X = np.array(cols, dtype=float).T
    X = np.clip(X, -6.0, 6.0)
    labels = DBSCAN(eps=NUMERIC_COHORT_EPS, min_samples=MIN_CLUSTER_SIZE).fit_predict(X)

    cohort_freq = Counter(f.cohort for f in feats if f.cohort)
    n_cohorted = max(1, sum(cohort_freq.values()))

    edges: list[Edge] = []
    for lab in set(labels):
        if lab < 0:
            continue
        group = [usable[i] for i in range(len(usable)) if labels[i] == lab]
        if len(group) < MIN_CLUSTER_SIZE:
            continue
        # A "cohort" that is most of the batch is the batch. DBSCAN happily returns the population's
        # centre of mass as its densest region, and on a small scan that region is just "ordinary
        # accounts": old, plenty of posts, balanced ratio. Reporting those as a cohort produced a
        # six-member coordinated_authentic cluster of six unrelated real people on the first run of
        # the worked example. The rarity principle applies to this view as much as to the
        # categorical ones: a group is only a cohort if it is a MINORITY against its own background.
        if len(group) / len(usable) > MAX_COHORT_SHARE:
            continue
        desc = _describe_numeric_group(group)
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                w = 0.72
                reason = f"profile shape cluster ({desc})"
                if a.cohort and a.cohort == b.cohort:
                    # Rarity weighting: sharing a common month proves little, sharing a rare one
                    # in a batch that otherwise spans years is the finding.
                    p = cohort_freq[a.cohort] / n_cohorted
                    w = min(0.98, w + 0.25 * (1.0 - p))
                    reason += f", both created {a.cohort}"
                edges.append(Edge(a=a.profile_id, b=b.profile_id, view="numeric_cohort",
                                  weight=w, reason=reason))
    return edges


def _describe_numeric_group(group: list[ProfileFeatures]) -> str:
    parts: list[str] = []
    for k, fmt in (("age_days", "age ~{:.0f}d"), ("posts", "~{:.0f} posts"),
                   ("ratio", "ratio ~{:.1f}")):
        vals = [f.numerics[k] for f in group if k in f.numerics]
        if len(vals) >= 2:
            parts.append(fmt.format(statistics.median(vals)))
    return ", ".join(parts) or "similar profile metrics"


def _handle_morphology_view(feats: list[ProfileFeatures]) -> list[Edge]:
    """Shared username template, weighted by how rare that template is in this batch."""
    freq = Counter(f.handle_skeleton for f in feats if f.handle_skeleton)
    n = max(1, sum(freq.values()))
    edges: list[Edge] = []
    by_skel: dict[str, list[ProfileFeatures]] = {}
    for f in feats:
        if f.handle_skeleton:
            by_skel.setdefault(f.handle_skeleton, []).append(f)
    for skel, group in by_skel.items():
        if len(group) < MIN_CLUSTER_SIZE:
            continue
        p = freq[skel] / n
        if p > 0.5:
            continue  # the batch's default shape carries no information
        # Surprisal, squashed to 0..1. A template held by 10% of the batch scores higher than one
        # held by 40%, and one held by 45% barely registers.
        w = min(0.95, -math.log(max(p, 1e-6)) / math.log(20.0))
        if w < 0.2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                edges.append(Edge(
                    a=group[i].profile_id, b=group[j].profile_id, view="handle_morphology",
                    weight=w,
                    reason=f"handle template '{skel}' shared by {len(group)} of {len(feats)} "
                           f"({p:.0%} of the batch)",
                ))
    return edges


def _verdict_residual_view(feats: list[ProfileFeatures]) -> list[Edge]:
    """Text similarity AFTER removing the protocol template and the score band's own vocabulary.

    Two subtractions, in order:

    1. **Boilerplate**: drop any token appearing in more than ``BOILERPLATE_DF`` of verdicts. That is
       the analyst's scaffolding, present regardless of the account.
    2. **Band conditioning**: subtract the mean TF-IDF vector of the profile's own score band, then
       renormalise. High scores share vocabulary *because* they are high scores; what survives this
       step is the part of the wording that the score does not already explain.

    Step 2 is the one that matters. Without it this view reports "all the 80s look alike", which is
    a restatement of the input, not a discovery.
    """
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer

    if len(feats) < MIN_CLUSTER_SIZE:
        return []
    df = Counter()
    for f in feats:
        df.update(set(f.tokens))
    n = len(feats)
    boiler = {t for t, c in df.items() if c / n > BOILERPLATE_DF}
    docs = [" ".join(t for t in f.tokens.elements() if t not in boiler) for f in feats]
    if not any(d.strip() for d in docs):
        return []

    try:
        vec = TfidfVectorizer(sublinear_tf=True, min_df=2, ngram_range=(1, 2))
        M = vec.fit_transform(docs).toarray()
    except ValueError:
        return []
    if M.shape[1] == 0:
        return []

    # Band-conditional centring.
    for band in {f.band for f in feats}:
        idx = [i for i, f in enumerate(feats) if f.band == band]
        if len(idx) < 2:
            continue
        M[idx] -= M[idx].mean(axis=0, keepdims=True)
    norms = np.linalg.norm(M, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    M = M / norms

    S = M @ M.T
    np.fill_diagonal(S, 0.0)
    edges: list[Edge] = []
    for i in range(len(feats)):
        for j in range(i + 1, len(feats)):
            s = float(S[i, j])
            if s >= RESIDUAL_COSINE_THRESHOLD:
                edges.append(Edge(
                    a=feats[i].profile_id, b=feats[j].profile_id, view="verdict_residual",
                    weight=min(1.0, s),
                    reason=f"verdict wording {s:.2f} cosine after removing template and "
                           f"score-band vocabulary",
                ))
    return edges


def _rationale_shape_view(feats: list[ProfileFeatures]) -> list[Edge]:
    """Accounts flagged for the same UNUSUAL COMBINATION of reasons.

    Weighted by the batch rarity of the shared claim set: 'unverified + no bio' is the base rate and
    contributes nothing, while 'burst_timing + repetition + promotional' shared by nine accounts is
    a shape.
    """
    freq = Counter()
    for f in feats:
        freq.update(f.claim_types)
    n = max(1, len(feats))
    edges: list[Edge] = []
    for i in range(len(feats)):
        for j in range(i + 1, len(feats)):
            a, b = feats[i], feats[j]
            shared = a.claim_types & b.claim_types
            if len(shared) < 3:
                continue
            # Inverse-frequency weight: rare shared claims dominate the sum.
            w_raw = sum(-math.log(max(freq[c] / n, 1e-6)) for c in shared)
            w = min(0.9, w_raw / (len(shared) * math.log(12.0)))
            if w < 0.25:
                continue
            named = ", ".join(sorted(shared)[:4])
            edges.append(Edge(a=a.profile_id, b=b.profile_id, view="rationale_shape",
                              weight=w, reason=f"same evidence pattern: {named}"))
    return edges


def _score_quantization_view(feats: list[ProfileFeatures]) -> list[Edge]:
    """Identical omi scores in a batch whose scores are otherwise dispersed.

    The weakest view by a wide margin, and reliability-weighted accordingly, because a model
    rounding to round numbers produces this too. It is included only because it corroborates: it can
    push a cluster that already has discriminative support over a threshold, never carry one alone.
    """
    scores = [f.omi_score for f in feats]
    if len(set(scores)) < 3:
        return []
    spread = statistics.pstdev(scores) or 1.0
    if spread < 6.0:
        return []  # a uniformly-scored batch tells us nothing by repeating itself
    freq = Counter(scores)
    edges: list[Edge] = []
    by_score: dict[int, list[str]] = {}
    for f in feats:
        by_score.setdefault(f.omi_score, []).append(f.profile_id)
    for score, ids in by_score.items():
        if len(ids) < MIN_CLUSTER_SIZE:
            continue
        p = freq[score] / len(feats)
        w = min(0.6, 0.25 + 0.5 * (1.0 - p))
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                edges.append(Edge(a=ids[i], b=ids[j], view="score_quantization", weight=w,
                                  reason=f"identical omi score {score} shared by {len(ids)} "
                                         f"accounts (batch sd {spread:.1f})"))
    return edges


VIEW_BUILDERS = {
    "quote_echo": _quote_echo_view,
    "numeric_cohort": _numeric_cohort_view,
    "handle_morphology": _handle_morphology_view,
    "verdict_residual": _verdict_residual_view,
    "rationale_shape": _rationale_shape_view,
    "score_quantization": _score_quantization_view,
}


# --------------------------------------------------------------------------------------------------
# 3. Fusion + community detection
# --------------------------------------------------------------------------------------------------
def fuse(edges: list[Edge], profile_ids: list[str]):
    """Collapse the multi-view edge sets into one weighted graph with noisy-OR fusion.

    Noisy-OR rather than a sum, for the reason ``aggregate.py`` documents at the batch level:
    coordination is disjunctive. Two accounts linked by a quote echo AND a shared cohort are more
    strongly linked than by either alone, but the combination must saturate towards 1 rather than
    run away, and a third weak view must not be able to add as much as the first strong one did.
    """
    import networkx as nx

    G = nx.Graph()
    G.add_nodes_from(profile_ids)
    per_pair: dict[tuple[str, str], list[Edge]] = {}
    for e in edges:
        per_pair.setdefault(tuple(sorted((e.a, e.b))), []).append(e)

    for (a, b), es in per_pair.items():
        prod = 1.0
        for e in es:
            rel = VIEW_RELIABILITY.get(e.view, 0.4)
            prod *= (1.0 - min(0.99, e.weight * rel))
        w = 1.0 - prod
        G.add_edge(a, b, weight=w,
                   views=sorted({e.view for e in es}),
                   reasons=[e.reason for e in es])
    return G


def detect_communities(G, seeds: tuple[int, ...] = (1, 7, 13, 29, 101)) -> list[set[str]]:
    """Consensus Louvain over multiple seeds and resolutions, then k-core pruning.

    Louvain maximises modularity, which asks exactly the right question: is this group denser than
    the configuration-model null expects? But Louvain is stochastic and resolution-dependent, so a
    single run produces boundaries that move between invocations, which is intolerable when the
    output is a published claim about named people.

    So: run it repeatedly, accumulate a co-association matrix (how often each pair landed together),
    keep only pairs that co-occurred in a majority of runs, and take connected components of that
    stable graph. Ensemble clustering, and it converts Louvain's instability into a measurable
    stability instead of a hidden one.

    ``k_core(2)`` then strips pendant nodes: an account attached to a cluster by a single edge is a
    bridge or a coincidence, not a participant.
    """
    import networkx as nx
    from networkx.algorithms.community import louvain_communities

    live = G.subgraph([n for n in G.nodes if G.degree(n) > 0]).copy()
    if live.number_of_nodes() < MIN_CLUSTER_SIZE:
        return []

    co: Counter = Counter()
    runs = 0
    for seed in seeds:
        for resolution in (0.7, 1.0, 1.4):
            parts = louvain_communities(live, weight="weight", resolution=resolution, seed=seed)
            runs += 1
            for part in parts:
                members = sorted(part)
                for i in range(len(members)):
                    for j in range(i + 1, len(members)):
                        co[(members[i], members[j])] += 1

    stable = nx.Graph()
    stable.add_nodes_from(live.nodes)
    for (a, b), c in co.items():
        if c / runs >= 0.6 and live.has_edge(a, b):
            stable.add_edge(a, b, weight=live[a][b]["weight"], stability=c / runs)

    pruned = nx.k_core(stable, k=2) if stable.number_of_edges() else stable
    return [set(c) for c in nx.connected_components(pruned) if len(c) >= MIN_CLUSTER_SIZE]


# --------------------------------------------------------------------------------------------------
# 4. Significance: the band-preserving permutation test
# --------------------------------------------------------------------------------------------------
@dataclass
class Significance:
    """Result of the permutation test, including whether the test had any power at all."""

    p_value: float | None        # None when no usable null could be built
    strata: str                  # "band" | "band_adjacent" | "unstratified" | "none"
    distinct_draws: float        # size of the null space that was actually available
    note: str


_MIN_NULL_SPACE = 20.0  # below this many distinct possible draws, a permutation test says nothing


def _null_space(want: Counter, pool: dict[int, list[str]]) -> float:
    """How many distinct member sets the null can actually produce."""
    total = 1.0
    for b, k in want.items():
        m = len(pool.get(b, []))
        if m < k:
            return 0.0
        total *= math.comb(m, k)
        if total > 1e12:
            return 1e12
    return total


def permutation_significance(G, cluster: set[str], feats_by_id: dict[str, ProfileFeatures],
                             permutations: int = PERMUTATIONS,
                             seed: int = 12345) -> Significance:
    """Is this group more mutually similar than a RANDOM group with the same score composition?

    This is the test that stops the system reporting a score band as a campaign: the null resamples
    node sets matching the cluster's per-band composition, holding fixed the confound the whole
    design is built around (high scorers share vocabulary *because* they are high scorers).

    THE SMALL-SAMPLE TRAP, which cost a correct detection the first time this ran. A stratified
    permutation test silently degenerates when a stratum is barely larger than the sample drawn from
    it. On an 11-profile batch, the campaign occupied 3 of the 3 accounts in its score band, so every
    "random" draw was the cluster itself, the null distribution collapsed onto the observation, and a
    group with 100%-identical quoted text came back at p = 0.50 and was gated down to ambiguous. The
    test was not wrong about its own arithmetic. It had no power, and reported that as evidence of
    nothing unusual.

    So the null is built in tiers, and the size of the null space is checked BEFORE the p-value is
    believed:

    1. ``band``            - exact score-band composition. The strongest control. Used when the pool
                             supports at least ``_MIN_NULL_SPACE`` distinct draws.
    2. ``band_adjacent``   - widen each stratum to the neighbouring bands. Weaker control of the
                             score confound, still far better than none.
    3. ``unstratified``    - draw from the whole batch. Reported as such, because it no longer rules
                             out "these are just the high scorers".
    4. ``none``            - the batch is too small for any test. Returns ``p_value=None``.

    A ``None`` p-value must never be treated as a high p-value. It means the question was not asked,
    and the caller lowers *confidence* rather than the score. Reporting "not significant" for a test
    that could not run is how a real finding gets thrown away.
    """
    import random

    rng = random.Random(seed)
    members = sorted(cluster)
    if len(members) < 2:
        return Significance(None, "none", 0.0, "cluster too small to test")

    def mean_pair_weight(nodes: list[str]) -> float:
        tot, cnt = 0.0, 0
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                d = G.get_edge_data(nodes[i], nodes[j])
                tot += float(d["weight"]) if d else 0.0
                cnt += 1
        return tot / max(1, cnt)

    observed = mean_pair_weight(members)
    by_band: dict[int, list[str]] = {}
    for pid, f in feats_by_id.items():
        by_band.setdefault(f.band, []).append(pid)
    want = Counter(feats_by_id[m].band for m in members if m in feats_by_id)

    # Tier 1: exact bands.
    tiers: list[tuple[str, Counter, dict[int, list[str]]]] = [("band", want, by_band)]
    # Tier 2: each stratum widened to its neighbours.
    adj: dict[int, list[str]] = {}
    for b in want:
        merged: list[str] = []
        for nb in (b - 1, b, b + 1):
            merged.extend(by_band.get(nb, []))
        adj[b] = merged
    tiers.append(("band_adjacent", want, adj))
    # Tier 3: no stratification at all.
    everyone = sorted(feats_by_id)
    tiers.append(("unstratified", Counter({0: len(members)}), {0: everyone}))

    for name, w, pool in tiers:
        space = _null_space(w, pool)
        if space < _MIN_NULL_SPACE:
            continue
        hits = 0
        for _ in range(permutations):
            draw: list[str] = []
            for b, k in w.items():
                draw.extend(rng.sample(pool[b], k))
            if mean_pair_weight(draw) >= observed:
                hits += 1
        p = (hits + 1) / (permutations + 1)
        note = {
            "band": "null preserves each member's score band",
            "band_adjacent": "score bands widened to neighbours: the exact-band null was degenerate "
                             "(the cluster filled its own stratum), so the score confound is only "
                             "partly controlled",
            "unstratified": "no score stratification was possible on a batch this small, so this "
                            "p-value does NOT rule out the group being merely the high scorers",
        }[name]
        return Significance(round(p, 4), name, space, note)

    return Significance(
        None, "none", 0.0,
        "batch too small for a permutation test: no resampling scheme produced enough distinct "
        "groups to compare against. Judge this cluster on its evidence, not on significance.",
    )


# --------------------------------------------------------------------------------------------------
# 5. Coordination scoring + labelling
# --------------------------------------------------------------------------------------------------
def _robust_botness(scores: list[int]) -> float:
    """Median rather than mean: one 95 among four 20s must not read as a bot cluster."""
    return statistics.median(scores) / 100.0 if scores else 0.0


def score_cluster(G, cluster: set[str], edges: list[Edge],
                  feats_by_id: dict[str, ProfileFeatures]) -> dict[str, float]:
    members = sorted(cluster)
    inside = [e for e in edges if e.a in cluster and e.b in cluster]
    by_view: dict[str, list[float]] = {}
    for e in inside:
        by_view.setdefault(e.view, []).append(e.weight)

    n = len(members)
    possible = n * (n - 1) / 2.0
    present = sum(1 for i in range(n) for j in range(i + 1, n) if G.has_edge(members[i], members[j]))
    density = present / possible if possible else 0.0

    strengths = [
        float(G[members[i]][members[j]]["weight"])
        for i in range(n) for j in range(i + 1, n) if G.has_edge(members[i], members[j])
    ]
    cohesion = statistics.mean(strengths) if strengths else 0.0

    disc = [v for v in by_view if v in DISCRIMINATIVE_VIEWS]
    # Saturating size prior: 3 members clears the floor, 20 identical accounts is a stronger claim
    # than 3, and beyond ~25 extra members add nothing (the operation is already established).
    size_prior = min(1.0, math.log1p(n - MIN_CLUSTER_SIZE + 1) / math.log(25.0))

    return {
        "density": density,
        "cohesion": cohesion,
        "view_multiplicity": min(1.0, len(by_view) / 3.0),
        "discriminative_views": float(len(disc)),
        "size_prior": size_prior,
        "quote_strength": max(by_view.get("quote_echo", [0.0])),
        "cohort_strength": max(by_view.get("numeric_cohort", [0.0])),
        "handle_strength": max(by_view.get("handle_morphology", [0.0])),
    }


def combine_coordination(components: dict[str, float], sig: Significance) -> float:
    """Weighted mean and noisy-OR, take the max, then apply the corroboration gate.

    The same two-view combination ``aggregate.py`` settled on after the Tier-2B evaluation, for the
    same reason: a plain mean demands consensus across lenses and so buries a campaign that lights
    up two strong signals and nothing else, while a plain OR lets one non-discriminative lens carry
    a group of unrelated real people to maximal.
    """
    mean_terms = [
        (components["density"], 0.9),
        (components["cohesion"], 1.0),
        (components["view_multiplicity"], 0.7),
        (components["size_prior"], 0.5),
    ]
    wsum = sum(w for _, w in mean_terms) or 1.0
    weighted_mean = sum(v * w for v, w in mean_terms) / wsum

    prod = 1.0
    for key, rel in (("quote_strength", VIEW_RELIABILITY["quote_echo"]),
                     ("cohort_strength", VIEW_RELIABILITY["numeric_cohort"]),
                     ("handle_strength", VIEW_RELIABILITY["handle_morphology"])):
        prod *= (1.0 - min(0.99, components.get(key, 0.0) * rel))
    corroboration = 1.0 - prod

    score = max(weighted_mean, corroboration)

    # Significance gate. A group a same-band random draw reproduces is not a finding, whatever its
    # internal density looks like.
    #
    # `p_value is None` means the test COULD NOT RUN, which is not the same fact and must not be
    # penalised the same way. Treating "unasked" as "answered no" is precisely what threw away a
    # cluster with 100%-identical quoted text on the first run of this pipeline. When the test is
    # unavailable the corroboration gate below carries the whole burden, which is the right
    # fallback: it asks for hard-to-fake evidence rather than for statistical power the batch does
    # not have.
    if sig.p_value is not None:
        if sig.p_value > 0.05:
            score = min(score, 0.45)
        if sig.p_value > 0.20:
            score = min(score, 0.25)

    # Corroboration gate: no discriminative view means no strong verdict, ever.
    if components["discriminative_views"] < 1:
        score = min(score, SUPPORTING_ONLY_CEILING)
    # Without a usable null, one discriminative view is not enough for a maximal verdict either.
    if sig.p_value is None and components["discriminative_views"] < 2:
        score = min(score, 0.59)
    return round(min(1.0, max(0.0, score)), 4)


def label_cluster(coordination: float, botness: float, sig: Significance, n_members: int) -> str:
    """The 2-D decision grid. Coordination and botness are read as separate axes.

    ``coordinated_authentic`` is the class that exists because of the constitution's confusable
    shapes: fan communities, brand accounts and news feeds genuinely do share vocabulary, join in
    cohorts and post repetitively. Detecting real coordination among real people is a CORRECT
    finding, and reporting it as a bot campaign is the mistake that gets a real person defamed.

    Note the ordering. A group that the null reproduces easily AND whose members score low is
    ``organic_cluster``, not ``ambiguous``: that is a confident negative and it is the most
    reassuring thing a report can say. ``ambiguous`` is reserved for genuine uncertainty, so that
    the word keeps meaning "we could not tell" rather than "nothing to see".
    """
    if n_members < MIN_CLUSTER_SIZE:
        return "insufficient_evidence"

    # Confident negative: the null explains it and the members do not look like bots.
    if sig.p_value is not None and sig.p_value > 0.20 and botness < 0.45:
        return "organic_cluster"
    if sig.p_value is not None and sig.p_value > 0.20:
        return "bot_swarm_uncoordinated" if botness >= 0.70 else "ambiguous"
    if coordination < 0.35:
        return "organic_cluster" if botness < 0.35 else "ambiguous"
    if coordination >= 0.60 and botness >= 0.55:
        return "coordinated_bot_campaign"
    if coordination >= 0.60 and botness < 0.35:
        return "coordinated_authentic"
    if coordination >= 0.60:
        return "coordinated_mixed"
    if botness >= 0.70:
        return "bot_swarm_uncoordinated"
    return "ambiguous"


# --------------------------------------------------------------------------------------------------
# 6. Cross-investigation signature
# --------------------------------------------------------------------------------------------------
def campaign_signature(cluster: set[str], feats_by_id: dict[str, ProfileFeatures],
                       num_perm: int = 32, bands: int = 8) -> tuple[tuple[int, ...], list[str]]:
    """A MinHash sketch of the campaign's DISCRIMINATIVE features, not its member list.

    Member-set overlap already links a campaign to itself when the same accounts reappear
    (``CampaignService._match_or_create``). This is the other half, and the one the cross-tenant
    requirement actually needs: an operation that rotates its accounts between posts shares no
    members with its own previous run, but it keeps its script, its handle factory and its
    account-creation cohort. Sketching those makes "different accounts, different investigation,
    different customer, same operation" an indexed lookup rather than an O(n^2) comparison.

    Deliberately excludes profile ids, so a signature reveals nothing about who was scanned.
    """
    tokens: set[str] = set()
    for pid in cluster:
        f = feats_by_id.get(pid)
        if f is None:
            continue
        for sh in list(f.quote_shingles)[:400]:
            tokens.add(f"q:{sh}")
        if f.handle_skeleton:
            tokens.add(f"h:{f.handle_skeleton}")
        if f.cohort:
            tokens.add(f"c:{f.cohort}")
        for c in f.claim_types:
            tokens.add(f"r:{c}")
    sketch = _minhash(frozenset(tokens), num_perm=num_perm)
    rows = max(1, num_perm // bands)
    band_keys = [
        hashlib.blake2b(
            repr(sketch[i * rows:(i + 1) * rows]).encode(), digest_size=8
        ).hexdigest()
        for i in range(bands)
    ]
    return sketch, band_keys


def signature_similarity(a: tuple[int, ...], b: tuple[int, ...]) -> float:
    """Estimated Jaccard between two campaign signatures."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(1 for x, y in zip(a, b) if x == y) / float(len(a))


# --------------------------------------------------------------------------------------------------
# 7. The pipeline
# --------------------------------------------------------------------------------------------------
def analyze(results: list[ProfileResult], *, permutations: int = PERMUTATIONS) -> CampaignAnalysis:
    """Full pipeline: extract, build views, fuse, cluster, test, score, label, explain."""
    if not results:
        return CampaignAnalysis(clusters=[], lone_wolves=[], unclustered=[],
                                batch_notes=["empty batch"])

    feats = extract_features(results)
    feats_by_id = {f.profile_id: f for f in feats}
    ids = [f.profile_id for f in feats]

    edges: list[Edge] = []
    active_views: list[str] = []
    for name, builder in VIEW_BUILDERS.items():
        produced = builder(feats)
        if produced:
            active_views.append(name)
        edges.extend(produced)

    G = fuse(edges, ids)
    communities = detect_communities(G)

    clustered: set[str] = set()
    verdicts: list[ClusterVerdict] = []
    for cluster in communities:
        clustered |= cluster
        comp = score_cluster(G, cluster, edges, feats_by_id)
        sig = permutation_significance(G, cluster, feats_by_id, permutations=permutations)
        coordination = combine_coordination(comp, sig)
        botness = _robust_botness([feats_by_id[m].omi_score for m in cluster if m in feats_by_id])
        label = label_cluster(coordination, botness, sig, len(cluster))

        inside = [e for e in edges if e.a in cluster and e.b in cluster]
        views_ranked = sorted(
            {e.view for e in inside},
            key=lambda v: -max(x.weight for x in inside if x.view == v) * VIEW_RELIABILITY.get(v, 0.4),
        )
        verdicts.append(ClusterVerdict(
            members=sorted(cluster),
            coordination=coordination,
            botness=round(botness, 4),
            # An untestable cluster is not less coordinated, but we are less sure, and that belongs
            # in confidence rather than in the score.
            confidence=round(min(1.0, (0.25 + 0.25 * len({e.view for e in inside})
                                       + 0.2 * comp["discriminative_views"])
                                 * (0.7 if sig.p_value is None else 1.0)), 4),
            p_value=sig.p_value,
            significance=sig,
            label=label,
            views=views_ranked,
            components={k: round(v, 4) for k, v in comp.items()},
            evidence=_cluster_evidence(inside, comp, sig, len(cluster)),
            per_member=_member_evidence(cluster, inside, feats_by_id),
            **dict(zip(("signature", "signature_bands"), campaign_signature(cluster, feats_by_id))),
        ))

    verdicts.sort(key=lambda c: (-c.coordination, -len(c.members)))

    lone = sorted(
        f.profile_id for f in feats
        if f.profile_id not in clustered and f.omi_score >= 70
    )
    unclustered = sorted(f.profile_id for f in feats
                         if f.profile_id not in clustered and f.omi_score < 70)

    notes = [
        f"{len(results)} profiles, {len(active_views)} views produced edges "
        f"({', '.join(active_views) or 'none'})",
        f"graph: {G.number_of_edges()} fused pairs over {G.number_of_nodes()} nodes",
    ]
    if "quote_echo" not in active_views:
        notes.append(
            "no quoted text was recoverable from the verdicts, so the most discriminative view "
            "abstained; treat every cluster below as lower confidence"
        )
    return CampaignAnalysis(clusters=verdicts, lone_wolves=lone, unclustered=unclustered,
                            batch_notes=notes)


def _cluster_evidence(inside: list[Edge], comp: dict[str, float], sig: "Significance",
                      n: int) -> list[str]:
    out = [
        f"{n} accounts, {comp['density']:.0%} of possible pairs linked, "
        f"mean link strength {comp['cohesion']:.2f}",
    ]
    if sig.p_value is None:
        out.append(f"significance NOT TESTED: {sig.note}")
    else:
        out.append(
            f"permutation test (strata: {sig.strata}, {sig.distinct_draws:.0f} possible "
            f"draws): p = {sig.p_value:.3f}. {sig.note}"
        )
    best_per_view: dict[str, Edge] = {}
    for e in inside:
        cur = best_per_view.get(e.view)
        if cur is None or e.weight > cur.weight:
            best_per_view[e.view] = e
    for view in sorted(best_per_view, key=lambda v: -VIEW_RELIABILITY.get(v, 0.4)):
        out.append(f"[{view}] {best_per_view[view].reason}")
    if comp["discriminative_views"] < 1:
        out.append(
            "no discriminative view fired (only shared reasoning vocabulary), so this is capped "
            "below a strong verdict regardless of density"
        )
    return out[:MAX_EXPLANATION_ITEMS + 2]


def _member_evidence(cluster: set[str], inside: list[Edge],
                     feats_by_id: dict[str, ProfileFeatures]) -> dict[str, list[str]]:
    """Why each individual account is in this cluster. Every published claim needs its own basis:
    a cluster-level score is not evidence about the person at position seven."""
    per: dict[str, list[str]] = {m: [] for m in cluster}
    for e in inside:
        for side, other in ((e.a, e.b), (e.b, e.a)):
            if side in per and len(per[side]) < MAX_EXPLANATION_ITEMS:
                per[side].append(f"[{e.view}] linked to {other}: {e.reason}")
    for m in per:
        if not per[m]:
            per[m].append("no direct link; included via a shared neighbour in the stable community")
        f = feats_by_id.get(m)
        if f and f.numerics:
            facts = ", ".join(f"{k}={v:g}" for k, v in sorted(f.numerics.items()))
            per[m].append(f"parsed from verdict: {facts}")
    return per
