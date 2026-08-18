"""The analyst's output budget is 50,000 tokens, and asking for it must not be able to kill the app.

WHY 50k. Batches are a fixed 25 accounts, so the linear formula asks for base + 450x25 = 23,250, and
a live run was observed spending 12,970 of that. Truncation here is not a graceful degradation: the
reply fails schema validation, the wrapper floors, and before the salvage path it took every
per-account read in the batch with it. The floor is the margin.

WHY THIS FILE EXISTS. `max_tokens` is a cap, not a spend — OpenRouter bills tokens generated — so the
increase costs nothing on a run that finishes early. What it risks is the served model refusing a cap
above its own ceiling. That is a 4xx, `http_error` is deliberately NOT retryable, and the result
would be every scan on the deployment flooring, permanently, until a human noticed. The model is
named by an env var and resolved by the gateway, so nothing in this codebase can check the number
against the model. The rejection is recognised instead, and retried downward.
"""
from __future__ import annotations

import app.reasoning.floor_reason as F
from app.reasoning.completion import completion_budget


class TestTheBudgetIsFiftyThousand:
    def test_a_full_batch_asks_for_50k(self):
        assert completion_budget(25) == 50_000

    def test_the_remainder_batch_asks_for_the_same(self):
        """The floor governs every batch size the product can produce today, so a 17-account
        remainder is not quietly given a third less room than the 25s beside it."""
        assert completion_budget(17) == 50_000
        assert completion_budget(1) == 50_000

    def test_the_formula_still_takes_over_above_the_floor(self):
        """The floor is a floor, not a fixed value: a hypothetical single request larger than ~84
        accounts still scales, and the ceiling still caps it."""
        assert completion_budget(100) == 12_000 + 450 * 100
        assert completion_budget(10_000) == 150_000


class TestAnOverLargeAskIsSurvivable:
    def test_a_rejection_naming_the_token_limit_is_classified(self):
        for msg in (
            "max_tokens is too large: 50000",
            "This model supports at most 32768 max_completion_tokens",
            "requested max_output_tokens exceeds the maximum for this model",
        ):
            assert F.classify_floor(
                {"response_status": 400, "endpoint_error": msg}
            ) == F.OUTPUT_BUDGET_TOO_LARGE, msg

    def test_it_is_retried_downward(self):
        assert F.is_retryable(F.OUTPUT_BUDGET_TOO_LARGE) is True
        assert F.budget_multiplier_for(F.OUTPUT_BUDGET_TOO_LARGE) == 0.5

    def test_truncation_is_still_retried_upward(self):
        """The two budget faults pull in opposite directions and must not be collapsed."""
        assert F.budget_multiplier_for(F.TRUNCATED_OUTPUT) == 1.5

    def test_everything_else_retries_at_the_same_budget(self):
        assert F.budget_multiplier_for(F.RATE_LIMITED) == 1.0
        assert F.budget_multiplier_for(None) == 1.0

    def test_an_ordinary_4xx_is_still_not_retryable(self):
        """THE CARVE-OUT MUST STAY NARROW. `http_error` is excluded from retry precisely because a
        4xx means the request was wrong and the next one would be wrong the same way; widening the
        hints would make ordinary bad requests billable twice."""
        r = F.classify_floor({"response_status": 400, "endpoint_error": "bad request"})
        assert r.startswith(F.HTTP_ERROR)
        assert F.is_retryable(r) is False

    def test_a_401_is_still_a_dead_credential_not_a_budget_fault(self):
        """Status is checked before the error string, so a credential fault cannot be mistaken for
        something a retry fixes just because the body mentions tokens."""
        assert F.classify_floor(
            {"response_status": 401, "endpoint_error": "invalid key, max_tokens ignored"}
        ) == F.BAD_API_KEY

    def test_the_new_reason_is_declared(self):
        assert F.OUTPUT_BUDGET_TOO_LARGE in F.ALL_REASONS
