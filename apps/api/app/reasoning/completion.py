"""Full-investigation completion budgeting + verification (Phase 5H).

OmiSphere optimizes for investigation QUALITY, not API cost: the AI reasons over the COMPLETE
investigation — every commenter is eligible for reasoning, none silently sampled or omitted. Two
mechanisms make that reliable on a single inference:

1. **Dynamic completion budget** — the output-token ceiling is sized from the investigation (how many
   commenters must each receive a concise per-account assessment), not a fixed number. Small
   investigations request little; a ~150-commenter investigation requests enough to finish. The formula
   scales linearly, so 300 / 500 / 1000 commenters need only a higher ``ceiling`` — never a redesign.

2. **Completion verification** — after the model responds, we determine explicitly whether the
   investigation actually finished: did generation stop normally (vs hit the token ceiling), did every
   represented commenter receive an assessment, was any INPUT evidence omitted upstream. The result is
   explicit completion metadata persisted on the assessment and surfaced in the UI. Nothing is ever
   silently truncated — an incomplete investigation is MARKED incomplete, with the reason and the
   estimated remaining work, leaving room for a future continuation pass.

Neither mechanism touches the deterministic engine, the echoed numbers, the Governor, or the canonical
schema — they govern only how much the model is asked to produce and how completeness is reported.
"""
from __future__ import annotations

from dataclasses import dataclass

# --- dynamic completion budget knobs (output tokens) --------------------------------------------- #
# Base covers the executive synthesis wrapper + the six domain reasoning sections + limits — the parts
# that do NOT grow with commenter count. Per-commenter covers ONE concise, information-dense per-account
# assessment object (ref + a short probabilistic assessment + a few citations, with JSON overhead). The
# ceiling is the hard upper bound for a single inference; raising it (config) is the ONLY change needed to
# support larger investigations — the formula itself never changes.
COMPLETION_BASE_TOKENS = 3000
COMPLETION_PER_COMMENTER_TOKENS = 160
COMPLETION_FLOOR_TOKENS = 4000          # even a 0-commenter investigation needs the full synthesis
COMPLETION_CEILING_TOKENS = 100000      # ~ (100000-3000)/160 ≈ 606 commenters before the ceiling binds.
# NOTE (2026-07-18): raised 40000 → 100000 deliberately, to observe REAL per-investigation output cost on
# live runs before tuning down. It is a CEILING, not a reservation — billing is on tokens actually
# generated, so a large investigation that finishes early still costs only what it produced. Lower this
# once real cost data is in.


def completion_budget(
    num_commenters: int,
    *,
    base: int = COMPLETION_BASE_TOKENS,
    per_commenter: int = COMPLETION_PER_COMMENTER_TOKENS,
    floor: int = COMPLETION_FLOOR_TOKENS,
    ceiling: int = COMPLETION_CEILING_TOKENS,
) -> int:
    """Output-token budget for an investigation with ``num_commenters`` accounts to assess. Linear in the
    commenter count, clamped to ``[floor, ceiling]`` — enough to finish without excessive unused budget on
    small investigations. Deterministic and pure."""
    n = max(0, int(num_commenters or 0))
    want = base + per_commenter * n
    return max(floor, min(ceiling, want))


def commenter_capacity(
    *,
    base: int = COMPLETION_BASE_TOKENS,
    per_commenter: int = COMPLETION_PER_COMMENTER_TOKENS,
    ceiling: int = COMPLETION_CEILING_TOKENS,
) -> int:
    """How many commenters a single inference can finish before the completion ceiling binds — the point
    beyond which a future continuation pass (not yet implemented) would be required."""
    return max(0, (ceiling - base) // max(1, per_commenter))


# --- completion verification --------------------------------------------------------------------- #
@dataclass(frozen=True)
class CompletionStatus:
    """Explicit completeness verdict for one investigation's AI reasoning. Persisted + surfaced so the
    user always knows whether the investigation is complete."""

    complete: bool
    finish_reason: str | None            # OpenRouter finish_reason: "stop" (normal) | "length" (ceiling) | ...
    stopped_on_token_limit: bool         # generation stopped because it hit the output ceiling
    json_complete: bool                  # structured JSON was received AND not truncated mid-generation
    schema_valid: bool                   # the model output passed canonical-schema validation
    governor_valid: bool                 # the model output passed the Governor
    represented_commenters: int          # accounts the model was SHOWN (eligible for reasoning) = expected
    assessed_commenters: int             # accounts the model actually assessed = returned
    missing_commenters: int              # shown but not assessed
    omitted_input_commenters: int        # accounts NOT shown to the model (upstream evidence budget)
    max_output_tokens: int | None        # the dynamic completion budget requested for this inference
    output_tokens: int | None            # actual completion size the gateway reported
    incomplete_kind: str | None          # None | "truncated_output" | "missing_assessments" | "omitted_input"
    reason: str
    estimated_remaining_commenters: int  # remaining work for a future continuation pass

    def to_dict(self) -> dict:
        return {
            "complete": self.complete,
            "finish_reason": self.finish_reason,
            "stopped_on_token_limit": self.stopped_on_token_limit,
            "json_complete": self.json_complete,
            "schema_valid": self.schema_valid,
            "governor_valid": self.governor_valid,
            "represented_commenters": self.represented_commenters,
            "assessed_commenters": self.assessed_commenters,
            "missing_commenters": self.missing_commenters,
            "omitted_input_commenters": self.omitted_input_commenters,
            "max_output_tokens": self.max_output_tokens,
            "output_tokens": self.output_tokens,
            "incomplete_kind": self.incomplete_kind,
            "reason": self.reason,
            "estimated_remaining_commenters": self.estimated_remaining_commenters,
        }


def verify_completion(
    *,
    model_backed: bool,
    finish_reason: str | None,
    represented_commenters: int,
    assessed_commenters: int,
    omitted_input_commenters: int,
    max_output_tokens: int | None = None,
    output_tokens: int | None = None,
    json_received: bool = True,
    schema_valid: bool = True,
    governor_valid: bool = True,
) -> CompletionStatus:
    """Decide whether the AI reasoning covered the COMPLETE investigation, and if not, why + how much
    remains. Precedence of incompleteness (most actionable first):

    * ``truncated_output`` — generation hit the token ceiling (``finish_reason == "length"``): the
      investigation over-ran a single inference. Estimated remaining = shown-but-unassessed.
    * ``missing_assessments`` — generation stopped normally but some shown commenters got no assessment.
    * ``omitted_input`` — the upstream evidence budget did not show every commenter to the model.

    When the model was not reached (Floor), completeness is not applicable — reported as incomplete with a
    clear reason so the UI never implies AI coverage that did not happen."""
    represented = max(0, int(represented_commenters or 0))
    assessed = max(0, int(assessed_commenters or 0))
    omitted_input = max(0, int(omitted_input_commenters or 0))
    missing = max(0, represented - assessed)
    truncated = (finish_reason or "").lower() == "length"
    json_complete = bool(json_received) and not truncated

    if not model_backed:
        return CompletionStatus(
            complete=False, finish_reason=finish_reason, stopped_on_token_limit=truncated,
            json_complete=json_complete, schema_valid=bool(schema_valid),
            governor_valid=bool(governor_valid), represented_commenters=represented,
            assessed_commenters=assessed, missing_commenters=missing,
            omitted_input_commenters=omitted_input, max_output_tokens=max_output_tokens,
            output_tokens=output_tokens, incomplete_kind=None,
            reason="AI reasoning was not produced (deterministic Floor); completeness not applicable.",
            estimated_remaining_commenters=represented + omitted_input,
        )

    if truncated:
        kind, reason = "truncated_output", (
            "Generation reached the output-token ceiling before finishing; the investigation exceeded a "
            "single inference. No commenters were dropped silently — the unassessed accounts are recorded."
        )
        remaining = missing if missing else omitted_input
    elif missing:
        kind, reason = "missing_assessments", (
            f"{missing} of {represented} shown commenters did not receive an AI assessment in this response."
        )
        remaining = missing
    elif omitted_input:
        kind, reason = "omitted_input", (
            f"{omitted_input} commenter(s) were not shown to the model by the upstream evidence budget; "
            "they remain citable but did not receive a per-account assessment."
        )
        remaining = omitted_input
    else:
        kind, reason, remaining = None, "Complete — every commenter in the investigation received AI reasoning.", 0

    # Complete requires: no coverage gap AND the output certified valid + intact. schema_valid /
    # governor_valid are True by construction on the model-backed path (the output had to pass both to
    # be model-backed), recorded here explicitly for certification.
    complete = (kind is None) and bool(schema_valid) and bool(governor_valid) and json_complete
    if kind is None and not complete:
        reason = "Model output did not fully certify (schema / Governor / JSON completeness)."
    return CompletionStatus(
        complete=complete, finish_reason=finish_reason, stopped_on_token_limit=truncated,
        json_complete=json_complete, schema_valid=bool(schema_valid), governor_valid=bool(governor_valid),
        represented_commenters=represented, assessed_commenters=assessed, missing_commenters=missing,
        omitted_input_commenters=omitted_input, max_output_tokens=max_output_tokens,
        output_tokens=output_tokens, incomplete_kind=kind, reason=reason,
        estimated_remaining_commenters=remaining,
    )


__all__ = [
    "COMPLETION_BASE_TOKENS", "COMPLETION_PER_COMMENTER_TOKENS", "COMPLETION_FLOOR_TOKENS",
    "COMPLETION_CEILING_TOKENS", "completion_budget", "commenter_capacity",
    "CompletionStatus", "verify_completion",
]
