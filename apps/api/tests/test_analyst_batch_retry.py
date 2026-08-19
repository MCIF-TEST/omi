"""Retrying a floored batch, salvaging a floored wrapper, and announcing a broken config at boot.

Three fixes to one failure, and the reason they belong together is that each one is a different
answer to "the model did not produce a usable analysis":

* **Retry** when a second call could plausibly differ (a transient 429, a malformed draw, a reply cut
  off at the token cap). A batch used to be lost outright on the first bad draw.
* **Salvage** the per-account reads when only the executive wrapper failed. That is the part the
  customer paid for, and it was being thrown away with the wrapper.
* **Announce** a config fault at boot, because none of the above helps against a revoked key: the
  retry is refused (correctly), the salvage finds nothing, and the deployment floors every scan in
  silence until somebody complains.

The spend discipline is the load-bearing half of the retry tests. Every extra generation is real
money, so the assertions are on the exact number of calls, not on "it recovered".
"""

from __future__ import annotations

import contextlib
import logging
from types import SimpleNamespace

import pytest

from app.reasoning import analyst
from app.reasoning import floor_reason as FR


# ==================================================================================================
# Helpers
# ==================================================================================================
def _floored(reason: str | None = None, *, status: int | None = None,
             finish: str | None = None) -> dict:
    """An assessment shaped like a real floored one: prose present, trace saying it is the Floor."""
    return {
        "verdict": "inconclusive", "omi_score": 10, "suspicion_tier": "low",
        "headline": "h", "assessment": "a", "commenter_assessments": [],
        "governance": {"provider": "openrouter->fallback:deterministic-analyst-v1"},
        "investigation_trace": {
            "model_backed": False, "fallback_reason": reason,
            "response_status": status, "finish_reason": finish,
        },
    }


def _good(n: int = 2) -> dict:
    return {
        "verdict": "likely_authentic", "omi_score": 20, "suspicion_tier": "low",
        "headline": "h", "assessment": "a",
        "commenter_assessments": [{"ref": f"A{i}", "handle": f"h{i}", "omi_score": 10,
                                   "assessment": "x", "resolved": True} for i in range(n)],
        "governance": {"provider": "openrouter"},
        "investigation_trace": {"model_backed": True},
    }


def _payload(accounts: int) -> dict:
    return {
        "video": {
            "video_id": "vid1",
            "commenters": [
                {"external_id": f"u{i}", "handle": f"h{i}", "overall_probability": 0.8,
                 "tier": "high", "recent_activity": []}
                for i in range(accounts)
            ],
            "coordination_score": 0.1, "clusters": [],
        },
        "overall_tier": "moderate", "overall_probability": 0.4, "summary": "s",
    }


class _Repo:
    """The narrowest stand-in for AccountRepository that ``_generate_batched`` touches."""

    def __init__(self, _session):
        pass

    def get_investigation(self, slug=None, user_id=None):
        return object()


@pytest.fixture()
def batched(monkeypatch):
    """Drive ``_generate_batched`` with a scripted per-batch outcome and count the calls.

    Everything the run does besides calling the model is stubbed: persistence, sessions, and the
    liveness guard. What is NOT stubbed is the retry logic itself, which is the subject.
    """
    calls: list[dict] = []

    @contextlib.contextmanager
    def fake_session():
        yield object()

    persists: list[dict] = []

    def fake_persist(_s, _i, merged, _p):
        persists.append(merged)
        return {"assessment": merged}

    monkeypatch.setattr(analyst, "get_session", fake_session)
    monkeypatch.setattr(analyst, "persist_assessment", fake_persist)
    monkeypatch.setattr(analyst, "cached_assessment", lambda _inv: None)
    monkeypatch.setattr("app.storage.repository.AccountRepository", _Repo)

    def run(outcomes, *, accounts=4, batch_size=2):
        """``outcomes`` maps a batch index to a list of results, consumed one per attempt.

        A batch with nothing left in its queue returns a healthy assessment, so an unscripted batch
        is the control rather than a second failure.
        """
        pending = {i: list(v) for i, v in outcomes.items()}

        def fake_assess(chunk, *, ref, platform, settings=None, **kw):
            i = int(str(ref).rsplit(".b", 1)[1]) - 1
            calls.append({"batch": i, "kwargs": kw})
            queue = pending.get(i)
            return queue.pop(0) if queue else _good(len(chunk["video"]["commenters"]))

        monkeypatch.setattr(analyst, "assess_payload", fake_assess)
        payload = _payload(accounts)
        # Explicit count so the scripted outcome indices line up. How a selection is divided is a
        # separate rule with its own tests; these are about what happens when a batch fails.
        chunks = analyst._split_batches(payload, batch_size,
                                        batches=max(1, accounts // batch_size))
        settings = SimpleNamespace(analyst_batch_accounts=batch_size, analyst_batch_concurrency=1)
        entry = analyst._generate_batched("slug1", 1, payload, chunks,
                                          platform="x", settings=settings)
        return (entry or {}).get("assessment")

    run.calls = calls
    # Every merge the run WROTE, in order. The final entry alone cannot answer what the page said
    # while the run was still going, which is the whole subject of the attempt record below.
    run.persists = persists
    return run


def _calls_for(calls, batch: int) -> list[dict]:
    return [c for c in calls if c["batch"] == batch]


# ==================================================================================================
# Retry: exactly once, and only where a second call could differ
# ==================================================================================================
def test_a_transient_floor_is_retried_exactly_once_and_recovers(batched):
    batched({0: [_floored(FR.RATE_LIMITED)]})
    assert len(_calls_for(batched.calls, 0)) == 2, "a retryable floor must be retried once"
    assert len(_calls_for(batched.calls, 1)) == 1, "a healthy batch must not be retried"


def test_a_retry_that_also_floors_is_not_retried_again(batched):
    """One retry, not a loop. Two attempts is a bounded cost; 'until it works' is not."""
    batched({0: [_floored(FR.RATE_LIMITED), _floored(FR.RATE_LIMITED)]})
    assert len(_calls_for(batched.calls, 0)) == 2


def test_a_dead_credential_is_never_retried(batched):
    """The second call fails identically, so retrying is pure spend in front of a failure the
    operator needs to see."""
    batched({0: [_floored(FR.BAD_API_KEY)], 1: [_floored(FR.BAD_API_KEY)]})
    assert len(_calls_for(batched.calls, 0)) == 1
    assert len(_calls_for(batched.calls, 1)) == 1


def test_a_timeout_is_never_retried(batched):
    """It may already have billed on their side. This must agree with the HTTP layer's own policy."""
    batched({0: [_floored(FR.MODEL_TIMEOUT)]})
    assert len(_calls_for(batched.calls, 0)) == 1


def test_a_truncated_batch_retries_with_more_room(batched):
    """Retrying a truncated reply UNCHANGED would truncate again at the same cap, which is exactly
    why the in-transport retry declines it. The second attempt has to be a different question."""
    batched({0: [_floored(None, finish="length")]})
    attempts = _calls_for(batched.calls, 0)
    assert len(attempts) == 2
    assert attempts[0]["kwargs"].get("completion_budget_multiplier") is None, (
        "the FIRST attempt must be byte-identical to what it always was")
    assert attempts[1]["kwargs"].get("completion_budget_multiplier", 1.0) > 1.0


def test_the_circuit_opens_after_two_unfixable_floors(batched):
    """A 12-batch scan against a broken config must not double its generations before giving up."""
    dead = {i: [_floored(FR.NO_CREDIT)] for i in range(6)}
    # Batches 0 and 1 floor unfixably and open the circuit; 2 onwards floor for a reason that WOULD
    # normally be retried, and must not be.
    dead[2] = [_floored(FR.RATE_LIMITED)]
    dead[3] = [_floored(FR.RATE_LIMITED)]
    batched(dead, accounts=12, batch_size=2)
    for i in range(6):
        assert len(_calls_for(batched.calls, i)) == 1, f"batch {i} was retried past the breaker"


def test_a_batch_that_crashed_outright_is_still_retried(batched, monkeypatch):
    """``_attempt`` returns None on an exception. That is the most transient failure of all and used
    to be the one that lost the batch permanently."""
    batched({0: [None]})
    assert len(_calls_for(batched.calls, 0)) == 2


def test_a_floored_result_is_kept_when_the_retry_produces_nothing(batched):
    """A floored assessment still carries every deterministic score. Discarding it in favour of the
    retry's None would lose the accounts entirely, which is worse than the floor."""
    merged = batched({0: [_floored(FR.RATE_LIMITED), None]})
    assert merged is not None
    assert merged["batching"]["total"] == 2


# ==================================================================================================
# Salvage: the wrapper floored, the reads did not
# ==================================================================================================
def _legend_for(aliases: dict[str, str]):
    class _Legend:
        def to_manifest(self):
            return {"accounts": dict(aliases)}

        def resolve(self, alias):
            return aliases.get(alias)

    return _Legend()


def test_the_per_account_reads_survive_a_wrapper_that_failed_validation():
    """The substantive output of an investigation is the per-account reads. Throwing twenty good
    paragraphs away because the summary above them was missing a field is the product refusing work
    the customer already paid for."""
    payload = {"video": {"commenters": [
        {"external_id": "u0", "handle": "one", "overall_probability": 0.8,
         "tier": "high", "recent_activity": []},
    ]}}
    raw = {"commenter_assessments": [
        {"ref": "A1", "omi_score": 60, "assessment": "a read of this account", "confidence": 50},
    ]}
    # The legend maps an alias to the pseudonymous author ref the model reasons over, which is
    # `_ref(handle)` and not the external id.
    rows = analyst._salvaged_account_reads(
        raw, _legend_for({"A1": analyst._ref("one")}), payload, governor_verdict="permit")
    assert rows and rows[0]["resolved"] is True
    assert rows[0]["omi_score"] == 60


def test_a_governor_rejection_is_never_salvaged():
    """Our own policy layer refused this output. Reaching around it to publish the rows it refused
    is the wrong instinct, and this must stay true if the adjudication mode ever changes."""
    payload = {"video": {"commenters": [
        {"external_id": "u0", "handle": "one", "overall_probability": 0.8},
    ]}}
    raw = {"commenter_assessments": [{"ref": "A1", "omi_score": 60, "assessment": "x"}]}
    assert analyst._salvaged_account_reads(
        raw, _legend_for({"A1": analyst._ref("one")}), payload, governor_verdict="reject") == []


def test_rows_that_resolve_to_nobody_are_not_salvaged():
    """A read of no account is not a read. An entry carrying only unresolved rows under a Floor
    wrapper is worse than an honest failure notice."""
    payload = {"video": {"commenters": []}}
    raw = {"commenter_assessments": [{"ref": "A9", "omi_score": 60, "assessment": "x"}]}
    assert analyst._salvaged_account_reads(
        raw, _legend_for({}), payload, governor_verdict="permit") == []


def test_nothing_is_salvaged_from_an_empty_response():
    payload = {"video": {"commenters": []}}
    for raw in (None, {}, {"commenter_assessments": []}, {"commenter_assessments": "nope"}):
        assert analyst._salvaged_account_reads(
            raw, _legend_for({}), payload, governor_verdict="permit") == []


def test_a_merged_run_flags_reads_that_survived_a_floor(batched):
    """A mixed batched run: one batch floored, so the merged entry is not model-backed while the
    other batch's reads are perfectly good. The UI needs to be able to tell that apart from a run
    that produced nothing, or it hides paid-for work behind 'could not be produced'."""
    merged = batched({0: [_floored(FR.BAD_API_KEY)]})
    trace = merged["investigation_trace"]
    assert trace["model_backed"] is False, "a floored batch must still block the self-heal path"
    assert trace["account_reads_salvaged"] is True
    assert merged["commenter_assessments"], "the good batch's reads must survive the merge"


def test_a_wholly_floored_run_does_not_claim_salvaged_reads(batched):
    merged = batched({0: [_floored(FR.BAD_API_KEY)], 1: [_floored(FR.BAD_API_KEY)]})
    trace = merged["investigation_trace"]
    assert trace["model_backed"] is False
    assert trace["account_reads_salvaged"] is False


# ==================================================================================================
# Boot preflight: it may never be the thing that breaks the boot
# ==================================================================================================
def test_the_preflight_no_ops_without_a_credential(monkeypatch):
    """A dev machine is not a misconfigured deployment. An alert that fires there is one people
    learn to ignore, which costs us the alert on the day it is real."""
    from app.core.config import get_settings
    from app.reasoning import boot_preflight

    monkeypatch.setenv("OMI_ANALYST_ENABLED", "true")
    monkeypatch.setenv("OMI_ANALYST_PROVIDER", "openrouter")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        assert boot_preflight.run_boot_preflight() is None
    finally:
        get_settings.cache_clear()


def test_the_preflight_no_ops_when_the_analyst_is_switched_off(monkeypatch):
    from app.core.config import get_settings
    from app.reasoning import boot_preflight

    monkeypatch.setenv("OMI_ANALYST_ENABLED", "false")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    get_settings.cache_clear()
    try:
        assert boot_preflight.run_boot_preflight() is None
    finally:
        get_settings.cache_clear()


def test_a_failing_probe_is_reported_to_the_error_tracker(monkeypatch, caplog):
    """The log line already existed for other faults and was not enough: nobody reads a log they are
    not already looking at. The assertion is that the EXCEPTION reaches the sink."""
    from app.core.config import get_settings
    from app.reasoning import boot_preflight
    from app.reasoning.model_providers import openrouter as orp

    seen: list[BaseException] = []
    monkeypatch.setattr(boot_preflight, "AnalystPreflightFailed", boot_preflight.AnalystPreflightFailed)
    monkeypatch.setattr("app.core.observability.capture_exception", seen.append)
    monkeypatch.setattr(orp.OpenRouterReasoningProvider, "probe", lambda self: {
        "ok": False, "reason": "preset_or_model_not_found", "model_ref": "@preset/gone",
        "detail": "no such preset",
    })
    monkeypatch.setenv("OMI_ANALYST_ENABLED", "true")
    monkeypatch.setenv("OMI_ANALYST_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    get_settings.cache_clear()
    try:
        with caplog.at_level(logging.ERROR):
            result = boot_preflight.run_boot_preflight()
    finally:
        get_settings.cache_clear()

    assert result is not None and result["ok"] is False
    assert seen and isinstance(seen[0], boot_preflight.AnalystPreflightFailed)
    assert "preset_or_model_not_found" in str(seen[0])
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "ANALYST PREFLIGHT FAILED" in joined
    assert "preflight" in joined, "the log must name where to look next"


def test_the_preflight_never_raises_however_broken_the_probe_is(monkeypatch):
    """Monitoring that can break the thing it monitors is a downgrade."""
    from app.core.config import get_settings
    from app.reasoning import boot_preflight
    from app.reasoning.model_providers import openrouter as orp

    def explode(self):
        raise RuntimeError("the probe itself is broken")

    monkeypatch.setattr(orp.OpenRouterReasoningProvider, "probe", explode)
    monkeypatch.setenv("OMI_ANALYST_ENABLED", "true")
    monkeypatch.setenv("OMI_ANALYST_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    get_settings.cache_clear()
    try:
        assert boot_preflight.run_boot_preflight() is None
    finally:
        get_settings.cache_clear()


def test_scheduling_never_raises_even_with_no_pool(monkeypatch):
    from app.reasoning import boot_preflight

    monkeypatch.setattr("app.core.background.submit",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no pool")))
    boot_preflight.schedule_boot_preflight()      # must not raise


# ==================================================================================================
# The attempt record: a retry has to be visible WHILE it is happening
# ==================================================================================================
# Reported live: "the fourth batch has been running about ten minutes and the others were quick."
# That is a batch on its second model call, and nothing on the page could say so — a retried batch
# and a slow first attempt rendered identically as "waiting on batch 4 of 4". One batch can honestly
# occupy a very long time across attempts (a per-request timeout, up to two in-transport retries,
# then the whole call again), so the number of the attempt is the fact that makes the wait legible.
def _record(merged: dict) -> list[dict]:
    return (merged.get("batching") or {}).get("batches") or []


def test_an_ordinary_batch_reports_its_first_attempt(batched):
    merged = batched({})
    assert [b["attempt"] for b in _record(merged)] == [1, 1]


def test_a_retried_batch_reports_the_second_attempt(batched):
    merged = batched({0: [_floored(FR.RATE_LIMITED)]})
    rec = _record(merged)
    assert rec[0]["attempt"] == 2, "the retried batch must say it cost two calls"
    assert rec[1]["attempt"] == 1, "an untouched batch must not inherit its neighbour's count"


def test_the_retry_is_published_before_the_second_call_not_after_it(batched):
    """Saying so once the retry is over is saying so too late to help anyone watching the strip.

    The write happens between the two calls, so there must be a persisted merge in which the batch
    is on attempt 2, is marked running, and has NOT yet produced accounts.

    Batch 1 rather than batch 0 on purpose: nothing can be published before the first batch lands,
    because there is no merge to write. A retry of the very first batch is therefore invisible by
    construction, which is honest — the page has no batching record to render at that point either.
    """
    batched({1: [_floored(FR.RATE_LIMITED)]}, accounts=6, batch_size=2)
    mid = [m for m in batched.persists
           if any(b["index"] == 1 and b.get("attempt") == 2 and b["state"] == "running"
                  for b in _record(m))]
    assert mid, "no progress was published while the retry was in flight"


def test_the_batch_on_the_wire_is_marked_running_not_pending(batched):
    """The client prefers the server's record over its own reconstruction, so the moment the record
    shipped with every incomplete batch as "pending", the strip's "Waiting on batch N of M" line
    became unreachable and a reader watching a long batch was told nothing about it."""
    batched({1: [_floored(FR.RATE_LIMITED)]}, accounts=6, batch_size=2)
    live = [m for m in batched.persists if any(b["state"] == "running" for b in _record(m))]
    assert live, "no write ever named the batch that was on the wire"
    states = _record(live[0])
    assert sum(1 for b in states if b["state"] == "running") == 1, (
        "a sequential run holds exactly one request open")


def test_a_finished_run_has_nothing_running(batched):
    """A batch that floored to nothing is finished and failed, not still in flight."""
    merged = batched({0: [_floored(FR.BAD_API_KEY), None], 1: [None, None]})
    assert not any(b["state"] == "running" for b in _record(merged))


def test_a_batch_that_is_never_retried_never_claims_a_second_attempt(batched):
    """The count is calls actually made. A dead credential is refused a retry, so reporting two
    would tell an operator money was spent that was not."""
    merged = batched({0: [_floored(FR.BAD_API_KEY)]})
    assert _record(merged)[0]["attempt"] == 1


def test_a_resumed_batch_is_not_counted_as_an_attempt_by_this_run(batched, monkeypatch):
    """A checkpointed batch costs this run no model call at all, so it must not report one."""
    monkeypatch.setattr(analyst, "_load_batch_parts",
                        lambda _inv, _sig, _total: {0: _good(2)})
    merged = batched({})
    assert len(_calls_for(batched.calls, 0)) == 0
    assert _record(merged)[0]["attempt"] == 1, (
        "a batch this run never sent must read as the ordinary first attempt, not as zero")


def test_the_running_batch_is_named_for_the_whole_time_it_is_running(batched):
    """Not just during a retry. Progress used to be written only when a batch LANDED, so for the
    entire duration of an ordinary batch — which is all of the time anyone spends waiting — the
    stored record described it as pending and the strip could say nothing about it."""
    batched({}, accounts=6, batch_size=2)
    named = set()
    for m in batched.persists:
        for b in _record(m):
            if b["state"] == "running":
                named.add(b["index"])
    assert named == {1, 2}, (
        "every batch after the first must be named while it is on the wire "
        f"(named {sorted(named)}); batch 0 cannot be, there is no merge to write yet")
