"""Shared types for the cohort coordination detector.

The unit of evidence here is an **edge between two accounts**, never a cluster. That is a
deliberate departure from ``app/detection/coordination/``, whose detectors each emit their own
clusters which ``CampaignService.merge_clusters`` then unions on any shared account. One account
appearing in two unrelated detectors' clusters is enough to fuse them into a single fake
mega-campaign. Edges plus community detection cannot do that: a bridge account joins two groups
only if the edges themselves say so, and the density gate in ``fuse.py`` throws out the chain that
results when they do not.

Every hit carries a mandatory ``artifact`` (the raw material the accounts themselves produced) and
a ``sentence`` (one line a human can check). ``fuse.py`` drops any hit with an empty artifact. That
is the deterministic form of the constitution's "if you cannot quote it, you cannot claim it", and
it is what earns the right to put named accounts on a page as a group.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# --------------------------------------------------------------------------------------------
# Families
# --------------------------------------------------------------------------------------------
# Signals are grouped into families of *independent evidence*, and fusion takes the max within a
# family rather than combining. Two methods reading the same underlying material are one kind of
# evidence seen twice, not two kinds: `verbatim_echo` and `bio_echo` are both "these accounts
# emitted the same string", so letting them corroborate each other would mean a copy-paste farm
# clears a gate designed to require independent confirmation. Counting method names would allow
# exactly that; counting families does not.
FAMILY_TEXT = "text"
FAMILY_TIMING = "timing"
FAMILY_NETWORK = "network"
FAMILY_INFRASTRUCTURE = "infrastructure"
FAMILY_IDENTITY = "identity"

METHOD_FAMILY: dict[str, str] = {
    "verbatim_echo": FAMILY_TEXT,
    "bio_echo": FAMILY_TEXT,
    "burst_lockstep": FAMILY_TIMING,
    "co_target": FAMILY_NETWORK,
    "client_signature": FAMILY_INFRASTRUCTURE,
    "provisioning_window": FAMILY_IDENTITY,
    "handle_template": FAMILY_IDENTITY,
}

#: Reliability prior per family, applied to every edge weight that family contributes.
FAMILY_RELIABILITY: dict[str, float] = {
    FAMILY_TEXT: 1.0,
    FAMILY_TIMING: 0.9,
    FAMILY_NETWORK: 0.9,
    FAMILY_INFRASTRUCTURE: 1.0,
    FAMILY_IDENTITY: 0.5,
}

#: Families whose agreement is hard to produce by accident between unrelated real people. A
#: finding needs at least one of these AND a second family of any kind (see `fuse.corroborate`).
DISCRIMINATIVE_FAMILIES: frozenset[str] = frozenset({
    FAMILY_TEXT, FAMILY_TIMING, FAMILY_NETWORK, FAMILY_INFRASTRUCTURE,
})

#: Method names this detector can emit. Kept here so `reports/campaign_pack.py` can report which
#: of them stayed silent without importing the signal modules.
COHORT_METHODS: tuple[str, ...] = tuple(METHOD_FAMILY)

#: The subset a campaign may lean on. Mirrors DISCRIMINATIVE_FAMILIES at method granularity.
COHORT_DISCRIMINATIVE: frozenset[str] = frozenset(
    m for m, f in METHOD_FAMILY.items() if f in DISCRIMINATIVE_FAMILIES
)

#: Bumped whenever a threshold moves. Stored on every run so a later recalibration can tell which
#: findings were produced under which constants. Every constant in this package is reasoned rather
#: than fitted, so this is not decoration.
THRESHOLDS_VERSION = "cohort-v1"


# --------------------------------------------------------------------------------------------
# Input
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ThreadComment:
    """One comment an account left *on the scanned post*.

    Distinct from an activity sample, which comes from the account's own timeline. The
    distinction matters: co-timing is only evidence when both accounts were commenting on the
    same thing, and the thread is the only place that is true.
    """

    text: str
    created_at: datetime | None = None
    comment_id: str | None = None
    parent_comment_id: str | None = None


@dataclass(frozen=True)
class ActivitySample:
    """One post from the account's own timeline (``recent_activity`` in the payload)."""

    text: str
    created_at: datetime | None = None
    parent_id: str | None = None
    source_client: str | None = None
    reply_to_id: str | None = None
    repost_of_id: str | None = None

    def targets(self) -> list[str]:
        """Every distinct thing this post points at. Used by `co_target`."""
        return [t for t in (self.parent_id, self.reply_to_id, self.repost_of_id) if t]


@dataclass
class CohortAccount:
    """One member of the 70+ cohort, with everything the signals may read.

    ``bio`` keeps the payload's distinction between ``""`` (the account has no bio, which is a
    real observation) and ``None`` (the platform never told us). Collapsing them would let
    `bio_echo` match every account whose bio we simply failed to fetch.
    """

    external_id: str
    handle: str
    score: float                      # 0-100, whichever scale `score_source` names
    score_source: str                 # "analyst" | "engine"
    bio: str | None = None
    account_created_at: datetime | None = None
    thread_comments: list[ThreadComment] = field(default_factory=list)
    activity: list[ActivitySample] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.handle or self.external_id


@dataclass
class BatchBackground:
    """Everything below the 70 cut, plus the whole thread, kept only as a null.

    Filtering to 70+ removes the *cohort's* internal background but not the batch's: every
    lower-scoring account is still in ``payload_json`` and every comment under the post is still
    available. So a signal that needs a null can have one, drawn from material the filter never
    touched, while only cohort members are ever reported as campaign members.

    Nothing in here is ever named in a finding.
    """

    #: Every comment timestamp under the post, from every author, scanned or not. The arrival
    #: process `burst_lockstep` tests against.
    thread_comment_times: list[datetime] = field(default_factory=list)
    #: True number of comments under the post, which exceeds ``len(thread_comment_times)`` when the
    #: persisted list was capped. The rate is scaled back up by this so truncation cannot make a
    #: busy thread look quiet.
    thread_arrival_total: int = 0
    #: Whether ``thread_comment_times`` covers EVERY author under the post, or only the scanned
    #: accounts. `burst_lockstep` abstains entirely when this is False: a rate measured over the
    #: scanned subset is lower than the real one, which makes ordinary co-timing look significant,
    #: which is the error that turns a busy comment section into an accusation. False is the
    #: expected state for investigations persisted before ``video.thread_arrivals`` existed.
    arrivals_complete: bool = False
    #: Distinct authors under the post, for the copypasta share gate.
    thread_author_count: int = 0
    #: normalised text -> how many distinct authors posted it. Above a share threshold a repeated
    #: string is a meme, not a script.
    text_author_counts: dict[str, int] = field(default_factory=dict)
    #: Creation timestamps of every scanned account, the empirical distribution
    #: `provisioning_window` tests against. Platform growth is famously non-uniform, so a
    #: theoretical uniform prior would fire on signup spikes.
    batch_created_at: list[datetime] = field(default_factory=list)
    #: handle skeleton -> count across the whole batch, for `handle_template`'s rarity gate.
    handle_skeleton_counts: dict[str, int] = field(default_factory=dict)
    #: target id -> how many batch accounts engaged it, for `co_target`'s rarity gate.
    target_counts: dict[str, int] = field(default_factory=dict)
    #: client string -> how many batch accounts used it, for `client_signature`'s strengthening.
    client_counts: dict[str, int] = field(default_factory=dict)
    #: How many accounts the scan actually scored, cohort included.
    scanned_total: int = 0

    def text_author_share(self, key: str) -> float:
        if self.thread_author_count <= 0:
            return 0.0
        return self.text_author_counts.get(key, 0) / self.thread_author_count

    def batch_share(self, counts: dict[str, int], key: str) -> float:
        if self.scanned_total <= 0:
            return 0.0
        return counts.get(key, 0) / self.scanned_total


@dataclass
class Cohort:
    """The detector's whole input."""

    accounts: list[CohortAccount]
    background: BatchBackground
    platform: str = "unknown"
    score_source: str = "engine"
    score_threshold: float = 70.0

    def by_id(self) -> dict[str, CohortAccount]:
        return {a.external_id: a for a in self.accounts}


# --------------------------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Edge:
    """One signal's claim that two specific accounts are linked.

    ``artifact`` is the raw material (the repeated string, the two timestamps, the shared id).
    ``sentence`` is the same fact written for a human. Both are required; `fuse` discards an edge
    whose artifact is empty, because a claim nobody can check is not evidence.

    ``weight`` is kept only as a human-readable strength for display and ordering. **It is not what
    decides anything** any more: the verdict is a posterior computed from ``log10_lr``. Two numbers
    on one object is a smell, so if `weight` ever stops being rendered, delete it.

    ``measured_p`` is the signal's own p-value where the signal has a null model (`burst_lockstep`,
    `provisioning_window`). It is exactly ``P(evidence | independent)``, which is the denominator of
    the likelihood ratio, so those two signals get a data-derived ratio per observation instead of
    an estimated constant.
    """

    a: str
    b: str
    method: str
    weight: float
    sentence: str
    artifact: str
    statistic: tuple[str, float] | None = None
    measured_p: float | None = None

    @property
    def family(self) -> str:
        return METHOD_FAMILY[self.method]

    @property
    def pair(self) -> tuple[str, str]:
        return (self.a, self.b) if self.a <= self.b else (self.b, self.a)

    @property
    def log10_lr(self) -> float:
        """How much this observation moves the odds. The only number that decides anything."""
        from app.campaigns.detector.probability import log10_lr

        return log10_lr(self.method, self.measured_p)


@dataclass
class Finding:
    """One group of accounts and the case for it.

    ``score`` is the group's posterior probability of coordination, and it is the **weakest**
    member's admitting posterior rather than the strongest or the mean. A group is only as
    defensible as the least defensible person named in it, and that person is the one who gets hurt
    if this is wrong.
    """

    finding_id: str
    members: list[str]                       # external ids, sorted
    score: float
    label: str
    capped: bool
    density: float
    families_fired: list[str]
    families_silent: list[str]
    methods: list[str]
    edges: list[Edge]
    evidence: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    #: Each member's own posterior link to the group. This is what admitted them, and showing it
    #: per account is what lets a reviewer challenge one name without dismissing the whole finding.
    member_posteriors: dict[str, float] = field(default_factory=dict)
    #: The prior this run used, stamped so a finding stays interpretable after the prior moves.
    prior: float = 0.0
    lr_version: str = ""
    #: One human-readable line showing how the strongest pair's number was reached. A posterior with
    #: no visible derivation is exactly as unaccountable as the score it replaced.
    derivation: str = ""


@dataclass
class DetectionRun:
    """Everything one pass over one investigation produced."""

    findings: list[Finding]
    cohort_size: int
    scanned_total: int
    score_source: str
    platform: str
    passes: int = 1
    thresholds_version: str = THRESHOLDS_VERSION
    lone_high_scorers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def best_score(self) -> float:
        return max((f.score for f in self.findings), default=0.0)

    @property
    def best_label(self) -> str:
        if not self.findings:
            return "no_campaign_detected"
        return max(self.findings, key=lambda f: f.score).label
