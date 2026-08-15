"""The probability model: how evidence becomes P(coordinated).

Everything else in this package produces evidence. This module is the only place that turns it into
a number, and that number is a real posterior probability rather than a score somebody normalised to
0..1. The difference matters for one reason: the product's rule is "only cluster accounts that have
a high probability of being coordinated", and you cannot implement that against a quantity that is
not a probability.

---------------------------------------------------------------------------------------------------
THE SHAPE
---------------------------------------------------------------------------------------------------

Odds form, so evidence adds instead of interacting:

    posterior_odds = prior_odds * PRODUCT over families of LR_family

where ``LR = P(evidence | coordinated) / P(evidence | independent)``.

Two design facts follow immediately, and both were previously enforced by hand-written rules that
can now be deleted:

1. **The family structure IS the conditional-independence assumption.** Likelihood ratios multiply
   only when the evidence is conditionally independent given the hypothesis. `verbatim_echo` and
   `bio_echo` both say "these accounts emitted the same string", so multiplying them would count one
   observation twice. Taking the strongest within a family and multiplying across families is not a
   heuristic any more; it is what the arithmetic requires.

2. **Corroboration stops being a rule and becomes a consequence.** With the honest likelihood ratios
   below, no single supporting family can lift the prior past the bar, and even the strongest single
   family lands short of it. The old ``SUPPORTING_CEILING`` / "discriminative AND >= 2 families"
   gate is not removed because it was wrong, it is removed because the numbers now do its job. See
   ``tests/test_coordination_probability.py``, which pins every one of those refusals.

---------------------------------------------------------------------------------------------------
WHY THE NUMBERS ARE CONSERVATIVE, AND WHY THAT IS NOT FALSE MODESTY
---------------------------------------------------------------------------------------------------

The likelihood ratios here are reasoned, not fitted: the labelled corpus in this repo is ~200
accounts across 16 scenarios, which can falsify a badly wrong ratio but cannot fit seven of them.
Every value is therefore chosen at the pessimistic end of its plausible range, and the total is
capped, because these findings name real people and the cost of overstating a ratio is an
accusation rather than a missed detection.

``LR_VERSION`` is stamped on every finding so a later recalibration can tell what produced what.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ==================================================================================================
# The prior
# ==================================================================================================
# P(two accounts drawn from one investigation's 70+ cohort are in the same operation).
#
#     P(an investigation contains an operation at all)  ~ 0.35
#     operation size when present                       ~ 5 of a ~15-account cohort
#     P(random pair coordinated) = 0.35 * C(5,2)/C(15,2) = 0.35 * 10/105 = 0.033
#
# Grounded in the base rates recorded in CLAUDE.md's research pass: 9-15% of active accounts are
# automated. Charged political threads measure 43-45%, but the tools producing that figure run
# 41-76% false-positive rates on the same measurements, so the charged number is not usable as a
# prior and deliberately is not used as one.
#
# This is the single most consequential constant in the detector. It is what makes weak evidence
# structurally unable to accuse anyone: from these odds a pair needs LR >= 551 to clear 0.95.
DEFAULT_PRIOR = 0.033

#: A finding is reported only at or above this posterior. Applied PER ACCOUNT against the group it
#: would join, never to the group as a whole, so no member is ever carried in by its neighbours'
#: evidence.
DECISION_THRESHOLD = 0.95

#: Ceiling on total accumulated log10 likelihood ratio. Caps the reportable posterior at ~0.997.
#: Nothing here may claim certainty, because every ratio below is an estimate and multiplying five
#: estimates does not produce a fact.
MAX_LOG10_LR = 4.0

#: Bumped whenever any ratio, the prior, or the threshold moves.
LR_VERSION = "lr-v1"


# ==================================================================================================
# Per-signal likelihood ratios
# ==================================================================================================
@dataclass(frozen=True)
class Likelihood:
    """One signal's evidential strength.

    ``p_given_coordinated`` is how often a real operation actually leaves this trace, which is well
    under 1 for every signal: plenty of operations never reuse copy verbatim, and plenty post
    through ordinary clients.

    ``p_given_independent`` is how often two unrelated accounts produce it anyway. This is the
    number that decides everything, and it is the number that is hardest to know, so each is set
    pessimistically high.
    """

    method: str
    p_given_coordinated: float
    p_given_independent: float
    note: str

    @property
    def lr(self) -> float:
        if self.p_given_independent <= 0:
            return 10.0 ** MAX_LOG10_LR
        return self.p_given_coordinated / self.p_given_independent

    @property
    def log10_lr(self) -> float:
        return math.log10(max(self.lr, 1e-9))


#: Signals whose null is ESTIMATED here. The two absent from this table (`burst_lockstep`,
#: `provisioning_window`) do not appear because they MEASURE their own denominator: each already
#: computes a p-value that is exactly P(evidence | independent). The null model those signals carry
#: for a different reason turns out to be precisely what Bayes wants underneath, so their ratios are
#: derived from data per observation rather than guessed once here. That is the strongest part of
#: this model and it should not be flattened into a constant for tidiness.
STATIC_LIKELIHOODS: dict[str, Likelihood] = {
    "verbatim_echo": Likelihood(
        method="verbatim_echo",
        p_given_coordinated=0.35,
        p_given_independent=0.002,
        note=(
            "Two unrelated accounts under one post emitting the same normalised 40+ character "
            "string. Set at 1-in-500 rather than something rarer because a single thread is full "
            "of shared context: quotes of the original post, stock phrasings, and the same joke."
        ),
    ),
    "bio_echo": Likelihood(
        method="bio_echo",
        p_given_coordinated=0.15,
        p_given_independent=0.001,
        note=(
            "Rarer than posted text because bios are short and denylisted here, but operations "
            "reuse them less often than they reuse scripts, so the numerator drops too."
        ),
    ),
    "co_target": Likelihood(
        method="co_target",
        p_given_coordinated=0.30,
        p_given_independent=0.002,
        note=(
            "Three or more shared engagement targets, each already filtered to targets under 20% "
            "of the batch touched. The id space is enormous, but people with one interest do "
            "converge, hence 1-in-500 rather than 1-in-10000."
        ),
    ),
    "client_signature": Likelihood(
        method="client_signature",
        p_given_coordinated=0.20,
        p_given_independent=0.0015,
        note=(
            "Both accounts publishing 80%+ through the same non-ubiquitous client. Rarity is a "
            "property of the platform's client ecosystem rather than of this batch, which is what "
            "makes it strong; the numerator is low because most operations use ordinary clients."
        ),
    ),
    "handle_template": Likelihood(
        method="handle_template",
        p_given_coordinated=0.20,
        p_given_independent=0.03,
        note=(
            "Deliberately weak. Handles are also just names, and the auto-append shape is already "
            "refused upstream. This exists to corroborate, and the ratio is set so it can never do "
            "anything else."
        ),
    ),
}

#: For the two measured-null signals: how often a real operation leaves that trace at all. Divided
#: by the observation's own p-value to get its likelihood ratio.
MEASURED_NULL_NUMERATOR: dict[str, float] = {
    "burst_lockstep": 0.30,
    "provisioning_window": 0.25,
}

#: Floor on a measured p-value before it becomes a denominator. Without it a p of 1e-12 would claim
#: a likelihood ratio of 1e11 off a single arrival coincidence, and the Poisson tail is not accurate
#: that far out.
MIN_MEASURED_P = 1e-6

#: Per-method ceiling on log10 LR. Only the measured-null signals need one, and the reason is not
#: tidiness: a p-value answers "how surprising is this under MY null", and each of these two nulls
#: has a real-world confound it cannot see. The cap is where that unmodelled confound is priced in.
#:
#: `burst_lockstep` (2.30, LR 200) — the null is the thread's own arrival rate, so it correctly
#:   refuses a viral post. What it cannot see is an EXTERNAL referral spike: a post linked from a
#:   Discord, a subreddit or a group chat produces a genuine burst of unrelated real people, and
#:   that burst is precisely the deviation the null flags. So co-arrival may corroborate but must
#:   never convict alone.
#: `provisioning_window` (2.00, LR 100) — the null is an empirical CDF over a few hundred creation
#:   dates, which already needs a uniform floor in `stats.window_mass` because it has no resolution
#:   below the spacing of the data. A p-value from a distribution that coarse does not deserve the
#:   same trust as one from thousands of arrival timestamps, and creation-date clustering is the
#:   exact shape (`age_cohort`) this product has produced false positives with before.
MAX_LOG10_PER_METHOD: dict[str, float] = {
    "burst_lockstep": 2.30,
    "provisioning_window": 2.00,
}


def likelihood_ratio(method: str, measured_p: float | None = None) -> float:
    """The likelihood ratio for one observation of one signal.

    ``measured_p`` is the signal's own p-value where it has one, and is ignored otherwise.
    """
    numerator = MEASURED_NULL_NUMERATOR.get(method)
    if numerator is not None:
        if measured_p is None or measured_p <= 0:
            return 1.0
        raw = numerator / max(measured_p, MIN_MEASURED_P)
    else:
        static = STATIC_LIKELIHOODS.get(method)
        if static is None:
            return 1.0
        raw = static.lr
    ceiling = MAX_LOG10_PER_METHOD.get(method)
    if ceiling is not None:
        raw = min(raw, 10.0 ** ceiling)
    return raw


def log10_lr(method: str, measured_p: float | None = None) -> float:
    return math.log10(max(likelihood_ratio(method, measured_p), 1e-9))


# ==================================================================================================
# Combination
# ==================================================================================================
def prior_odds(prior: float = DEFAULT_PRIOR) -> float:
    prior = min(max(prior, 1e-9), 1 - 1e-9)
    return prior / (1.0 - prior)


def combine_log10(
    per_family_log10: dict[str, float],
    *,
    prior: float = DEFAULT_PRIOR,
    extra_log10: float = 0.0,
) -> float:
    """Total log10 posterior odds.

    ``per_family_log10`` must already be reduced to ONE value per family, the strongest observation
    within it. Passing two entries for one family is the double-counting this whole structure exists
    to prevent, so the caller reduces first and this function does not second-guess it.

    ``extra_log10`` carries cross-scan accumulation: seeing the same pair coordinate on a different
    post is genuinely new evidence, and the tracking layer supplies it already discounted.
    """
    evidence = sum(max(0.0, v) for v in per_family_log10.values()) + max(0.0, extra_log10)
    evidence = min(evidence, MAX_LOG10_LR)
    return math.log10(prior_odds(prior)) + evidence


def posterior_from_log10_odds(value: float) -> float:
    """Odds to probability, overflow-safe at both ends."""
    if value > 12:
        return 1.0
    if value < -12:
        return 0.0
    odds = 10.0 ** value
    return odds / (1.0 + odds)


def posterior(
    per_family_log10: dict[str, float],
    *,
    prior: float = DEFAULT_PRIOR,
    extra_log10: float = 0.0,
) -> float:
    """P(coordinated | evidence), the number the whole product turns on."""
    return posterior_from_log10_odds(
        combine_log10(per_family_log10, prior=prior, extra_log10=extra_log10)
    )


def required_log10_lr(
    *, prior: float = DEFAULT_PRIOR, threshold: float = DECISION_THRESHOLD,
) -> float:
    """How much evidence is needed to clear the bar from this prior.

    Exposed rather than hardcoded because it is the sentence that explains the detector to an
    operator: at the default prior and a 0.95 bar this is 2.74, which no single family reaches.
    """
    threshold = min(max(threshold, 1e-9), 1 - 1e-9)
    return math.log10(threshold / (1.0 - threshold)) - math.log10(prior_odds(prior))


def explain(per_family_log10: dict[str, float], *, prior: float = DEFAULT_PRIOR) -> str:
    """One line an operator can check, naming the prior and each family's contribution.

    A posterior with no visible derivation is exactly as unaccountable as the score it replaced.
    """
    parts = ", ".join(
        f"{fam} +{v:.2f}" for fam, v in sorted(per_family_log10.items(), key=lambda kv: -kv[1])
        if v > 0
    ) or "no evidence"
    total = combine_log10(per_family_log10, prior=prior)
    return (
        f"prior {prior:.3f} (log odds {math.log10(prior_odds(prior)):.2f}), {parts}, "
        f"total log odds {total:.2f}, posterior {posterior_from_log10_odds(total):.3f}"
    )
