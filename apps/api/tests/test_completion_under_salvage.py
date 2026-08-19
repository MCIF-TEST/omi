"""The coverage box must not deny reasoning that is printed directly beneath it.

Seen live, as three lines of one box, above twenty-five model-written paragraphs:

    PARTIAL AI COVERAGE · 25 OF 25 COMMENTERS ASSESSED
    AI reasoning was not produced (deterministic Floor); completeness not applicable.
    ~25 commenters remaining.
    25/25 analyzed · 12,970/23,250 out tokens · stop: stop

Every clause came from `verify_completion` and no two of them agreed. The cause is that salvage was
being reported as a Floor: `model_backed` is False on that path, so the Floor branch fired even
though every account genuinely did receive the model's own read.
"""
from __future__ import annotations

from app.reasoning.completion import verify_completion


class TestSalvageIsNotAFloor:
    def _salvaged(self, **kw):
        base = dict(model_backed=False, finish_reason="stop", represented_commenters=25,
                    assessed_commenters=25, omitted_input_commenters=0, salvaged_reads=True)
        base.update(kw)
        return verify_completion(**base)

    def test_it_does_not_claim_no_reasoning_was_produced(self):
        c = self._salvaged()
        assert "was not produced" not in c.reason.lower()
        assert "deterministic floor" not in c.reason.lower()

    def test_it_does_not_report_every_account_as_both_assessed_and_remaining(self):
        """The exact contradiction on the screenshot: 25 of 25 assessed, 25 remaining."""
        c = self._salvaged()
        assert c.assessed_commenters == 25
        assert c.estimated_remaining_commenters == 0

    def test_it_says_which_half_is_missing(self):
        c = self._salvaged()
        assert c.incomplete_kind == "summary_not_certified"
        assert "summary" in c.reason.lower()

    def test_it_is_still_not_certified_complete(self):
        """`complete` stays False: the entry as a whole did not pass validation, and the export and
        the operator surfaces both key on that. Only the SENTENCE changes."""
        assert self._salvaged().complete is False

    def test_a_salvaged_run_that_really_did_miss_accounts_still_counts_them(self):
        c = self._salvaged(assessed_commenters=18)
        assert c.missing_commenters == 7
        assert c.estimated_remaining_commenters == 7


class TestATrueFloorIsUnchanged:
    def test_it_still_says_no_reasoning_was_produced(self):
        """The Floor branch is the honest one when there really is no model prose, and it must keep
        firing: the UI relies on it to avoid implying AI coverage that did not happen."""
        c = verify_completion(
            model_backed=False, finish_reason="stop", represented_commenters=25,
            assessed_commenters=0, omitted_input_commenters=0, salvaged_reads=False)
        assert "was not produced" in c.reason.lower()
        assert c.estimated_remaining_commenters == 25
        assert c.complete is False

    def test_salvage_defaults_off(self):
        """Every existing caller keeps the old behaviour without being edited."""
        c = verify_completion(
            model_backed=False, finish_reason="stop", represented_commenters=4,
            assessed_commenters=0, omitted_input_commenters=0)
        assert "deterministic floor" in c.reason.lower()


class TestAHealthyRunIsUnchanged:
    def test_complete_when_every_shown_account_was_assessed(self):
        c = verify_completion(
            model_backed=True, finish_reason="stop", represented_commenters=25,
            assessed_commenters=25, omitted_input_commenters=0)
        assert c.complete is True
        assert c.incomplete_kind is None


class TestTheMergedReasonNeverContradictsTheHeading:
    """Caught in an end-to-end run of a real 100-account investigation.

    `_merge_batch_parts` starts from the FIRST completed batch's payload, so every unstated key is
    inherited from it — including `reason`, which is the sentence a reader actually sees. The run
    came back `complete: false` with `missing_commenters: 2` and the inherited sentence "Complete,
    every commenter in the investigation received AI reasoning", inside a box whose own heading said
    the coverage was partial.
    """

    def _merged(self, parts, total):
        from app.reasoning.analyst import _merge_batch_parts
        return _merge_batch_parts(parts, batch_size=25, done=total, run_finished=True,
                                  run_id="t")["completion"]

    def _part(self, accounts: int, represented: int, complete: bool) -> dict:
        return {
            "commenter_assessments": [{"ref": f"A{i}", "resolved": True} for i in range(accounts)],
            "omi_score": 20,
            "completion": {
                "complete": complete, "represented_commenters": represented,
                "assessed_commenters": accounts,
                "reason": ("Complete — every commenter in the investigation received AI reasoning."
                           if complete else "something else"),
            },
            "investigation_trace": {"model_backed": True},
        }

    def test_every_pass_landed_but_accounts_are_short(self):
        """THE REGRESSION. Four passes, all landed, two accounts never got a read."""
        parts = [self._part(25, 25, True), self._part(24, 25, False),
                 self._part(24, 25, False), self._part(25, 25, True)]
        c = self._merged(parts, 4)
        assert c["complete"] is False
        assert "complete" not in c["reason"].lower() or "did not" in c["reason"].lower()
        assert "2 of 100" in c["reason"], c["reason"]

    def test_an_empty_pass_is_still_named_as_such(self):
        parts = [self._part(25, 25, True), self._part(0, 25, False),
                 self._part(25, 25, True), self._part(25, 25, True)]
        c = self._merged(parts, 4)
        assert "came back empty" in c["reason"], c["reason"]

    def test_a_wholly_clean_run_still_says_complete(self):
        parts = [self._part(25, 25, True) for _ in range(4)]
        c = self._merged(parts, 4)
        assert c["complete"] is True
        assert "Complete" in c["reason"]
