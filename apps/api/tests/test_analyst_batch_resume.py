"""An interrupted run must CONTINUE, not start over.

Reported live: a scan finished 2 of 4 batches, stopped, and the elapsed clock kept running. The run
had died mid-flight — a redeploy (`background.shutdown` cancels in-flight work after a 5s grace), a
container restart, an OOM — and nothing could pick it up where it left off.

`parts` was a local `[None] * total`, so the route's interrupted-run branch resubmitted the whole
generation and batches 1 and 2 were re-sent to OpenRouter to produce answers already in the database.
The customer paid twice and waited through work that was finished.

The product behaviour these tests protect, stated the way it should read: one bundle of 25 accounts
goes to the model, its response is persisted so the UI can show it, and only then does the next
bundle start — through to the last batch, across an interruption if there is one.
"""
from __future__ import annotations

import pytest

from app.reasoning import analyst as A


def _chunk(ids: list[str]) -> dict:
    return {"video": {"commenters": [{"external_id": i} for i in ids]}}


def _part(n: int, tag: str = "x") -> dict:
    return {
        "commenter_assessments": [
            {"ref": f"A{i}", "resolved": True, "omi_score": 10, "assessment": tag} for i in range(n)
        ],
        "omi_score": 30,
    }


class _Inv:
    """The two attributes the checkpoint helpers touch."""
    def __init__(self, payload=None, slug="inv_test"):
        self.payload_json = payload or {}
        self.slug = slug


class _Session:
    """`begin_nested` is a context manager and `add` is a no-op; nothing else is used."""
    def begin_nested(self):
        class _Ctx:
            def __enter__(self_inner): return self_inner
            def __exit__(self_inner, *a): return False
        return _Ctx()

    def add(self, _obj): pass


@pytest.fixture()
def sess():
    return _Session()


class TestTheCheckpointRoundTrips:
    def test_a_saved_batch_comes_back(self, sess):
        chunks = [_chunk(["a", "b"]), _chunk(["c", "d"])]
        sig = A._chunk_signature(chunks)
        inv = _Inv()
        A._save_batch_part(sess, inv, sig, 2, 0, _part(2))
        loaded = A._load_batch_parts(inv, sig, 2)
        assert set(loaded) == {0}
        assert len(loaded[0]["commenter_assessments"]) == 2

    def test_it_is_cleared_when_the_run_ends(self, sess):
        chunks = [_chunk(["a"]), _chunk(["b"])]
        sig = A._chunk_signature(chunks)
        inv = _Inv()
        A._save_batch_part(sess, inv, sig, 2, 0, _part(1))
        assert A.BATCH_PARTS_KEY in inv.payload_json
        A._clear_batch_parts(sess, inv)
        assert A.BATCH_PARTS_KEY not in inv.payload_json
        assert A._load_batch_parts(inv, sig, 2) == {}

    def test_clearing_leaves_the_rest_of_the_payload_alone(self, sess):
        inv = _Inv({"video": {"commenters": [1, 2, 3]}, A.CACHE_KEY: {"assessment": {}}})
        A._save_batch_part(sess, inv, "sig", 1, 0, _part(1))
        A._clear_batch_parts(sess, inv)
        assert inv.payload_json["video"] == {"commenters": [1, 2, 3]}
        assert A.CACHE_KEY in inv.payload_json


class TestAResumeIsRefusedWhenTheWorkChanged:
    """THE DANGEROUS CASE. A batch-3 result stapled onto a run whose batch 3 holds DIFFERENT accounts
    would publish real model prose against the wrong handles, which is the single worst thing this
    product can do. The signature is what makes that impossible."""

    def test_a_different_selection_is_not_resumed(self, sess):
        old = [_chunk(["a", "b"]), _chunk(["c", "d"])]
        new = [_chunk(["a", "b"]), _chunk(["e", "f"])]
        inv = _Inv()
        A._save_batch_part(sess, inv, A._chunk_signature(old), 2, 0, _part(2))
        assert A._load_batch_parts(inv, A._chunk_signature(new), 2) == {}

    def test_a_reordered_selection_is_not_resumed(self, sess):
        old = [_chunk(["a", "b"])]
        new = [_chunk(["b", "a"])]
        inv = _Inv()
        A._save_batch_part(sess, inv, A._chunk_signature(old), 1, 0, _part(2))
        assert A._load_batch_parts(inv, A._chunk_signature(new), 1) == {}

    def test_a_different_batch_count_is_not_resumed(self, sess):
        chunks = [_chunk(["a"]), _chunk(["b"])]
        sig = A._chunk_signature(chunks)
        inv = _Inv()
        A._save_batch_part(sess, inv, sig, 2, 0, _part(1))
        assert A._load_batch_parts(inv, sig, 4) == {}

    def test_the_signature_is_stable_for_the_same_layout(self):
        a = [_chunk(["a", "b"]), _chunk(["c"])]
        b = [_chunk(["a", "b"]), _chunk(["c"])]
        assert A._chunk_signature(a) == A._chunk_signature(b)

    def test_the_same_accounts_split_differently_are_a_different_layout(self):
        """25/25 and 50 cover the same accounts and are not the same work."""
        one = [_chunk(["a", "b", "c", "d"])]
        two = [_chunk(["a", "b"]), _chunk(["c", "d"])]
        assert A._chunk_signature(one) != A._chunk_signature(two)


class TestAFlooredBatchIsNotResumedAsDone:
    def test_an_empty_part_is_re_run(self, sess):
        """Resuming a floored batch would make an interruption permanently lose whichever batch it
        happened to interrupt. Re-running it is the retry the customer is owed."""
        chunks = [_chunk(["a"]), _chunk(["b"])]
        sig = A._chunk_signature(chunks)
        inv = _Inv()
        A._save_batch_part(sess, inv, sig, 2, 0, {"commenter_assessments": []})
        assert A._load_batch_parts(inv, sig, 2) == {}


class TestTheCheckpointNeverReachesAPublicResponse:
    def test_the_public_json_export_strips_it(self):
        """It holds the RAW per-batch assessments: exactly what the viewer gate filters, one batch at
        a time, on a route with no authentication at all."""
        from app.routes.reports import _public_payload

        out = _public_payload({
            "video": {"commenters": []},
            A.CACHE_KEY: {"assessment": {"commenter_assessments": [{"signals": "admin only"}]}},
            A.BATCH_PARTS_KEY: {"parts": {"0": _part(3)}},
        })
        assert set(out) == {"video"}
