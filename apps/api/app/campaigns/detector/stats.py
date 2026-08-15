"""The two null models this detector is allowed to use, and nothing else.

Deliberately stdlib ``math`` only. scipy would give these in one line each and is installed here
as a transitive dependency of scikit-learn, but it is **not declared** in
``apps/api/pyproject.toml``, so relying on it means a future dependency change can remove the
statistical core of a detector that names real people, silently. Both functions below are a dozen
lines. That is a better trade than the import.

WHY THERE ARE NULLS AT ALL, given the cohort is pre-filtered to 70+:

Filtering to 70+ removes the *cohort's* internal background. It does not remove the batch. Every
lower-scoring account is still in the payload and every comment under the post is still available,
so a signal that needs a null gets one from material the filter never touched. Only cohort members
are ever named. Two signals need this and are honest about it:

* ``burst_lockstep`` without a null is the single worst false-positive generator available. On a
  viral post two hundred comments land per minute and any four accounts you pick will share a
  minute. The rate has to come from the thread itself.
* ``provisioning_window`` without a null fires on platform growth. Signups are not uniform over
  time: migration waves and viral growth periods create real cohorts of unrelated people. The
  empirical distribution of the whole batch absorbs that automatically.

A future session will be tempted to replace either with a fixed window because the arithmetic
looks like overkill. It is not overkill; it is the entire difference between a finding and a
libel.
"""

from __future__ import annotations

import math

#: Returned when the input cannot support a test at all. Callers must treat this as "no evidence",
#: never as "not significant" - the two are different and conflating them is how a detector starts
#: reporting confidence it never earned.
UNTESTABLE = None


def poisson_sf(k: int, mu: float) -> float:
    """``P(X >= k)`` for ``X ~ Poisson(mu)``, summed directly.

    ``k`` is small here by construction (a burst of three to a few dozen accounts), so the naive
    forward sum is both exact enough and cheap. No continued fractions needed.
    """
    if k <= 0:
        return 1.0
    if mu <= 0.0:
        return 0.0
    # P(X < k) = sum_{i=0}^{k-1} e^-mu mu^i / i!, accumulated with a running term to avoid
    # overflowing mu**i for large mu.
    try:
        term = math.exp(-mu)
    except OverflowError:  # pragma: no cover - mu that large cannot reach here
        return 1.0
    total = term
    for i in range(1, k):
        term *= mu / i
        total += term
        if total >= 1.0:
            return 0.0
    return max(0.0, min(1.0, 1.0 - total))


def _log_binom(n: int, k: int) -> float:
    if k < 0 or k > n:
        return -math.inf
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1))


def scan_statistic_p(n: int, k: int, window_mass: float) -> float | None:
    """Probability that some window holds at least ``k`` of ``n`` independent points.

    ``window_mass`` is the probability mass the window covers under the null distribution, so a
    non-uniform background is handled by whatever produced that number (see ``empirical_mass``).

    Uses the standard first-order approximation ``n * C(n-1, k-1) * p^(k-1)``, computed in log
    space, and clamps to 1.0. It over-estimates the tail slightly, which is the direction we want:
    it makes the test harder to pass, not easier.

    Returns ``None`` when the input cannot support a test (too few points, degenerate mass).
    """
    if n < k or k < 2:
        return UNTESTABLE
    if window_mass <= 0.0:
        return UNTESTABLE
    if window_mass >= 1.0:
        # The window covers the whole distribution, so "clustered" is meaningless.
        return 1.0
    log_p = math.log(n) + _log_binom(n - 1, k - 1) + (k - 1) * math.log(window_mass)
    if log_p >= 0.0:
        return 1.0
    return math.exp(log_p)


def empirical_mass(sorted_values: list[float], lo: float, hi: float) -> float:
    """Share of ``sorted_values`` lying in ``[lo, hi]``.

    This is the empirical CDF difference that makes ``scan_statistic_p`` non-parametric. Feeding
    it the whole batch is what lets a genuine platform signup spike absorb itself: if half the
    batch was created that week, the window mass is 0.5 and no k makes it significant.
    """
    if not sorted_values or hi < lo:
        return 0.0
    import bisect

    left = bisect.bisect_left(sorted_values, lo)
    right = bisect.bisect_right(sorted_values, hi)
    return max(0, right - left) / len(sorted_values)


def window_mass(
    sorted_values: list[float],
    lo: float,
    hi: float,
    *,
    bandwidth: float,
) -> float | None:
    """Probability that one draw from the background lands in ``[lo, hi]``.

    Two things this does that a raw ``empirical_mass`` cannot, and both are the difference between
    a working test and a broken one:

    * **It excludes the candidate window from its own background.** A cluster counted in the
      distribution it is being tested against inflates that distribution and hides itself. Exactly
      the flaw ``local_rate`` documents for the timing signal; it is the same mistake in a
      different coordinate.
    * **It has resolution below the spacing of the data.** With 300 creation dates spread over ten
      years the points sit twelve days apart, so the empirical count in a 200-second window is zero
      for every window that does not contain the cluster, and zero mass makes the test untestable
      rather than significant. So the mass is estimated as a local density (from a neighbourhood
      wide enough to contain points) and floored at the uniform-over-the-whole-span rate, taking
      whichever is LARGER. Larger mass means a harder test, which is the safe direction.

    Returns ``None`` when there is no usable background at all.
    """
    if not sorted_values or hi < lo or bandwidth <= 0:
        return UNTESTABLE
    n = len(sorted_values)
    span = sorted_values[-1] - sorted_values[0]
    width = hi - lo
    if n < 3 or span <= 0 or width <= 0:
        return UNTESTABLE

    # Uniform-over-the-whole-span floor.
    uniform = width / span

    # Local density, excluding the candidate window itself.
    import bisect

    centre = (lo + hi) / 2.0
    n_lo, n_hi = centre - bandwidth, centre + bandwidth
    left = bisect.bisect_left(sorted_values, n_lo)
    right = bisect.bisect_right(sorted_values, n_hi)
    count = right - left
    ex_left = bisect.bisect_left(sorted_values, lo)
    ex_right = bisect.bisect_right(sorted_values, hi)
    count -= max(0, ex_right - ex_left)
    usable = (2.0 * bandwidth) - width
    local = 0.0
    if count > 0 and usable > 0:
        local = (count / usable) * width / n

    return min(1.0, max(uniform, local))


def local_rate(
    sorted_times: list[float],
    centre: float,
    half_span: float,
    *,
    exclude: tuple[float, float] | None = None,
) -> float | None:
    """Events per second near ``centre``, measured from the full stream.

    ``exclude`` removes a range from both the count and the span, and passing the candidate burst
    there is not optional: a burst included in its own background inflates the rate it is being
    tested against and hides itself. Measured on a quiet thread, the same four-account burst went
    from p=1.4e-4 (missed) to p=2.3e-7 (caught) once it stopped being its own null.

    ``None`` when the neighbourhood is too sparse to estimate a rate. That must be treated as
    untestable, never as a rate of zero: zero would make every co-occurrence infinitely
    significant, which is exactly backwards. The caller is expected to fall back to the whole
    thread's rate, which is always defined.
    """
    if not sorted_times or half_span <= 0:
        return UNTESTABLE
    import bisect

    lo, hi = centre - half_span, centre + half_span
    left = bisect.bisect_left(sorted_times, lo)
    right = bisect.bisect_right(sorted_times, hi)
    count = right - left
    span = 2.0 * half_span

    if exclude is not None:
        ex_lo, ex_hi = exclude
        ex_lo, ex_hi = max(ex_lo, lo), min(ex_hi, hi)
        if ex_hi > ex_lo:
            e_left = bisect.bisect_left(sorted_times, ex_lo)
            e_right = bisect.bisect_right(sorted_times, ex_hi)
            count -= max(0, e_right - e_left)
            span -= (ex_hi - ex_lo)

    if count < 3 or span <= 0:
        return UNTESTABLE
    return count / span


def global_rate(sorted_times: list[float]) -> float | None:
    """Events per second across the whole stream. Always defined for 3+ events, so it is the
    fallback when a local neighbourhood is too sparse to measure."""
    if len(sorted_times) < 3:
        return UNTESTABLE
    span = sorted_times[-1] - sorted_times[0]
    if span <= 0:
        return UNTESTABLE
    return len(sorted_times) / span


def bonferroni(p: float, tests: int) -> float:
    """Family-wise correction. Every signal here tests many windows or many pairs, and an
    uncorrected p-value over a few thousand comparisons is not a p-value."""
    if tests <= 1:
        return p
    return min(1.0, p * tests)
