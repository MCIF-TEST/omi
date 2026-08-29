"""A formation is an ENTITY, not a search result.

WHY THIS EXISTS. `detect` answers "are these accounts, in this corpus, coordinated?" and then
forgets. Every run starts from nothing. So the system cannot say the one thing an investigator most
wants said: *we have seen this operation before*. A finding is an event; an operation is a thing that
persists, rotates its accounts, goes quiet and comes back.

This module makes the operation a first-class object with a lifecycle, and it is the substrate for
`app/netdetect/assign.py`, which places a newly scanned account into a formation that was catalogued
weeks earlier and in a different investigation.

---------------------------------------------------------------------------------------------------
A FORMATION IS DEFINED BY ITS EVIDENCE, NOT BY ITS MEMBERS
---------------------------------------------------------------------------------------------------

The obvious representation is "the set of accounts", and it is the wrong one twice over. A serious
operation burns its accounts between runs, so a member list identifies the run rather than the
operator. And a member list cannot answer "does this new account belong", because the answer would
be a tautology.

So a formation carries the features that were *evidence*: the rare things its members shared that
made the set improbable in the first place. Not everything the members do. That distinction is the
same one `persist.pair_evidence_from` draws for pairs, and for the same reason: crediting everything
a member happens to do invents significance nobody measured.

---------------------------------------------------------------------------------------------------
THE OMI SCORE IS CARRIED AND NEVER DETECTS
---------------------------------------------------------------------------------------------------

`detect` is score-blind on purpose, and that must not change: the old 70+ cohort filter was blind BY
CONSTRUCTION to the operation worth catching most, one running on aged accounts with hand-written
posts that each score 30 alone. Reading the score into detection would rebuild that blindness.

But refusing to read it into detection is not a reason to throw it away. `Composition` reads the
scores of a formation's members AFTER the formation has been found, and turns them into the thing an
operator actually needs: which of these formations should I look at first.

The interesting output is inverted from the obvious one. A formation of eight accounts that each
score 85 is a group of accounts the per-account engine ALREADY flags; an analyst would have found
them anyway. A formation of eight accounts that each score 22, that the engine sees as ordinary
people, and that a degree-preserving null says is nonetheless improbably coordinated, is the finding
that only this system can produce. `Composition.concealment` names that case, and it is the reason to
carry the score at all.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.netdetect.significance import Corpus
from app.netdetect.types import ALL_FAMILIES, Candidate, Feature

# --------------------------------------------------------------------------------------------- #
# The discriminative profile
# --------------------------------------------------------------------------------------------- #

#: Features carried forward as the formation's identity. Beyond this the tail contributes almost
#: nothing after harmonic discounting, and a fat profile makes assignment slower and looser.
MAX_PROFILE_FEATURES = 60

#: A feature held by more than this share of the corpus it was measured in is not identifying, and
#: carrying it would make the formation match any account that happens to do an ordinary thing. This
#: mirrors `significance.RARITY_CEILING` and exists separately because a profile outlives the corpus
#: it was built from: nothing downstream can re-check prevalence once the corpus is gone.
PROFILE_PREVALENCE_CEILING = 0.25


@dataclass(frozen=True, slots=True)
class ProfileFeature:
    """One feature that helped make a formation improbable, with what made it so.

    `surprise` and `prevalence` are frozen at the moment of measurement. The corpus they came from is
    not kept, so these are the only record of how rare this behaviour was when it was evidence, and
    an assignment made months later is honest precisely because it uses the measured value rather
    than re-deriving one from whatever corpus happens to be at hand.
    """

    family: str
    kind: str
    value: str
    #: -log10 P(at least this many of the group share it) under the configuration null, at the time.
    surprise: float
    #: Share of the measuring corpus that exhibited it. Lower is more identifying.
    prevalence: float

    def token(self) -> str:
        return f"{self.kind}:{self.value}"

    def as_feature(self) -> Feature:
        return Feature(self.family, self.kind, self.value)


@dataclass(slots=True)
class FormationProfile:
    """What a formation IS, independent of which accounts are currently running it."""

    features: list[ProfileFeature] = field(default_factory=list)
    #: Families the evidence spans. A formation resting on one family is one kind of evidence
    #: however many times it fired, and assignment refuses to be confident about it.
    families: set[str] = field(default_factory=set)
    #: Corpus the profile was measured in, so a reader can weigh a finding among 30 accounts against
    #: the same finding among 3,000.
    corpus_size: int = 0
    #: Which platform this operation was observed on. Carried so `assign` can apply the rule
    #: `campaigns/tracking/crossplatform.py` already states: a cross-platform claim may rest only
    #: on evidence that means the same thing on both services. Empty means unknown, which is read
    #: as "do not restrict" rather than as a mismatch, so profiles stored before this existed keep
    #: behaving as they did.
    platform: str = ""

    @property
    def hard_families(self) -> set[str]:
        from app.netdetect.types import HARD_FAMILIES

        return self.families & set(HARD_FAMILIES)

    def by_token(self) -> dict[str, ProfileFeature]:
        return {f.token(): f for f in self.features}


#: Feature kinds that identify a MOMENT rather than a behaviour, and so can never be part of an
#: operation's durable identity.
#:
#: `arrival` is a wall-clock bucket under one specific post. Two accounts under that post can
#: meaningfully share it; an account seen six weeks later on a different post cannot, and any match
#: it produces is a coincidence of the calendar. A formation profile is supposed to survive account
#: rotation precisely BECAUSE it holds only what the operator keeps doing, so a timestamp in it is a
#: category error.
#:
#: Measured before this exclusion: a member of the fan-community control was assigned to a
#: catalogued operation, which is the most serious error this system can make because assignment
#: names a real person as part of one.
CONTEXTUAL_KINDS: frozenset[str] = frozenset({"arrival"})


def build_profile(candidate: Candidate, corpus: Corpus) -> FormationProfile:
    """Distil a finding into the operation's identity.

    Reads the candidate's own evidence list rather than the members' full feature bags, so what
    identifies the formation later is exactly what a reader was shown as the reason for it now.
    """
    size = max(1, corpus.size)
    picked: list[ProfileFeature] = []
    for item in candidate.evidence or []:
        if item.feature.kind in CONTEXTUAL_KINDS:
            # A moment, not a behaviour. See CONTEXTUAL_KINDS.
            continue
        prevalence = item.corpus_count / size
        if prevalence > PROFILE_PREVALENCE_CEILING:
            # It was not identifying even where it was measured. Carrying it would make the
            # formation match any account that happens to do an ordinary thing.
            continue
        picked.append(ProfileFeature(
            family=item.feature.family,
            kind=item.feature.kind,
            value=item.feature.value,
            surprise=round(float(item.surprise), 6),
            prevalence=round(prevalence, 6),
        ))

    picked.sort(key=lambda f: (-f.surprise, f.token()))
    picked = picked[:MAX_PROFILE_FEATURES]
    return FormationProfile(
        features=picked,
        families={f.family for f in picked},
        corpus_size=corpus.size,
    )


# --------------------------------------------------------------------------------------------- #
# Composition: the OMI score, used where it belongs
# --------------------------------------------------------------------------------------------- #

#: At or below this median OMI a formation's members read as ordinary people to the per-account
#: engine. Combined with a real coordination finding that is the CONCEALED case, and it is the one
#: worth surfacing first.
CONCEALED_MEDIAN_SCORE = 40.0

#: At or above this median the per-account engine already flags them; coordination adds structure to
#: a suspicion somebody could have reached without it.
OVERT_MEDIAN_SCORE = 70.0


@dataclass(slots=True)
class Composition:
    """What the per-account engine thinks of a formation's members, computed AFTER detection.

    Never an input to detection. See the module docstring: reading the score into the search is how
    the previous detector became blind to competent operations.
    """

    scored: int = 0
    unscored: int = 0
    median: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    #: "concealed", "mixed", "overt", or "unknown" when too few members carry a score.
    posture: str = "unknown"
    #: Plain sentence for a reader. The posture name alone invites the wrong reading.
    note: str = ""

    @property
    def concealment(self) -> bool:
        """The finding only this system can produce: coordinated, and individually unremarkable."""
        return self.posture == "concealed"


def composition_of(scores: list[float | None]) -> Composition:
    """Summarise member OMI scores.

    An unscored member is counted, never imputed. Substituting a mean for a missing score would let
    a formation of mostly-unscored accounts present a confident posture built from two numbers.
    """
    present = [float(s) for s in scores if s is not None]
    out = Composition(scored=len(present), unscored=sum(1 for s in scores if s is None))
    if len(present) < 3:
        out.note = (
            "Too few members carry an OMI score to describe this formation's posture. That is a "
            "gap in what was scanned, not a finding about the accounts."
        )
        return out

    out.median = round(statistics.median(present), 1)
    out.minimum = round(min(present), 1)
    out.maximum = round(max(present), 1)

    if out.median <= CONCEALED_MEDIAN_SCORE:
        out.posture = "concealed"
        out.note = (
            f"Median OMI {out.median:.0f}: individually these accounts read as ordinary people, and "
            f"the per-account engine would not have flagged them. The coordination is the whole "
            f"finding, which makes this the shape a competent operation takes."
        )
    elif out.median >= OVERT_MEDIAN_SCORE:
        out.posture = "overt"
        out.note = (
            f"Median OMI {out.median:.0f}: the per-account engine already flags these accounts on "
            f"their own behaviour. Coordination adds structure to a suspicion reachable without it."
        )
    else:
        out.posture = "mixed"
        out.note = (
            f"Median OMI {out.median:.0f}: neither uniformly flagged nor uniformly ordinary. Check "
            f"whether the low-scoring members are the same ones the membership test flagged as "
            f"weakly attached."
        )
    return out


# --------------------------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------------------------- #

#: No sighting for this long and a formation is dormant rather than active. Operations run in
#: campaigns with gaps between them, so silence is a phase and not an ending.
DORMANT_AFTER_DAYS = 21

#: A formation first seen inside this window is still forming: too new for its member roster or its
#: cadence to mean much.
FORMING_WITHIN_DAYS = 7

PHASES = ("forming", "active", "dormant", "resurgent")


def phase_of(
    first_seen: datetime | None,
    last_seen: datetime | None,
    *,
    previous_phase: str | None = None,
    now: datetime | None = None,
) -> str:
    """Where a formation is in its life.

    RESURGENT IS THE PHASE WORTH HAVING. An operation that went quiet for a month and is active again
    is a different claim from one that never stopped, and it is invisible to any per-run detector: it
    only exists if the entity persisted across the gap. It is derived from the PREVIOUS phase rather
    than from the gap alone, because "dormant then seen" is a transition, not a measurement.
    """
    at = now or datetime.now(timezone.utc)
    if first_seen is None or last_seen is None:
        return "forming"

    first_seen = _aware(first_seen)
    last_seen = _aware(last_seen)

    if at - last_seen > timedelta(days=DORMANT_AFTER_DAYS):
        return "dormant"
    if previous_phase == "dormant":
        return "resurgent"
    if at - first_seen <= timedelta(days=FORMING_WITHIN_DAYS):
        return "forming"
    return "active"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------------------------- #
# Merging two profiles: an operation seen twice
# --------------------------------------------------------------------------------------------- #

#: Each additional sighting of the SAME feature contributes this fraction of its surprise.
#:
#: Two sightings of one operation are not independent observations: the same script deployed on two
#: posts is one script. `campaigns/tracking/graph.REPEAT_DISCOUNT` prices the identical problem for
#: pairwise edges, and the number matches deliberately so the two layers do not disagree about how
#: much a repeat is worth.
REPEAT_DISCOUNT = 0.5

#: Ceiling on any one feature's accumulated surprise, however many times it is seen again. Without
#: it a long-lived formation would drift to certainty on one behaviour observed many times, which is
#: the compounding error the repeat discount exists to prevent.
MAX_ACCUMULATED_SURPRISE = 8.0


def merge_profiles(existing: FormationProfile, incoming: FormationProfile) -> FormationProfile:
    """Fold a new sighting into a formation's identity.

    A feature seen again is reinforced but discounted; a feature seen for the first time joins at
    full weight. The profile is then re-trimmed, so a formation's identity tracks what it keeps
    doing rather than growing without bound.
    """
    merged: dict[str, ProfileFeature] = existing.by_token()
    for feature in incoming.features:
        token = feature.token()
        prior = merged.get(token)
        if prior is None:
            merged[token] = feature
            continue
        merged[token] = ProfileFeature(
            family=prior.family,
            kind=prior.kind,
            value=prior.value,
            surprise=round(min(
                MAX_ACCUMULATED_SURPRISE,
                prior.surprise + feature.surprise * REPEAT_DISCOUNT,
            ), 6),
            # Keep the LOWEST prevalence seen: the corpus where it was rarest is the one where it
            # was most identifying, and averaging would let one common sighting dilute that.
            prevalence=round(min(prior.prevalence, feature.prevalence), 6),
        )

    features = sorted(merged.values(), key=lambda f: (-f.surprise, f.token()))
    features = features[:MAX_PROFILE_FEATURES]
    return FormationProfile(
        features=features,
        families={f.family for f in features},
        corpus_size=max(existing.corpus_size, incoming.corpus_size),
    )


def profile_similarity(a: FormationProfile, b: FormationProfile) -> float:
    """Weighted Jaccard over the two profiles, for recognising a rotated operation.

    Weighted by surprise rather than counting tokens: two formations sharing one very rare behaviour
    are more likely the same operator than two sharing five ordinary ones, and a flat Jaccard says
    the opposite.
    """
    left = {f.token(): f.surprise for f in a.features}
    right = {f.token(): f.surprise for f in b.features}
    if not left or not right:
        return 0.0
    keys = set(left) | set(right)
    intersection = sum(min(left.get(k, 0.0), right.get(k, 0.0)) for k in keys)
    union = sum(max(left.get(k, 0.0), right.get(k, 0.0)) for k in keys)
    return (intersection / union) if union > 0 else 0.0


def family_spread(profile: FormationProfile) -> dict[str, float]:
    """Total surprise per family, for describing what a formation rests on."""
    out = {fam: 0.0 for fam in ALL_FAMILIES}
    for f in profile.features:
        out[f.family] = out.get(f.family, 0.0) + f.surprise
    return {k: round(v, 4) for k, v in out.items() if v > 0}


def logistic(log_odds: float) -> float:
    """Probability from log10 odds, clamped away from a certainty nothing here can support."""
    odds = 10.0 ** max(-12.0, min(12.0, log_odds))
    return odds / (1.0 + odds)
