"""Does this newly scanned account belong to an operation we already know?

THE CAPABILITY THE DETECTOR DID NOT HAVE. `detect` finds formations inside one corpus and forgets
them. So an account scanned today could be a member of an operation catalogued three weeks ago in a
different customer's investigation, and nothing would say so. Every run started from zero, which
means the system could never accumulate knowledge about an adversary, only about a post.

This module closes that. Given an account's feature bag and a registry of known formations, it asks
one question per formation and answers it as a likelihood ratio.

---------------------------------------------------------------------------------------------------
IT IS A LIKELIHOOD RATIO, NOT A SIMILARITY
---------------------------------------------------------------------------------------------------

The tempting implementation is cosine similarity to a cluster centroid, and it is wrong here for the
same reason the attachment weight was wrong: it produces a number that ranks, looks authoritative,
and answers a question nobody asked. "How similar is this account to that group" is not "how much
more likely is this account's behaviour if it belongs to that operation than if it does not".

So the score is

    log10 LR = sum over the formation's discriminative features that this account ALSO holds,
               of the surprise measured when that feature was evidence,
               harmonically discounted within each family, then weighted across families.

Which is deliberately the same arithmetic `significance.score_candidate` uses, so an assignment and
a detection are quoted on one scale and can be compared without a conversion nobody would trust.

---------------------------------------------------------------------------------------------------
WHAT IT REFUSES
---------------------------------------------------------------------------------------------------

* **One family is never enough.** One kind of evidence however many times it fires is one
  observation seen repeatedly, and `MIN_FAMILIES` says so in detection already. An account sharing
  six shingles with a formation and nothing else has shared one thing.
* **It never reads the account's OMI score.** Same rule as detection, same reason: a competent
  operation's accounts each look ordinary, and gating assignment on suspicion would refuse exactly
  the members worth finding. `Composition` describes posture afterwards.
* **It abstains rather than guessing when the formation is thin.** A profile with almost no
  identifying evidence would match half the corpus, and that is a property of the profile rather
  than a fact about the account.
* **A match is a lead.** Nothing here publishes, adds a member, or changes a stored finding. It
  ranks candidates for a person, exactly as the detector's own findings do.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.netdetect.formation import (
    CONCEALED_MEDIAN_SCORE,
    FormationProfile,
    logistic,
)
from app.netdetect.types import (
    ALL_FAMILIES,
    FAMILY_WEIGHT,
    HARD_FAMILIES,
    AccountProfile,
    Feature,
)

#: P(an account scanned in a context where a known formation operates is a member of THAT formation).
#:
#: Stated rather than implied, and deliberately pessimistic. Formations are small and scans are
#: large, so the base rate is low; setting it by feel at something comfortable would move every
#: posterior at once and invisibly. From here, clearing 0.90 needs log10 LR of about 2.95, which is
#: in the same range as `detect.MIN_HARD_EVIDENCE`, so the two layers demand comparable evidence.
ASSIGN_PRIOR = 0.01

#: Posterior at which an assignment is worth putting in front of a person.
ASSIGN_THRESHOLD = 0.90

#: Families that must EACH carry real weight before an assignment is confident. One family is one
#: kind of evidence, however many features fire inside it.
MIN_FAMILIES = 2

#: A family contributing less than this is a rounding error rather than a second kind of evidence.
#: Matches `significance.MIN_FAMILY_CONTRIBUTION` so the two layers agree on what counts.
MIN_FAMILY_CONTRIBUTION = 2.0

#: Below this much total identifying evidence a formation cannot be matched against at all: it would
#: accept too much. Reported as an abstention, never as "no match".
MIN_PROFILE_EVIDENCE = 4.0

#: Weighted evidence that must come from the families where innocent sharing is implausible
#: (`HARD_FAMILIES`: how the accounts were MADE, and which outside targets they converge on).
#:
#: MEASURED, and it closes the one false positive this module had. A true member scored against its
#: own formation carried 17.8 of hard evidence across five families. The same member scored against
#: an UNRELATED operation carried 0.0: its whole match was text and timing, the two families
#: `FAMILY_WEIGHT` already prices lowest because a shared topic and a shared working rhythm are what
#: any two automated accounts have in common. Without this floor that account would have been named
#: as a member of an operation it has nothing to do with.
#:
#: The value matches `detect.MIN_HARD_EVIDENCE` deliberately: naming somebody as part of a specific
#: named operation is at least as strong a claim as reporting the operation, so it should not ask
#: for less.
MIN_HARD_EVIDENCE = 3.0

#: Ceiling on the accumulated log10 LR. Several estimates multiplied do not make a fact, and
#: `detector/probability.MAX_LOG10_LR` prices the same restraint for the cohort detector.
MAX_LOG10_LR = 4.0


@dataclass(slots=True)
class MatchedFeature:
    family: str
    kind: str
    value: str
    surprise: float
    sentence: str


@dataclass(slots=True)
class Assignment:
    """One account weighed against one formation."""

    formation_key: str
    #: Capped at MAX_LOG10_LR. This is what the posterior is built from, because the cap expresses
    #: how much certainty this evidence can support.
    log_lr: float = 0.0
    #: UNCAPPED, and used only to order formations against each other. The cap is a statement about
    #: what may be CLAIMED; applying it to the ranking too would collapse every strong match to one
    #: value and make "which formation does this account belong to" unanswerable, which is the
    #: question this module exists for.
    raw_log_lr: float = 0.0
    posterior: float = 0.0
    by_family: dict[str, float] = field(default_factory=dict)
    matched: list[MatchedFeature] = field(default_factory=list)
    #: Set when no verdict could be reached. NEVER read an absent assignment as "not a member".
    abstained: str | None = None
    #: Why this fell short, when it was tested and did not clear the bar.
    refused: str | None = None

    @property
    def assigned(self) -> bool:
        return self.abstained is None and self.refused is None

    @property
    def families(self) -> int:
        return sum(1 for v in self.by_family.values() if v >= MIN_FAMILY_CONTRIBUTION)

    @property
    def hard_evidence(self) -> float:
        return sum(v * FAMILY_WEIGHT.get(k, 0.5)
                   for k, v in self.by_family.items() if k in HARD_FAMILIES)


def _harmonic(values: list[float]) -> float:
    """Sorted descending, weighted 1, 1/2, 1/3, ...

    The same discount `significance._harmonic_sum` applies, and for the same reason: two shingles
    from one copy-pasted post are one observation seen twice, and summing them plainly is how a
    detector talks itself into certainty.
    """
    return sum(v / (i + 1) for i, v in enumerate(sorted(values, reverse=True)))


def score_against(account: AccountProfile, profile: FormationProfile,
                  *, formation_key: str = "") -> Assignment:
    """How much more likely this account's behaviour is if it belongs to this formation.

    Reads only what the account and the formation SHARE. Features the account holds that the
    formation does not are neither credited nor penalised: they are things this operation has never
    been seen doing, which is not evidence either way about membership.
    """
    out = Assignment(formation_key=formation_key)

    total_available = sum(f.surprise for f in profile.features)
    if total_available < MIN_PROFILE_EVIDENCE:
        out.abstained = (
            f"this formation carries only {total_available:.1f} of identifying evidence, below the "
            f"{MIN_PROFILE_EVIDENCE:.1f} needed to test an account against it. A thinner profile "
            f"would match ordinary accounts."
        )
        return out

    held: set[str] = {f"{f.kind}:{f.value}" for f in account.features}
    per_family: dict[str, list[float]] = {fam: [] for fam in ALL_FAMILIES}

    for feature in profile.features:
        if feature.token() not in held:
            continue
        per_family.setdefault(feature.family, []).append(feature.surprise)
        out.matched.append(MatchedFeature(
            family=feature.family,
            kind=feature.kind,
            value=feature.value,
            surprise=round(feature.surprise, 4),
            sentence=_sentence(feature.as_feature(), feature.prevalence),
        ))

    out.by_family = {fam: round(_harmonic(vals), 6)
                     for fam, vals in per_family.items() if vals}
    weighted = sum(v * FAMILY_WEIGHT.get(k, 0.5) for k, v in out.by_family.items())
    out.raw_log_lr = round(weighted, 6)
    out.log_lr = round(min(MAX_LOG10_LR, weighted), 6)

    prior_odds = ASSIGN_PRIOR / (1.0 - ASSIGN_PRIOR)
    out.posterior = round(logistic(math.log10(prior_odds) + out.log_lr), 6)
    out.matched.sort(key=lambda m: -m.surprise)

    if not out.matched:
        out.refused = "shares none of the behaviours that identify this formation"
    elif out.families < MIN_FAMILIES:
        out.refused = (
            f"shares only {out.families} kind of evidence with this formation; membership needs "
            f"{MIN_FAMILIES} independent kinds, and one family firing repeatedly is one observation"
        )
    elif out.hard_evidence < MIN_HARD_EVIDENCE:
        # The match rests on what any two automated accounts share. See MIN_HARD_EVIDENCE: this is
        # the rule that stops a member of one operation being named as a member of another.
        out.refused = (
            f"shares {out.hard_evidence:.1f} of evidence in the operator's own acts (how the "
            f"accounts were made, which outside targets they converge on), below the "
            f"{MIN_HARD_EVIDENCE:.1f} needed. A match on topic and rhythm alone is what any two "
            f"automated accounts have in common, and does not place this one in THIS formation"
        )
    elif out.posterior < ASSIGN_THRESHOLD:
        out.refused = (
            f"posterior {out.posterior:.2f} is below the {ASSIGN_THRESHOLD:.2f} needed to name "
            f"somebody as part of an operation"
        )
    return out


def rank(account: AccountProfile,
         profiles: dict[str, FormationProfile]) -> list[Assignment]:
    """Weigh one account against every known formation, best first.

    Returns EVERY result, including the refusals and abstentions. "We looked at forty formations and
    refused all of them" is a more trustworthy statement than an empty list, and a near miss is what
    an operator calibrating this needs to see.
    """
    out = [score_against(account, profile, formation_key=key)
           for key, profile in sorted(profiles.items())]
    # Ordered on the UNCAPPED value: several formations can sit at the cap, and the cap is about
    # what may be claimed rather than about which formation fits best.
    out.sort(key=lambda a: (-a.raw_log_lr, a.formation_key))
    return out


#: Accounts swept in one request. A comment section is bounded by the scan cap, and the work is a
#: set intersection per (account, formation) pair, but an unbounded product inside an admin request
#: is how a cheap read becomes a slow one on a page somebody is waiting for.
MAX_SWEEP_ACCOUNTS = 400


@dataclass(slots=True)
class Placement:
    """One account, and the known formation it was placed in."""

    external_id: str
    handle: str
    assignment: Assignment
    #: The account's own OMI score, carried for CHARACTERISATION and never fed into the placement.
    #: `score_against` reads behaviour only, which
    #: `test_the_score_never_reads_an_accounts_own_suspicion_score` pins for the detector and which
    #: holds here for the same reason: an operation of accounts that each look ordinary is exactly
    #: what the old 70+ cohort filter was blind to by construction.
    omi_score: float | None = None

    @property
    def concealed(self) -> bool:
        """Placed in a known operation while reading as an ordinary account on its own.

        THE MOST VALUABLE ROW IN A SWEEP, and the reading is inverted from the obvious one. An
        account the per-account engine already flags is one an analyst could have found without
        this. An account that would pass an individual review and nonetheless matches an operation's
        recorded behaviour is the finding nothing else in the product can produce.

        None is not low: an unscored account has not been examined, and reading that as concealed
        would manufacture the system's most alarming label out of missing data.
        """
        return self.omi_score is not None and self.omi_score <= CONCEALED_MEDIAN_SCORE


@dataclass(slots=True)
class Sweep:
    """Every account in a comment section, weighed against every known formation.

    THE CAPABILITY THE ROUTE COULD NOT OFFER. `score_against` answers "does THIS account belong to
    THAT operation", which requires an operator to already suspect both. The question an analyst
    actually has when a comment section lands is the other way round: is anybody here part of
    something we have already catalogued?
    """

    placed: list[Placement] = field(default_factory=list)
    #: Accounts weighed and placed in nothing. A COUNT, never a list of names: publishing "these
    #: 140 accounts matched no known operation" invites reading it as a clean bill of health, and
    #: it is not one. See `NOT_A_CLEARANCE`.
    unplaced: int = 0
    #: Accounts that could not be weighed at all (no formation catalogued, nothing to compare).
    skipped: int = 0
    formations_considered: int = 0
    truncated: bool = False

    @property
    def looked(self) -> bool:
        return self.formations_considered > 0


#: Why an empty sweep is not an all-clear, stated with the result rather than left in a docstring.
NOT_A_CLEARANCE = (
    "An account placed in no known formation is an account this deployment has never catalogued "
    "doing this before. That is not a finding of innocence: an operation nobody has recorded yet is "
    "exactly what the detector exists to find, and a disciplined one emits nothing to place. Read "
    "an empty sweep as 'no match in the catalogue', never as 'these accounts are unrelated'."
)


def sweep(accounts: Iterable[AccountProfile],
          profiles: dict[str, FormationProfile]) -> Sweep:
    """Weigh a whole comment section against the catalogue.

    Bounded, and it reports its own truncation rather than quietly answering about a subset, which
    would be a claim about the accounts it never looked at.
    """
    out = Sweep(formations_considered=len(profiles))
    if not profiles:
        out.skipped = sum(1 for _ in accounts)
        return out

    for i, account in enumerate(accounts):
        if i >= MAX_SWEEP_ACCOUNTS:
            out.truncated = True
            break
        placement = best(account, profiles)
        if placement is None:
            out.unplaced += 1
            continue
        out.placed.append(Placement(
            external_id=account.external_id,
            handle=account.handle or account.external_id,
            assignment=placement,
            omi_score=account.score,
        ))

    # Strongest first: an operator reads the top of this list and stops.
    out.placed.sort(key=lambda p: (-p.assignment.raw_log_lr, p.external_id))
    return out


def best(account: AccountProfile,
         profiles: dict[str, FormationProfile]) -> Assignment | None:
    """The single formation this account belongs to, or None.

    NONE MEANS "NO KNOWN FORMATION", NEVER "NOT COORDINATED". An operation nobody has catalogued yet
    is exactly the thing `detect` exists to find, and reading a null here as innocence would invert
    the system's purpose.
    """
    for assignment in rank(account, profiles):
        if assignment.assigned:
            return assignment
    return None


def _sentence(feature: Feature, prevalence: float) -> str:
    """One checkable line per matched behaviour. Every published claim needs one."""
    where = {
        "shingle": "uses a phrase this formation uses",
        "bio_shingle": "carries a profile phrase this formation carries",
        "gap_class": "posts on this formation's interval rhythm",
        "active_hours": "is active in this formation's hours",
        "quiet_hours": "shares this formation's daily quiet period",
        "target_post": "engaged a post this formation targets",
        "reply_to": "replied to an account this formation replies to",
        "repost_of": "amplified a post this formation amplifies",
        "client": "publishes with this formation's tool",
        "link_domain": "links to this formation's domain",
        "creation_week": "was created in this formation's provisioning week",
        "handle_template": "shares this formation's handle template",
        "topic": "speaks on this formation's topic",
    }.get(feature.kind, feature.kind.replace("_", " "))
    return f"{where} ({feature.value[:60]}), seen in {prevalence:.1%} of the measured corpus"
