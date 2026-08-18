"""A salvaged run must not buy itself a second full generation.

Reported live from a 100-account scan: the customer read the per-account verdicts, then watched the
panel reset to "1 of 4" and analyse the whole investigation again. The chain:

  batch 1's wrapper fails validation
    -> `_salvaged_account_reads` keeps its 25 per-account rows (the paid-for substance)
    -> `_merge_batch_parts` marks the MERGED entry model_backed=False on the strength of that part
    -> `routes/reasoning.py`'s floor self-heal keys on exactly that flag
    -> sets refresh=True, which also BYPASSES the live-run guard
    -> submits a second full run of every batch.

Nothing outside the OpenRouter bill would have shown it. These tests pin the distinction the fix
rests on: `entry_is_model_backed` is a question about the SYNTHESIS WRAPPER, and
`entry_warrants_auto_regeneration` is a question about MONEY, and they are not the same question.
"""
from __future__ import annotations

from app.reasoning import analyst


def _entry(*, model_backed: bool, reads: int, provider: str = "openrouter-omi-analyst-v1") -> dict:
    return {
        "provider": provider,
        "assessment": {
            "investigation_trace": {"model_backed": model_backed},
            "commenter_assessments": [
                {"ref": f"A{i}", "resolved": True, "omi_score": 20 + i,
                 "assessment": "A real paragraph the model wrote."}
                for i in range(reads)
            ],
        },
    }


class TestWhatWarrantsASecondBillableRun:
    def test_a_salvaged_run_does_not(self):
        """THE REGRESSION. Floored wrapper, 25 real per-account reads: the customer already has the
        substance. What is missing is the summary paragraph above them, and that is not worth a full
        re-run of every batch that nobody asked for."""
        entry = _entry(model_backed=False, reads=25)
        assert analyst.entry_is_model_backed(entry) is False
        assert analyst.entry_has_model_account_reads(entry) is True
        assert analyst.entry_warrants_auto_regeneration(entry) is False

    def test_a_total_floor_still_does(self):
        """The self-heal must keep working for the case it was built for: nothing of the model's
        survived, so there is nothing to lose and everything to gain."""
        entry = _entry(model_backed=False, reads=0,
                       provider="openrouter->fallback:deterministic-analyst-v1")
        assert analyst.entry_warrants_auto_regeneration(entry) is True

    def test_a_healthy_run_never_does(self):
        assert analyst.entry_warrants_auto_regeneration(_entry(model_backed=True, reads=25)) is False

    def test_a_missing_entry_does(self):
        """Nothing cached at all is the uncached path, not a refusal to regenerate."""
        assert analyst.entry_warrants_auto_regeneration(None) is True
        assert analyst.entry_warrants_auto_regeneration({}) is True

    def test_one_salvaged_read_is_enough_to_refuse(self):
        """Deliberately not a threshold. Any model-authored read means a regeneration is discarding
        work somebody paid for in order to spend more money, and the customer can still press Retry
        if they judge it worth it. That choice is theirs, not ours."""
        assert analyst.entry_warrants_auto_regeneration(_entry(model_backed=False, reads=1)) is False


class TestTheRouteServesASalvagedEntryAsFinished:
    def test_the_serve_gate_and_the_spend_gate_disagree_on_purpose(self):
        """`entry_is_model_backed` stays False for a salvaged entry, because the SYNTHESIS prose
        really is the Floor's and must never be presented as the model's. The page renders
        `AiUnavailable summaryOnly` above the reads for exactly that reason. Only the spend decision
        changes."""
        entry = _entry(model_backed=False, reads=25)
        assert analyst.entry_is_model_backed(entry) is False, (
            "the wrapper is still the Floor's; changing this would publish Floor prose as the model's"
        )
        assert analyst.entry_warrants_auto_regeneration(entry) is False
