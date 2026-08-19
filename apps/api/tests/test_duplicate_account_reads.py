"""One account, one published verdict.

Observed live on a 100-account scan: the page read "PER-ACCOUNT ASSESSMENTS · 103" beside
"PARTIAL AI COVERAGE · 103 OF 100 COMMENTERS ASSESSED". `assessed_commenters` counts rows that
RESOLVED to a real account, so 103 of 100 never meant three strangers had been invented. It meant
three of the hundred were each written up twice, and both paragraphs rendered.

That is the specific harm this product exists to avoid causing. These are scored claims about named
real people, they get posted publicly, and two independently reached verdicts about one person are
free to disagree about the score, the tier and the evidence. A reader cannot tell which one we stand
behind, and neither can we.

The key is the ACCOUNT, never the alias. `build_alias_legend` numbers A1..An within one package and
every batch builds its own, so A1 means a different person in each of them: deduplicating on the
alias would silently delete three quarters of a four-batch run. The last test here is that one.
"""
from __future__ import annotations

from app.reasoning import analyst as A


class _Legend:
    """The two methods the join uses, over an alias -> author_ref map."""

    def __init__(self, mapping: dict[str, str]):
        self._m = dict(mapping)

    def to_manifest(self) -> dict:
        return {"accounts": dict(self._m)}

    def resolve(self, alias: str) -> str | None:
        return self._m.get(alias)


def _payload(handles: list[str]) -> dict:
    return {"video": {"commenters": [
        {"handle": h, "external_id": f"id_{h}", "overall_probability": 0.5,
         "recent_activity": []} for h in handles
    ]}}


def _legend_for(handles: list[str]) -> _Legend:
    return _Legend({f"A{i + 1}": A._ref(h) for i, h in enumerate(handles)})


def _read(alias: str, score: int = 20, text: str = "An ordinary account.") -> dict:
    return {"ref": alias, "omi_score": score, "suspicion_tier": "low",
            "assessment": text, "confidence": 50}


def _join(handles: list[str], reads: list[dict]) -> list[dict]:
    return A._join_commenter_assessments(
        {"commenter_assessments": reads}, _legend_for(handles), _payload(handles))


# ==================================================================================================
# Inside one batch
# ==================================================================================================
def test_an_account_written_up_twice_is_published_once():
    rows = _join(["alice", "bob"], [_read("A1"), _read("A2"), _read("A1", score=71)])
    assert len(rows) == 2
    assert [r["handle"] for r in rows] == ["alice", "bob"]


def test_the_first_verdict_is_the_one_kept():
    """The output contract asks for the accounts in legend order, so the first mention is the one
    the model wrote in its intended sweep and the later one is the slip."""
    rows = _join(["alice"], [_read("A1", score=20, text="first"),
                             _read("A1", score=90, text="second")])
    assert [r["omi_score"] for r in rows] == [20]
    assert rows[0]["assessment"] == "first"


def test_distinct_accounts_are_never_collapsed():
    rows = _join(["alice", "bob", "carol"], [_read("A1"), _read("A2"), _read("A3")])
    assert [r["handle"] for r in rows] == ["alice", "bob", "carol"]


def test_two_rows_that_resolve_to_nobody_are_kept_apart():
    """"We could not tell who this is" is not evidence that two such rows are the same account."""
    rows = _join(["alice"], [_read("A1"), _read("Z9"), _read("Z8")])
    assert len(rows) == 3
    assert sum(1 for r in rows if not r["resolved"]) == 2


def test_the_same_unresolved_alias_twice_is_still_one_row():
    rows = _join(["alice"], [_read("Z9"), _read("Z9")])
    assert len(rows) == 1


# ==================================================================================================
# Across batches — where the alias key would be catastrophic
# ==================================================================================================
def _part(handles: list[str]) -> dict:
    """A landed batch, joined exactly as the real path joins it."""
    reads = [_read(f"A{i + 1}") for i in range(len(handles))]
    return {"commenter_assessments": _join(handles, reads), "omi_score": 30,
            "completion": {"represented_commenters": len(handles),
                           "assessed_commenters": len(handles), "complete": True}}


def test_every_batch_reuses_A1_and_the_merge_must_not_collapse_them():
    """The regression that a naive fix introduces. Each batch's legend restarts at A1, so four
    batches of 25 all carry A1..A25 for four different sets of people."""
    parts = [_part(["alice", "bob"]), _part(["carol", "dave"])]
    assert all(p["commenter_assessments"][0]["ref"] == "A1" for p in parts)
    merged = A._merge_batch_parts(parts, batch_size=2, done=2, run_finished=True)
    assert [r["handle"] for r in merged["commenter_assessments"]] == [
        "alice", "bob", "carol", "dave"]


def test_one_account_dealt_into_two_batches_is_published_once():
    """A selection carrying the same account twice gets it chunked into two separate requests. The
    customer is charged for it once and must be told about it once."""
    merged = A._merge_batch_parts([_part(["alice", "bob"]), _part(["alice", "carol"])],
                                  batch_size=2, done=2, run_finished=True)
    handles = [r["handle"] for r in merged["commenter_assessments"]]
    assert handles == ["alice", "bob", "carol"]


def test_the_coverage_count_matches_what_is_actually_on_the_page():
    """The bug as the user saw it: a box claiming coverage for paragraphs that are not rendered.

    Each batch computes its own `assessed_commenters` before the merge exists, so summing those
    counts a cross-batch duplicate that the merge then drops.
    """
    merged = A._merge_batch_parts([_part(["alice", "bob"]), _part(["alice", "carol"])],
                                  batch_size=2, done=2, run_finished=True)
    served = len(merged["commenter_assessments"])
    assert merged["completion"]["assessed_commenters"] == served == 3
