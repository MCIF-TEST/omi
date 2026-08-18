"""The shape of a batched run, and the counters that used to lie about it.

Every progress bug this year was one of `done` / `landed` / `model_backed` being read as another.
Here they are all derived from one list of outcomes, so the tests below are about the DERIVATION:
if these hold, no reader can be told something the batches do not say.
"""

from __future__ import annotations

from app.reasoning.batch_plan import (
    BATCH_SIZE,
    RunPlan,
    plan_batches,
    plan_run,
)


# ==================================================================================================
# The split: a fixed SIZE, remainder last
# ==================================================================================================
def test_the_split_is_a_fixed_size_not_a_fixed_count():
    """A SIZE bounds the request; a COUNT does not. Dividing into a fixed number of batches made the
    size grow with the selection, so a 197-account scan became four calls of ~50 and every one came
    back empty. More accounts must mean more requests, never a bigger request."""
    assert [e - s for s, e in plan_batches(100)] == [25, 25, 25, 25]
    assert [e - s for s, e in plan_batches(200)] == [25] * 8
    assert [e - s for s, e in plan_batches(197)] == [25] * 7 + [22]
    for n in (1, 25, 26, 92, 150, 500):
        sizes = [e - s for s, e in plan_batches(n)]
        assert sum(sizes) == n, n
        assert max(sizes, default=0) <= BATCH_SIZE, n


def test_a_remainder_gets_its_own_batch():
    """92 is 25/25/25/17. The short final request is not worth resizing every other batch to avoid."""
    assert [e - s for s, e in plan_batches(92)] == [25, 25, 25, 17]


def test_the_slices_cover_the_selection_in_order_with_no_gap_or_overlap():
    """An account dropped between two slices is an account the customer paid for and never sees."""
    slices = plan_batches(197)
    assert slices[0][0] == 0
    assert slices[-1][1] == 197
    for (_, prev_end), (next_start, _) in zip(slices, slices[1:]):
        assert prev_end == next_start


def test_a_selection_that_fits_in_one_request_is_one_batch():
    assert len(plan_batches(25)) == 1
    assert len(plan_batches(1)) == 1
    assert plan_batches(0) == []


# ==================================================================================================
# The derived counters
# ==================================================================================================
def _run(*outcomes: tuple[str, int]) -> RunPlan:
    """Build a run whose batches already carry the given (state, accounts) outcomes."""
    plan = plan_run("r1", 25 * len(outcomes))
    for b, (state, accounts) in zip(plan.batches, outcomes):
        b.state, b.accounts = state, accounts
    return plan


def test_attempted_and_landed_are_different_numbers_and_both_are_right():
    """The live contradiction: a strip reading "3 of 4 done" beside "25 accounts scored". Three
    batches HAD been tried and one HAD produced accounts; the two numbers were both true of
    different things and the pair of them was a lie."""
    plan = _run(("done", 25), ("failed", 0), ("failed", 0), ("running", 0))
    assert plan.attempted == 3
    assert plan.landed == 1
    assert plan.accounts_scored == 25
    assert plan.failed == 2


def test_a_batch_that_returned_an_object_carrying_no_accounts_is_a_FAILURE():
    """A floored batch is not None: it returns a complete deterministic Floor with zero accounts.
    Counting it as landed made `landed` restate the lie `done` already told, and disabled the one
    notice whose whole job is to say 'finished, but N batches yielded nothing'."""
    plan = _run(("done", 25), ("done", 0), ("done", 25), ("done", 0))
    assert plan.landed == 2
    assert plan.failed == 2
    assert plan.states() == ["done", "failed", "done", "failed"]


def test_complete_means_the_run_is_over_not_that_every_batch_succeeded():
    """Conflating them makes the route treat a finished run as interrupted and resubmit a full
    billable regeneration on every poll, forever."""
    assert _run(("done", 25), ("failed", 0)).complete is True
    assert _run(("done", 25), ("running", 0)).complete is False
    assert _run(("done", 25), ("pending", 0)).complete is False
    assert RunPlan(run_id="r").complete is False, "a run with no batches is not a finished run"


def test_exactly_one_batch_is_running_and_it_is_the_one_being_sent():
    plan = _run(("done", 25), ("running", 0), ("pending", 0))
    assert plan.running_index == 1
    assert plan.states() == ["done", "running", "pending"]
    assert _run(("done", 25), ("done", 25)).running_index is None


def test_the_progress_track_never_shows_a_failure_as_a_quieter_success():
    """Colour and state come from the same derivation the counts do, so the track cannot disagree
    with the sentence printed above it."""
    plan = _run(("done", 25), ("done", 0), ("running", 0), ("pending", 0))
    assert plan.states() == ["done", "failed", "running", "pending"]


def test_the_serialised_record_agrees_with_the_object_it_came_from():
    """The UI reads the dict, so a derivation that only holds in Python is a derivation the customer
    never gets."""
    plan = _run(("done", 25), ("failed", 0), ("done", 20))
    d = plan.to_dict()
    assert d["total"] == 3
    assert d["attempted"] == 3
    assert d["landed"] == 2
    assert d["accounts_scored"] == 45
    assert d["complete"] is True
    assert [b["state"] for b in d["batches"]] == ["done", "failed", "done"]
    assert sum(b["accounts"] for b in d["batches"]) == d["accounts_scored"]


def test_a_fresh_run_is_entirely_pending_and_claims_nothing():
    plan = plan_run("r1", 92)
    assert plan.total == 4
    assert [b.planned for b in plan.batches] == [25, 25, 25, 17]
    assert plan.attempted == 0 and plan.landed == 0 and plan.accounts_scored == 0
    assert plan.complete is False
    assert plan.states() == ["pending"] * 4
