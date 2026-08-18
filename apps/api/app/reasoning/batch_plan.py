"""How an investigation is divided into model requests, and what state each one is in.

THE PURE CORE OF A BATCHED RUN. No I/O, no model, no database, no settings: give it a number of
accounts and a list of outcomes and it tells you the shape of the run. Everything that decides what
a customer sees about progress is derived here, in one place, from one record.

WHY THIS EXISTS AS ITS OWN MODULE. The previous design stored three separate numbers on the
assessment and had every reader work out what they meant:

* ``done``          batches ATTEMPTED, so it advances when one fails
* ``landed``        batches that produced accounts
* ``model_backed``  whether the prose in the entry is the model's

They look interchangeable and they are not, and almost every progress bug shipped this year was one
of them being read as another: a strip that said "3 of 4 done" beside 25 accounts, a coverage notice
that could never fire because a floored batch counted as landed, and a completion counter that ran
backwards. Here there is ONE record, a list of per-batch outcomes, and every number a caller wants is
a function of it. A derived count cannot drift from the thing it counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

#: Accounts per OpenRouter request.
#:
#: A SIZE, not a count. The size is what bounds the request, and the request is what fails: measured
#: on this deployment, 25 accounts per call succeeds and roughly 50 comes back empty within about
#: thirty seconds. Dividing a selection into a fixed NUMBER of batches instead made the size grow
#: with the selection, so a 197-account scan became four calls of ~50 and every one of them failed.
#: With a fixed size, a bigger scan is more requests, never a bigger request.
BATCH_SIZE = 25

BatchState = Literal["pending", "running", "done", "failed"]


def plan_batches(total_accounts: int, size: int = BATCH_SIZE) -> list[tuple[int, int]]:
    """Half-open ``(start, end)`` slices over the selection, in order.

    Fixed size, remainder last: 100 accounts is 4 x 25, 200 is 8 x 25, and 92 is 25/25/25/17. The
    remainder gets its own request rather than being spread, because spreading it would change the
    size of every batch to avoid a short one, and a short final request is not a problem worth
    paying for.
    """
    n = max(0, int(total_accounts))
    step = max(1, int(size))
    return [(i, min(i + step, n)) for i in range(0, n, step)]


@dataclass
class BatchOutcome:
    """What happened to one request. ``accounts`` is how many reads it actually produced."""

    index: int
    planned: int
    state: BatchState = "pending"
    accounts: int = 0
    attempts: int = 0
    reason: str | None = None            # floor_reason for a failure, None otherwise

    @property
    def landed(self) -> bool:
        """Produced at least one account. A batch that returned a Floor object produced nothing."""
        return self.state == "done" and self.accounts > 0


@dataclass
class RunPlan:
    """The whole run: every batch, in order, with its current state.

    This is the single source of truth a caller persists and the UI renders. Nothing else needs to
    be stored about progress, because every question anyone asks is answered below.
    """

    run_id: str
    batch_size: int = BATCH_SIZE
    batches: list[BatchOutcome] = field(default_factory=list)

    # ---- the derived counts. Never stored, so they can never disagree with the batches. ----
    @property
    def total(self) -> int:
        return len(self.batches)

    @property
    def attempted(self) -> int:
        """Batches whose request has returned, successfully or not. This is what a progress readout
        moves on, so a run containing a failure still visibly advances instead of looking hung."""
        return sum(1 for b in self.batches if b.state in ("done", "failed"))

    @property
    def landed(self) -> int:
        """Batches that produced accounts. This is COVERAGE, and it is the number a customer is
        owed: 'four of four were tried' and 'four of four worked' are different claims."""
        return sum(1 for b in self.batches if b.landed)

    @property
    def failed(self) -> int:
        return sum(1 for b in self.batches if b.state == "failed" or
                   (b.state == "done" and b.accounts == 0))

    @property
    def accounts_scored(self) -> int:
        return sum(b.accounts for b in self.batches)

    @property
    def complete(self) -> bool:
        """The RUN IS OVER, which is not the same as every batch having succeeded. A caller that
        conflates the two resubmits a full billable regeneration forever."""
        return all(b.state in ("done", "failed") for b in self.batches) and bool(self.batches)

    @property
    def running_index(self) -> int | None:
        for b in self.batches:
            if b.state == "running":
                return b.index
        return None

    def states(self) -> list[BatchState]:
        """Per-batch state for the progress track. A batch that returned an object carrying no
        accounts is 'failed': it was tried and it produced nothing, which is what the reader needs
        to know. Rendering it as a quieter kind of success is how a run that lost three quarters of
        its work came to report full coverage."""
        return ["failed" if (b.state == "done" and b.accounts == 0) else b.state
                for b in self.batches]

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "batch_size": self.batch_size,
            "total": self.total,
            "attempted": self.attempted,
            "landed": self.landed,
            "accounts_scored": self.accounts_scored,
            "complete": self.complete,
            "batches": [
                {"index": b.index, "planned": b.planned, "state": s,
                 "accounts": b.accounts, "attempts": b.attempts, "reason": b.reason}
                for b, s in zip(self.batches, self.states())
            ],
        }


def plan_run(run_id: str, total_accounts: int, size: int = BATCH_SIZE) -> RunPlan:
    """A fresh run over ``total_accounts``, every batch pending."""
    slices = plan_batches(total_accounts, size)
    return RunPlan(
        run_id=run_id, batch_size=max(1, int(size)),
        batches=[BatchOutcome(index=i, planned=end - start)
                 for i, (start, end) in enumerate(slices)],
    )


__all__ = ["BATCH_SIZE", "BatchState", "BatchOutcome", "RunPlan", "plan_batches", "plan_run"]
