"""The probability model, pinned case by case.

Every worked example in ``probability.py``'s docstring and in CLAUDE.md is a test here. That is the
point of the file: the likelihood ratios are reasoned rather than fitted, so the thing that keeps
them honest is a set of documented cases that must keep coming out the same way. Change a ratio and
whichever refusal it breaks will say so.

The refusals matter more than the detections. A detector that misses an operation is a weaker
product; a detector that names an innocent person is a harm.
"""

from __future__ import annotations

import math

from app.campaigns.detector import probability as P


# ==================================================================================================
# The prior
# ==================================================================================================
def test_the_prior_is_stated_and_low():
    """Most pairs of accounts, even inside a cohort pre-filtered to 70+, are not coordinated with
    each other. If this drifts upward every finding gets easier and nothing else changes."""
    assert 0.01 <= P.DEFAULT_PRIOR <= 0.10
    assert P.prior_odds() < 0.05


def test_the_evidence_needed_to_convict_is_substantial():
    """From the stated prior, clearing 0.95 takes roughly 550x evidence. That number IS the
    discipline: it is what makes a single weak signal structurally unable to accuse anyone."""
    required = P.required_log10_lr()
    assert 2.5 <= required <= 3.0
    assert 10 ** required >= 300


# ==================================================================================================
# No single family convicts. This is the property that replaced the old hardcoded gate.
# ==================================================================================================
SINGLE_FAMILY_CASES = [
    ("text via verbatim_echo", {"text": P.log10_lr("verbatim_echo")}),
    ("text via bio_echo", {"text": P.log10_lr("bio_echo")}),
    ("network via co_target", {"network": P.log10_lr("co_target")}),
    ("infrastructure", {"infrastructure": P.log10_lr("client_signature")}),
    ("identity via handle_template", {"identity": P.log10_lr("handle_template")}),
    # The measured-null signals at absurd significance, to prove the per-method ceiling holds.
    ("identity via provisioning at p=1e-9", {"identity": P.log10_lr("provisioning_window", 1e-9)}),
    ("timing via burst at p=1e-4", {"timing": P.log10_lr("burst_lockstep", 1e-4)}),
    ("timing via burst at p=1e-12", {"timing": P.log10_lr("burst_lockstep", 1e-12)}),
]


def test_no_single_family_can_convict_at_any_strength():
    leaks = [
        name for name, families in SINGLE_FAMILY_CASES
        if P.posterior(families) >= P.DECISION_THRESHOLD
    ]
    assert leaks == [], f"a single family cleared the bar: {leaks}"


def test_the_measured_null_signals_are_capped_for_stated_reasons():
    """`burst_lockstep` cannot see an external referral spike (a post linked from a Discord makes
    real strangers arrive together) and `provisioning_window`'s empirical CDF is coarse. The caps
    are where those unmodelled confounds are priced in, so they must actually bite."""
    assert P.log10_lr("burst_lockstep", 1e-12) == P.MAX_LOG10_PER_METHOD["burst_lockstep"]
    assert P.log10_lr("provisioning_window", 1e-12) == P.MAX_LOG10_PER_METHOD["provisioning_window"]


def test_a_supporting_signal_barely_moves_anything():
    """`handle_template` exists to corroborate. On its own it should leave the posterior low, not
    merely under the bar."""
    assert P.posterior({"identity": P.log10_lr("handle_template")}) < 0.30


# ==================================================================================================
# Two independent families are enough
# ==================================================================================================
def test_any_two_independent_families_convict():
    families = ["text", "timing", "network", "infrastructure"]
    strengths = {
        "text": P.log10_lr("verbatim_echo"),
        "timing": P.log10_lr("burst_lockstep", 1e-4),
        "network": P.log10_lr("co_target"),
        "infrastructure": P.log10_lr("client_signature"),
    }
    for i in range(len(families)):
        for j in range(i + 1, len(families)):
            a, b = families[i], families[j]
            p = P.posterior({a: strengths[a], b: strengths[b]})
            assert p >= P.DECISION_THRESHOLD, f"{a} + {b} did not convict ({p:.4f})"


def test_a_strong_family_plus_a_weak_one_convicts():
    p = P.posterior({
        "text": P.log10_lr("verbatim_echo"),
        "identity": P.log10_lr("handle_template"),
    })
    assert p >= P.DECISION_THRESHOLD


# ==================================================================================================
# Nothing claims certainty
# ==================================================================================================
def test_the_posterior_is_capped_below_one():
    """Five families all firing at maximum still does not produce certainty, because every ratio in
    the model is an estimate and multiplying five estimates does not make a fact."""
    everything = {fam: 9.0 for fam in
                  ("text", "timing", "network", "infrastructure", "identity")}
    p = P.posterior(everything)
    assert p < 0.999
    assert p == P.posterior({fam: 99.0 for fam in everything}), "the cap must be a hard ceiling"


def test_no_evidence_returns_the_prior():
    assert abs(P.posterior({}) - P.DEFAULT_PRIOR) < 1e-9


def test_negative_or_junk_contributions_cannot_lower_the_prior():
    """Evidence is one-directional here: a signal that did not fire says nothing, and must not be
    allowed to argue for innocence it never established."""
    assert P.posterior({"text": -5.0}) == P.posterior({})


# ==================================================================================================
# Accumulation across scans
# ==================================================================================================
def test_a_second_sighting_carries_one_family_over_the_bar():
    """The single most valuable property of tracking operations globally: one post is not enough,
    two unrelated posts are."""
    base = P.log10_lr("verbatim_echo")
    assert P.posterior({"text": base}) < P.DECISION_THRESHOLD
    assert P.posterior({"text": base}, extra_log10=base * 0.5) >= P.DECISION_THRESHOLD


def test_carried_evidence_is_capped_too():
    assert P.posterior({"text": 0.0}, extra_log10=999.0) < 0.999


# ==================================================================================================
# The derivation is legible
# ==================================================================================================
def test_the_derivation_names_the_prior_and_every_family():
    """A posterior with no visible derivation is exactly as unaccountable as the score it
    replaced."""
    text = P.explain({
        "text": P.log10_lr("verbatim_echo"),
        "infrastructure": P.log10_lr("client_signature"),
    })
    assert "prior" in text
    assert "text" in text and "infrastructure" in text
    assert "posterior" in text


def test_every_static_likelihood_carries_a_reason():
    """Each ratio is a judgement call, so each one has to say what the judgement was. A bare number
    here would be unreviewable."""
    for method, likelihood in P.STATIC_LIKELIHOODS.items():
        assert likelihood.note.strip(), method
        assert 0 < likelihood.p_given_independent < likelihood.p_given_coordinated <= 1.0, method


def test_the_lr_version_is_stamped():
    assert P.LR_VERSION


def test_an_unknown_method_is_inert():
    """A signal added without a likelihood ratio must contribute nothing rather than a default that
    quietly convicts."""
    assert P.likelihood_ratio("something_new") == 1.0
    assert P.log10_lr("something_new") == 0.0


def test_a_measured_null_signal_without_its_p_value_is_inert():
    """Its likelihood ratio IS its p-value's reciprocal, so an edge that lost the p-value must not
    silently fall back to something confident."""
    assert P.likelihood_ratio("burst_lockstep", None) == 1.0
    assert P.likelihood_ratio("provisioning_window", None) == 1.0


# ==================================================================================================
# The calibration gate
# ==================================================================================================
def test_the_detector_stays_silent_on_every_clean_benchmark_scenario():
    """The single number that decides whether this is shippable.

    Nine of the committed scenarios are labelled as having no coordination in them. A detector that
    cannot stay quiet on those is not usable at any recall, because the cost of a false finding here
    is a named real person being called part of an operation.
    """
    from app.evaluation.coordination_probability import evaluate

    report = evaluate()
    assert report.scenarios > 0, "the benchmark scenarios are missing from this checkout"
    assert report.clean_pass_rate == 1.0, (
        "the detector reported coordination on data labelled as having none:\n  "
        + "\n  ".join(report.notes)
    )


def test_no_benchmark_pair_is_called_coordinated_at_the_decision_threshold():
    """These scenarios carry no comment timestamps, no posting clients and no engagement targets,
    so four of the seven signals cannot fire and the rest have little to work with. Nothing should
    clear 0.95 on that. If something does, either a likelihood ratio drifted upward or a signal
    started reading evidence that is not there."""
    from app.evaluation.coordination_probability import evaluate

    called = [o for o in evaluate().outcomes if o.predicted >= P.DECISION_THRESHOLD]
    assert called == [], f"{len(called)} pair(s) cleared the bar on evidence-poor fixtures"
