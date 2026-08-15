"""Batched analyst inference — the per-request account cap.

A selection larger than the cap is split into ≤cap batches, run ONE AT A TIME, merged strictly
first-to-last, and persisted progressively so the UI can render batch 1's accounts while later
batches still generate. These tests pin the pure core (split + ordered merge), the sequential +
progressive semantics, and the terminal state of a run with a failed batch — no model, no network.
"""
from __future__ import annotations

import contextlib

import pytest

from app.core.config import get_settings
from app.reasoning import analyst as A
from app.reasoning.analyst import _merge_batch_parts, _split_batches


def _batching_core(merged: dict) -> dict:
    """The batching marker without its liveness fields.

    ``run_id`` and ``heartbeat`` identify the run that wrote the entry and when, so another process
    can tell a live batched run from an interrupted one. A heartbeat is a wall-clock timestamp, so
    asserting on the whole dict would be asserting on the current time.
    """
    return {k: v for k, v in (merged["batching"] or {}).items()
            if k not in ("run_id", "heartbeat")}


def _payload(n_accounts: int) -> dict:
    return {
        "video": {
            "url": "https://x.com/i/status/1",
            "commenters": [{"handle": f"user{i}", "external_id": f"id{i}"} for i in range(n_accounts)],
        },
        "overall_probability": 0.4,
    }


def _part(*, scores: list[int], overall: int, model_backed: bool = True,
          in_tok: int = 100, cost: float = 0.01) -> dict:
    return {
        "omi_score": overall,
        "suspicion_tier": "moderate",
        "verdict": "mixed",
        "commenter_assessments": [
            {"ref": f"A{i+1}", "omi_score": s, "suspicion_tier": "low", "assessment": f"account {i} read"}
            for i, s in enumerate(scores)
        ],
        "evidence_for": [{"signal": f"s{overall}", "claim": f"claim-{overall}", "evidence_refs": ["A1"]}],
        "completion": {"complete": True, "represented_commenters": len(scores),
                       "assessed_commenters": len(scores)},
        "investigation_trace": {"model_backed": model_backed, "input_tokens": in_tok,
                                "output_tokens": 50, "total_tokens": in_tok + 50,
                                "endpoint_cost_usd": cost, "endpoint_request_id": f"req-{overall}"},
        "governance": {"provider": "openrouter"},
    }


# --------------------------------------------------------------------------- #
# Split
# --------------------------------------------------------------------------- #
def test_small_selection_is_not_split():
    assert _split_batches(_payload(50), 50) is None
    assert _split_batches(_payload(1), 50) is None


def test_a_large_selection_splits_into_a_FIXED_NUMBER_of_batches():
    """The batch count is a constant, not a function of the selection size.

    Slicing at a fixed size made the count depend on how many accounts someone happened to pick: the
    same customer saw 4 batches on one post and 9 on the next, with nothing on the page to explain
    the difference, and a deployment tuning the slice size for latency silently reshaped every scan.
    100 accounts is four batches of 25, whatever the threshold is set to.
    """
    chunks = _split_batches(_payload(100), 12, batches=4)
    assert chunks is not None
    assert [len(c["video"]["commenters"]) for c in chunks] == [25, 25, 25, 25]
    # Selection order preserved across every boundary.
    assert chunks[0]["video"]["commenters"][0]["handle"] == "user0"
    assert chunks[1]["video"]["commenters"][0]["handle"] == "user25"
    assert chunks[3]["video"]["commenters"][-1]["handle"] == "user99"
    # Non-account context rides along; the cached-assessment key never leaks into a chunk.
    assert all(c["overall_probability"] == 0.4 for c in chunks)


def test_a_remainder_is_spread_across_the_batches_not_dumped_on_the_last():
    """126 over four is 32/32/31/31, not 32/32/32/30.

    Slicing at ceil(n/k) looks equivalent and is not: it concentrates the shortfall in one request
    and, at small counts, produces FEWER batches than asked for (5 over 4 slices to 2/2/1, three
    batches). Spreading the remainder keeps the count exact at every size.
    """
    assert A._batch_sizes(126, 4) == [32, 32, 31, 31]
    assert sum(A._batch_sizes(126, 4)) == 126
    for n in range(5, 200):
        sizes = A._batch_sizes(n, 4)
        assert len(sizes) == 4, n
        assert sum(sizes) == n, n
        assert max(sizes) - min(sizes) <= 1, n


def test_the_count_never_plans_an_empty_request():
    """Fewer accounts than batches. A request carrying no accounts costs a full protocol send and
    can only come back empty."""
    assert A._batch_sizes(3, 4) == [1, 1, 1]
    assert A._batch_sizes(0, 4) == []


def test_the_threshold_still_decides_whether_to_batch_at_all():
    """`analyst_batch_accounts` did not change meaning for a small scan: at or below it, one request.
    A 13-account selection above a 12 threshold becomes four batches, not thirteen."""
    assert _split_batches(_payload(12), 12, batches=4) is None
    sizes = [len(c["video"]["commenters"]) for c in _split_batches(_payload(13), 12, batches=4)]
    assert sizes == [4, 3, 3, 3]


def test_the_shipped_default_is_four_batches():
    """The product decision, pinned. `render.yaml` can raise it if per-batch latency starts racing
    the timeout, but four is what a customer sees unless someone chose otherwise."""
    assert A.DEFAULT_ANALYST_BATCHES == 4
    assert get_settings().analyst_batch_count == 4
    # And the default is what an omitted argument uses, so no call site can quietly diverge.
    assert len(_split_batches(_payload(100), 12)) == 4


# --------------------------------------------------------------------------- #
# Merge — ordered, progressive, telemetry-summing
# --------------------------------------------------------------------------- #
def test_merge_concatenates_accounts_first_to_last():
    parts = [_part(scores=[10, 20], overall=15), _part(scores=[80, 90], overall=85)]
    merged = _merge_batch_parts(parts, batch_size=2, done=2)
    assert merged is not None
    scores = [a["omi_score"] for a in merged["commenter_assessments"]]
    assert scores == [10, 20, 80, 90]
    assert _batching_core(merged) == {"total": 2, "done": 2, "landed": 2, "batch_size": 2, "complete": True}


def test_merge_overall_is_account_weighted_mean_of_batch_overalls():
    # 2 accounts at overall 10 + 2 accounts at overall 90 -> 50; tier follows the band.
    parts = [_part(scores=[10, 10], overall=10), _part(scores=[90, 90], overall=90)]
    merged = _merge_batch_parts(parts, batch_size=2, done=2)
    assert merged["omi_score"] == 50
    assert merged["suspicion_tier"] == "elevated"


def test_partial_merge_reports_progress_and_incomplete():
    parts = [_part(scores=[10], overall=10), None, None]
    merged = _merge_batch_parts(parts, batch_size=1, done=1)
    assert merged is not None
    assert len(merged["commenter_assessments"]) == 1
    assert _batching_core(merged) == {"total": 3, "done": 1, "landed": 1, "batch_size": 1, "complete": False}
    assert merged["completion"]["complete"] is False


def test_merge_sums_usage_and_collects_batch_traces():
    parts = [_part(scores=[10], overall=10, in_tok=100, cost=0.01),
             _part(scores=[20], overall=20, in_tok=200, cost=0.02)]
    merged = _merge_batch_parts(parts, batch_size=1, done=2)
    tr = merged["investigation_trace"]
    assert tr["input_tokens"] == 300
    assert abs(tr["endpoint_cost_usd"] - 0.03) < 1e-9
    assert tr["inference_count"] == 2
    assert [b["batch"] for b in tr["batches"]["traces"]] == [1, 2]
    assert tr["model_backed"] is True


def test_a_floored_batch_marks_the_merge_not_model_backed():
    parts = [_part(scores=[10], overall=10), _part(scores=[20], overall=20, model_backed=False)]
    merged = _merge_batch_parts(parts, batch_size=1, done=2)
    assert merged["investigation_trace"]["model_backed"] is False


def test_merge_with_no_parts_is_none():
    assert _merge_batch_parts([None, None], batch_size=50, done=0) is None


def test_a_finished_run_is_marked_complete_even_with_a_failed_batch():
    """``complete`` means THE RUN IS OVER, not "every batch succeeded".

    If a finished-but-partial run stayed incomplete, the route would treat the cached entry as an
    interrupted run and resubmit a full (billable) regeneration on every poll, forever, while the
    client waited for a batch that is never coming."""
    parts = [_part(scores=[10], overall=10), None, _part(scores=[20], overall=20)]
    merged = _merge_batch_parts(parts, batch_size=1, done=2, run_finished=True)
    assert _batching_core(merged) == {"total": 3, "done": 2, "landed": 2, "batch_size": 1, "complete": True}
    # Still honest about coverage: only the two landed batches' accounts are present.
    assert len(merged["commenter_assessments"]) == 2


# --------------------------------------------------------------------------- #
# The generation loop — sequential, progressive, always terminal
# --------------------------------------------------------------------------- #
@pytest.fixture
def batched(monkeypatch):
    """Drive ``_generate_batched`` with a fake model + fake persistence, recording (a) how many
    persists had happened when each batch STARTED, and (b) every persisted batching marker."""
    persisted: list[dict] = []
    persists_seen_at_start: list[int] = []

    @contextlib.contextmanager
    def fake_session():
        yield object()

    class FakeRepo:
        def __init__(self, _session):
            pass

        def get_investigation(self, slug=None, user_id=None):
            return object()

    def fake_persist(_session, _inv, merged, _provider):
        persisted.append(merged["batching"])
        return {"assessment": merged}

    monkeypatch.setattr(A, "get_session", fake_session)
    monkeypatch.setattr(A, "persist_assessment", fake_persist)
    monkeypatch.setattr("app.storage.repository.AccountRepository", FakeRepo)

    def run(outcomes: list[bool]):
        """``outcomes[i]`` = whether batch i produces an assessment."""
        def fake_assess(chunk, *, ref, platform, settings):
            persists_seen_at_start.append(len(persisted))
            i = len(persists_seen_at_start) - 1
            if not outcomes[i]:
                return None
            n = len(chunk["video"]["commenters"])
            return _part(scores=[10] * n, overall=10)

        monkeypatch.setattr(A, "assess_payload", fake_assess)
        payload = _payload(25 * len(outcomes))
        # `batches` is pinned to the scripted length rather than left at the shipped default of 4:
        # these tests are about the RUN LOOP (ordering, progressive persistence, terminal state with
        # a failed batch), and how the selection is divided is a separate rule tested above.
        chunks = _split_batches(payload, 25, batches=len(outcomes))
        A._generate_batched("inv_test", 1, payload, chunks,
                            platform="x", settings=get_settings())
        return persists_seen_at_start, persisted

    return run


def test_batches_run_one_at_a_time_and_persist_as_they_land(batched):
    """The point of the whole design: batch 1's accounts are saved (and therefore renderable) BEFORE
    batch 2 is even sent. If the batches were fired together, no persist would have happened when
    batches 2 and 3 started."""
    starts, persisted = batched([True, True, True])
    assert starts == [0, 1, 2]
    assert [b["done"] for b in persisted] == [1, 2, 3]
    assert [b["complete"] for b in persisted] == [False, False, True]


def test_get_session_is_importable_at_module_scope():
    """Regression guard for a silent, total failure of the batched path.

    ``_generate_batched``'s progressive persist is a nested closure that calls ``get_session()``. When
    that import lived only inside ``generate_and_persist`` it was a local there, so the closure
    resolved the name against module globals, found nothing, and raised NameError on the first
    persist — swallowed by the background pool. Every investigation larger than one batch produced no
    assessment at all while the client polled until it gave up. Keep the name on the module."""
    assert hasattr(A, "get_session"), (
        "analyst.get_session must be a module-level import — the batched persist closure needs it"
    )


def test_the_default_configuration_is_sequential_25s():
    """Pins the shipped defaults the sequential design depends on."""
    s = get_settings()
    assert s.analyst_batch_accounts == 25
    assert s.analyst_batch_concurrency == 1


def test_a_run_whose_batch_fails_still_ends_complete(batched):
    """A failed middle batch must not leave the run polling forever / regenerating forever."""
    _starts, persisted = batched([True, False, True])
    final = persisted[-1]
    assert final["complete"] is True, "a finished run must be terminal even when a batch failed"
    # `done` counts batches ATTEMPTED, not batches that succeeded. It drives the progress readout and
    # the client's poll-budget reset, and counting only successes meant a run containing any failure
    # could never show itself finishing, and a failed batch looked like no progress at all. How many
    # batches produced accounts is visible in the accounts.
    assert final["done"] == 3 and final["total"] == 3


def test_a_first_batch_failure_still_ends_complete(batched):
    """The prefix flush can never advance here, so the terminal state comes from the final merge."""
    _starts, persisted = batched([False, True])
    assert persisted, "the landed batch must still be persisted"
    final = persisted[-1]
    assert final["complete"] is True
    assert final["done"] == 2 and final["total"] == 2  # both attempted; see the note above


def test_a_fully_successful_run_is_not_persisted_twice(batched):
    """The last progressive flush already wrote the complete entry — writing it again is a wasted
    round trip on the hot path of every large scan."""
    _starts, persisted = batched([True, True])
    assert len(persisted) == 2


# --------------------------------------------------------------------------- #
# A failed batch must not freeze the run
#
# Live symptom on a 100-account scan: batch 1 landed, batch 2 floored, and the UI sat on
# "1 OF 4 DONE" while batches 3 and 4 were still being generated. The progress readout was the
# longest COMPLETED PREFIX, so one failure pinned it, and because progress was only persisted when
# that prefix grew, batches 3 and 4 kept their finished accounts unpersisted until the entire run
# ended minutes later. It read as a hung scan and it withheld work that was already done.
#
# The prefix was never needed for ordering: _merge_batch_parts walks parts by index, so accounts
# always come out in batch order however the batches finish.
# --------------------------------------------------------------------------- #
def test_a_failed_middle_batch_does_not_freeze_progress_or_withhold_later_batches(monkeypatch):
    from app.reasoning import analyst as A

    persisted: list[dict] = []

    def _fake_assess(chunk, *, ref, platform, settings):
        # Batch 2 (ref ...b2) floors; every other batch returns one account.
        if ref.endswith(".b2"):
            return None
        n = ref.rsplit(".b", 1)[1]
        return {
            "omi_score": 20,
            "governance": {"provider": "openrouter-omi-analyst-v1"},
            "commenter_assessments": [{"ref": f"A{n}", "omi_score": 20,
                                       "suspicion_tier": "low", "assessment": "x"}],
        }

    def _fake_persist(session, inv, merged, provider):
        entry = {"assessment": merged, "provider": provider}
        persisted.append(entry)
        return entry

    class _Repo:
        def __init__(self, _s): pass
        def get_investigation(self, **_k): return object()

    import contextlib

    @contextlib.contextmanager
    def _fake_session():
        yield object()

    monkeypatch.setattr(A, "assess_payload", _fake_assess)
    monkeypatch.setattr(A, "persist_assessment", _fake_persist)
    monkeypatch.setattr(A, "get_session", _fake_session)
    monkeypatch.setattr("app.storage.repository.AccountRepository", _Repo)

    chunks = [{"video": {"commenters": [{"handle": f"h{i}"}]}} for i in range(4)]
    A._generate_batched("inv_x", 1, {"video": {"commenters": []}}, chunks,
                        platform="twitter", settings=A.get_settings())

    # Progress was persisted after EVERY batch, including the one that failed and the two after it.
    assert len(persisted) >= 4, f"only {len(persisted)} persists; a failed batch stalled the run"

    dones = [e["assessment"]["batching"]["done"] for e in persisted]
    assert dones == sorted(dones), f"progress went backwards: {dones}"
    assert dones[-1] == 4, f"final progress should count all four attempts, got {dones}"

    # Batches 3 and 4 reached the reader rather than waiting for the run to end.
    final_refs = [a["ref"] for a in persisted[-1]["assessment"]["commenter_assessments"]]
    assert final_refs == ["A1", "A3", "A4"], final_refs


# --------------------------------------------------------------------------- #
# Progress must never go backwards on screen
#
# Live symptom (2026-08-05): the panel reached "3 of 4" and then dropped back to "1 of 4" with no
# accounts scored. Two runs were writing to one row. `_autogen_inflight` is a PER-PROCESS set, so a
# second worker (or a poll after a restart) looked at the incomplete entry, concluded the run had
# been interrupted, and started a duplicate whose first write replaced the user's 75 accounts with
# 25.
# --------------------------------------------------------------------------- #
def _entry(*, done: int, total: int, accounts: int, run_id: str,
           heartbeat_age_sec: float = 0.0, complete: bool = False) -> dict:
    from datetime import datetime, timedelta, timezone
    beat = datetime.now(timezone.utc) - timedelta(seconds=heartbeat_age_sec)
    return {"assessment": {
        "commenter_assessments": [{"ref": f"A{i+1}"} for i in range(accounts)],
        "batching": {"total": total, "done": done, "batch_size": 25, "complete": complete,
                     "run_id": run_id, "heartbeat": beat.isoformat()},
    }}


def test_a_fresh_heartbeat_means_some_process_is_still_working():
    assert A.batched_run_looks_alive(_entry(done=3, total=4, accounts=75, run_id="r1")) is True
    # Stale: whoever was writing has stopped, so this entry is fair game to regenerate.
    assert A.batched_run_looks_alive(
        _entry(done=3, total=4, accounts=75, run_id="r1",
               heartbeat_age_sec=A.BATCH_HEARTBEAT_STALE_SEC + 5)) is False
    # A finished run is not "alive", however recently it was written.
    assert A.batched_run_looks_alive(
        _entry(done=4, total=4, accounts=100, run_id="r1", complete=True)) is False
    # Entries written before the field existed must still self-heal rather than block forever.
    assert A.batched_run_looks_alive(
        {"assessment": {"batching": {"total": 4, "done": 3, "complete": False}}}) is False
    assert A.batched_run_looks_alive(None) is False


def test_a_duplicate_run_does_not_publish_its_first_batch_over_a_live_runs_third():
    """The exact regression: run B's "1 of 4" must not replace run A's "3 of 4"."""
    live = _entry(done=3, total=4, accounts=75, run_id="runA")
    mine = {"commenter_assessments": [{"ref": "A1"}] * 25,
            "batching": {"total": 4, "done": 1, "run_id": "runB", "complete": False}}
    assert A._entry_is_ahead(live, mine, "runB") is True


def test_a_run_always_advances_over_its_own_earlier_writes():
    """Deferring to our own previous write would freeze the run at batch 1 forever."""
    ours = _entry(done=3, total=4, accounts=75, run_id="runA")
    mine = {"commenter_assessments": [{"ref": "A1"}] * 100,
            "batching": {"total": 4, "done": 4, "run_id": "runA", "complete": False}}
    assert A._entry_is_ahead(ours, mine, "runA") is False


def test_a_dead_run_is_replaceable_even_though_it_has_more_accounts():
    """Otherwise a crashed run's partial result would be permanent and nothing could heal it."""
    dead = _entry(done=3, total=4, accounts=75, run_id="runA",
                  heartbeat_age_sec=A.BATCH_HEARTBEAT_STALE_SEC + 60)
    mine = {"commenter_assessments": [{"ref": "A1"}] * 25,
            "batching": {"total": 4, "done": 1, "run_id": "runB", "complete": False}}
    assert A._entry_is_ahead(dead, mine, "runB") is False


def test_catching_up_publishes_again():
    """The guard defers, it does not disable the run. Once we draw level we write."""
    live = _entry(done=2, total=4, accounts=50, run_id="runA")
    mine = {"commenter_assessments": [{"ref": "A1"}] * 75,
            "batching": {"total": 4, "done": 3, "run_id": "runB", "complete": False}}
    assert A._entry_is_ahead(live, mine, "runB") is False


def test_a_duplicate_runs_FINAL_write_cannot_bury_a_live_runs_progress():
    """The worst version of the bug, and the one that survived the first fix.

    The final write used to be exempt from the guard. So a duplicate run finishing with one batch
    published 25 accounts over the leader's 75 AND set ``complete: true``, which stops the entry
    being regenerable: the customer was left permanently with a quarter of what they paid for.
    """
    live = _entry(done=3, total=4, accounts=75, run_id="runA")
    final = {"commenter_assessments": [{"ref": "A1"}] * 25,
             "batching": {"total": 4, "done": 4, "run_id": "runB", "complete": True}}
    assert A._entry_is_ahead(live, final, "runB") is True


def test_a_forced_refresh_does_not_start_a_second_run_against_a_live_one(monkeypatch):
    """`refresh` used to skip reading the entry entirely, so every forced regeneration raced.

    Both the route's one-shot floor auto-heal and the UI's Retry button pass refresh=True. A refresh
    exists to heal a dead or floored result, not to race a live one.
    """
    live = _entry(done=3, total=4, accounts=75, run_id="runA")

    class _Inv:
        slug = "inv_live"
        payload_json = {"video": {"commenters": []}}

    class _Repo:
        def __init__(self, _s): pass
        def get_investigation(self, **_k): return _Inv()

    @contextlib.contextmanager
    def _fake_session():
        yield object()

    called: list[str] = []

    monkeypatch.setattr(A, "get_session", _fake_session)
    monkeypatch.setattr(A, "cached_assessment", lambda _inv: live)
    monkeypatch.setattr(A, "analyst_enabled", lambda _s: True)
    monkeypatch.setattr(A, "assess_payload",
                        lambda *a, **k: called.append("model") or None)
    monkeypatch.setattr("app.storage.repository.AccountRepository", _Repo)

    out = A.generate_and_persist("inv_live", 1, refresh=True)

    assert out is live, "a forced refresh must serve the live run's partial, not start a duplicate"
    assert called == [], "a forced refresh started a duplicate model run against a live one"


def test_a_finished_run_that_missed_a_batch_is_still_model_backed():
    """MISSING COVERAGE IS NOT FLOORED, and conflating them restarted finished scans.

    Live symptom: the results appeared, then the panel started batching again from the top. A run
    that landed 3 of 4 batches was marked non-model-backed on the strength of the fourth, which is
    exactly the signal the route's floor self-heal keys on, so the moment the scan finished the route
    regenerated the WHOLE thing and billed a second full run.

    `model_backed` answers "is the prose in this entry the model's?" and for three real batches it is
    yes. Coverage is a separate fact, carried by `landed`.
    """
    parts = [_part(scores=[10], overall=10), None, _part(scores=[20], overall=20)]
    merged = _merge_batch_parts(parts, batch_size=1, done=3, run_finished=True)
    assert merged["investigation_trace"]["model_backed"] is True, \
        "a finished run with real model prose must not look like the Floor"
    # ...and the shortfall is still visible, so the UI can offer a retry the user chooses to spend.
    assert merged["batching"]["landed"] == 2
    assert merged["batching"]["total"] == 3
    assert merged["batching"]["complete"] is True


def test_a_run_where_every_batch_floored_is_still_not_model_backed():
    """The inverse, so the self-heal that matters keeps working.

    A floored batch returns an assessment carrying model_backed=False, so a wholly floored run is
    caught by the per-part check rather than by the coverage count.
    """
    parts = [_part(scores=[10], overall=10, model_backed=False),
             _part(scores=[20], overall=20, model_backed=False)]
    merged = _merge_batch_parts(parts, batch_size=1, done=2, run_finished=True)
    assert merged["investigation_trace"]["model_backed"] is False


def test_landed_is_the_coverage_figure_and_done_is_not():
    """`done` counts ATTEMPTS so the readout moves when a batch fails, which makes it equal to
    `total` on every finished run. Keying coverage off it would silence the notice entirely."""
    parts = [_part(scores=[10], overall=10), None, None]
    merged = _merge_batch_parts(parts, batch_size=1, done=3, run_finished=True)
    assert merged["batching"]["done"] == 3      # every batch was attempted
    assert merged["batching"]["landed"] == 1    # only one produced accounts


# --------------------------------------------------------------------------- #
# The startup window: "it scans twice"
#
# `batching.heartbeat` only exists once the FIRST batch has persisted, minutes into a run. Until
# then a batched generation is invisible to every other process, so the page's first POST (arriving
# seconds after the scan scheduled the run) landed on another worker and started a second full run.
# Two OpenRouter runs, two bills, one investigation.
# --------------------------------------------------------------------------- #
class _LeaseInv:
    def __init__(self, payload=None):
        self.slug = "inv_lease"
        self.payload_json = payload or {}


class _LeaseSession:
    """Just enough session for the SAVEPOINT-wrapped lease write."""
    def begin_nested(self):
        return contextlib.nullcontext()

    def add(self, _obj):
        pass


def test_the_lease_is_claimed_before_any_batch_has_landed():
    """The whole point: a claim that exists from the first moment of the run."""
    inv, session = _LeaseInv(), _LeaseSession()
    assert A.generation_lease_is_live(inv) is False
    assert A.claim_generation_lease(session, inv, "runA") is True
    assert A.generation_lease_is_live(inv) is True


def test_a_second_process_cannot_claim_a_live_lease():
    inv, session = _LeaseInv(), _LeaseSession()
    assert A.claim_generation_lease(session, inv, "runA") is True
    assert A.claim_generation_lease(session, inv, "runB") is False, \
        "a second worker started a duplicate run while the first was still going"


def test_a_run_can_reclaim_its_own_lease():
    inv, session = _LeaseInv(), _LeaseSession()
    assert A.claim_generation_lease(session, inv, "runA") is True
    assert A.claim_generation_lease(session, inv, "runA") is True


def test_a_stale_lease_does_not_block_a_new_run_forever():
    """A crashed run must not lock the investigation out of ever being generated again."""
    from datetime import datetime, timedelta, timezone
    old = (datetime.now(timezone.utc)
           - timedelta(seconds=A.BATCH_HEARTBEAT_STALE_SEC + 60)).isoformat()
    inv = _LeaseInv({A.LEASE_KEY: {"run_id": "dead", "heartbeat": old}})
    assert A.generation_lease_is_live(inv) is False
    assert A.claim_generation_lease(_LeaseSession(), inv, "runB") is True


def test_releasing_frees_the_investigation_immediately():
    """Otherwise a Retry right after a run would sit out the whole staleness window."""
    inv, session = _LeaseInv(), _LeaseSession()
    A.claim_generation_lease(session, inv, "runA")
    A.release_generation_lease(session, inv, "runA")
    assert A.generation_lease_is_live(inv) is False


def test_releasing_someone_elses_lease_is_a_no_op():
    inv, session = _LeaseInv(), _LeaseSession()
    A.claim_generation_lease(session, inv, "runA")
    A.release_generation_lease(session, inv, "runB")
    assert A.generation_lease_is_live(inv) is True, "runB released a lease it did not own"


def test_the_lease_is_never_mistaken_for_a_result():
    """It lives outside the assessment cache, so `cached_assessment` cannot return it."""
    inv, session = _LeaseInv(), _LeaseSession()
    A.claim_generation_lease(session, inv, "runA")
    assert A.LEASE_KEY != A.CACHE_KEY
    assert A.cached_assessment(inv) is None
