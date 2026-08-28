"""Core types for the coordinated-network detector.

THE UNIT OF EVIDENCE IS A FEATURE, NOT A PAIR.

The previous detector asked "do accounts a and b share X" and assembled groups out of strong pairs.
That decomposition can never ask the question that actually matters: *how improbable is it that
THESE k accounts all share something this rare?* A set-level statistic is not recoverable by fusing
pairwise ones, so this design makes the set the unit from the start.

An account becomes a bag of ``Feature`` tokens. All accounts together form a bipartite graph of
accounts against features. Detection is then a search over that graph for sets that share improbably
many rare features, tested against a null that holds both degree sequences fixed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------------------------- #
# Families
# --------------------------------------------------------------------------------------------- #
#
# Features inside one family are NOT independent: two 5-gram shingles from the same post co-occur
# perfectly, and summing their surprises would multiply one observation into several. Families are
# the independence assumption written down, exactly as ``detector/types.METHOD_FAMILY`` is for the
# older detector, and the scorer discounts within a family before summing across them.

FAMILY_TEXT = "text"                    # what the account wrote
FAMILY_TIMING = "timing"                # when it acts
FAMILY_NETWORK = "network"              # who and what it engages
FAMILY_INFRASTRUCTURE = "infrastructure"  # what it publishes with
FAMILY_IDENTITY = "identity"            # how the account itself was made
FAMILY_NARRATIVE = "narrative"          # topic, once real embeddings land

ALL_FAMILIES: tuple[str, ...] = (
    FAMILY_TEXT, FAMILY_TIMING, FAMILY_NETWORK,
    FAMILY_INFRASTRUCTURE, FAMILY_IDENTITY, FAMILY_NARRATIVE,
)

#: How much a family's evidence is worth, by how easily it is shared INNOCENTLY.
#:
#: The configuration null measures STATISTICAL rarity: given these degrees, how unlikely is this
#: much sharing. It cannot measure BEHAVIOURAL innocence, and the two come apart badly. Ten city-hall
#: reporters genuinely share a topic, a working day and a newsroom publishing tool; that sharing is
#: statistically rare and completely innocent. This table is where the likelihood ratio's
#: denominator gets the part the null cannot see, and it is the same role the per-method caps play
#: in the older detector's ``probability.py``.
#:
#: The split that matters: IDENTITY and NETWORK are the OPERATOR'S OWN ACTS. Provisioning a batch of
#: accounts in one week under one naming convention, and pointing them at the same outside targets,
#: are things a profession or a fandom does not do. Text, timing and infrastructure are all things a
#: shared job or a shared interest produces for free.
FAMILY_WEIGHT: dict[str, float] = {
    FAMILY_IDENTITY: 1.00,        # how the accounts were MADE. Nobody signs up as a cohort by chance.
    FAMILY_NETWORK: 1.00,         # converging on the same OUTSIDE targets.
    FAMILY_INFRASTRUCTURE: 0.55,  # a shared tool can simply be a shared profession.
    FAMILY_NARRATIVE: 0.45,
    FAMILY_TEXT: 0.45,            # a shared topic is the most innocently shared thing there is.
    FAMILY_TIMING: 0.40,          # a timezone and a working day are shared by millions.
}

#: Families where innocent sharing is genuinely implausible. A finding resting on NONE of these is
#: not necessarily wrong, but it is not resolvable by statistics either, so it goes to a reader
#: rather than to a customer. See ``Candidate.needs_adjudication``.
HARD_FAMILIES: frozenset[str] = frozenset({FAMILY_IDENTITY, FAMILY_NETWORK})


def weighted(by_family: dict[str, float]) -> float:
    return sum(v * FAMILY_WEIGHT.get(k, 0.5) for k, v in by_family.items())


#: Families whose meaning survives a platform change, so an edge between two platforms may rest on
#: them. ``infrastructure`` is X-only (a client string) and ``identity`` compares handle conventions
#: that differ per platform, so a match across two platforms there is evidence about the platforms
#: rather than about the accounts.
PLATFORM_NEUTRAL_FAMILIES: frozenset[str] = frozenset({
    FAMILY_TEXT, FAMILY_NETWORK, FAMILY_TIMING, FAMILY_NARRATIVE,
})


@dataclass(frozen=True, slots=True)
class Feature:
    """One behaviour, as a token.

    ``family`` decides how it combines with others; ``kind`` is the extractor that produced it and
    exists so a finding can be explained in words; ``value`` is the token itself.

    Frozen and slotted because there are a great many of these and they are used as dict keys.
    """

    family: str
    kind: str
    value: str

    def token(self) -> str:
        return f"{self.kind}:{self.value}"


@dataclass(slots=True)
class AccountProfile:
    """One account as the detector sees it: an id, a platform, and a set of features.

    ``score`` and ``tier`` ride along but are NEVER used in detection. Coordination and botness are
    orthogonal axes: a dense, improbable cluster of low-scoring accounts is the most valuable thing
    this system can find, and multiplying the two would hide it while letting a pile of unrelated
    high scorers masquerade as an operation. They are carried only so a finding can be described.
    """

    external_id: str
    platform: str
    features: set[Feature] = field(default_factory=set)
    handle: str = ""
    score: float | None = None
    tier: str | None = None

    def tokens_by_family(self) -> dict[str, set[Feature]]:
        out: dict[str, set[Feature]] = {}
        for f in self.features:
            out.setdefault(f.family, set()).add(f)
        return out


@dataclass(slots=True)
class FeatureEvidence:
    """Why one feature counted toward a group's score. The audit trail for a published claim."""

    feature: Feature
    #: How many of the group's accounts exhibit it.
    shared_by: int
    #: How many accounts in the whole corpus exhibit it. The denominator of the rarity claim.
    corpus_count: int
    #: -log10 P(at least this many of the group share it) under the configuration null.
    surprise: float
    #: A short human sentence. "If you cannot quote it, you cannot claim it" applies here too.
    sentence: str = ""


@dataclass(slots=True)
class Candidate:
    """A set of accounts proposed as an operation, before and after the search correction."""

    members: list[str]
    platform: str
    #: Total surprise in log10 units, after within-family discounting.
    score: float
    #: Per-family contribution, so a reviewer can see whether one family is carrying everything.
    by_family: dict[str, float] = field(default_factory=dict)
    evidence: list[FeatureEvidence] = field(default_factory=list)
    #: Set once the candidate has been compared against the distribution of the shuffled maximum.
    #: None means "not yet corrected", which must never be read as "significant".
    corrected_p: float | None = None
    refused: str | None = None
    #: Why a human has to look at this before it reaches a customer, or None when the evidence
    #: settles it. A finding built only from families a profession or a community shares for free
    #: cannot be resolved statistically, and pretending a threshold resolves it is how this product
    #: would publish an accusation about a real community.
    needs_adjudication: str | None = None
    #: Members that do not carry this finding, from `app.netdetect.attachment`. A REPORT, never an
    #: exclusion: these accounts are still members and still named, and a reader decides. Empty
    #: also when the test abstained, so read `attachment_note` before concluding anything from it.
    weakly_attached: list[str] = field(default_factory=list)
    #: Why no verdict was reached on membership, or None when one was. Never read the absence of
    #: `weakly_attached` entries as "every member belongs".
    attachment_note: str | None = None
    #: Whether the membership test actually ran. EXPLICIT on purpose: an empty `weakly_attached`
    #: means "checked, every member carries the finding" when this is True and "could not check"
    #: when it is False, and those are opposite statements about the people named. Same distinction
    #: as `score: null` against `0` on the analyst's signals.
    attachment_checked: bool = False

    @property
    def weighted_score(self) -> float:
        from app.netdetect.types import weighted as _w

        return _w(self.by_family)

    @property
    def hard_evidence(self) -> float:
        return sum(v * FAMILY_WEIGHT.get(k, 0.5)
                   for k, v in self.by_family.items() if k in HARD_FAMILIES)

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def families_firing(self) -> int:
        return sum(1 for v in self.by_family.values() if v > 0)
