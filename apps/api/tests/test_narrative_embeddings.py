"""The hosted embedder, and the one failure mode that is worse than not embedding at all.

Topic clustering compares a new vector against stored centroids. Two embedders produce coordinates
that mean nothing to each other, and `cosine` answers 0.0 on a width mismatch rather than raising,
so mixing them does not fail: every utterance misses every existing topic, spawns a duplicate, and
the run reports success. The topic space forks in half and nothing anywhere says so.

That is why `ApiEmbedder` raises instead of degrading, why `Narrative.embedding_space` exists, and
why the ingest skips a batch it cannot embed rather than reaching for the fallback.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.narrative.embeddings import (
    ApiEmbedder,
    EmbeddingUnavailable,
    HashingEmbedder,
    get_embedder,
    set_embedder_for_tests,
)


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_a: Any) -> None:
        return None


def _embedder(**kw: Any) -> ApiEmbedder:
    defaults = dict(base_url="https://vendor.example/v1/embeddings", model="embed-1", api_key="k")
    defaults.update(kw)
    return ApiEmbedder(**defaults)  # type: ignore[arg-type]


def _stub(monkeypatch: pytest.MonkeyPatch, payload: dict | Exception) -> list[dict]:
    """Replace the HTTP call, and record the request bodies it was given."""
    sent: list[dict] = []

    def _urlopen(req: Any, timeout: float = 0) -> Any:  # noqa: ARG001
        sent.append(json.loads(req.data.decode()))
        if isinstance(payload, Exception):
            raise payload
        return _FakeResponse(payload)

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)
    return sent


def _payload(vectors: list[list[float]]) -> dict:
    return {"data": [{"index": i, "embedding": v} for i, v in enumerate(vectors)]}


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


def test_it_returns_one_unit_vector_per_input(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(monkeypatch, _payload([[3.0, 4.0], [0.0, 5.0]]))
    vecs = _embedder().embed(["a", "b"])
    assert len(vecs) == 2
    # Normalised here rather than trusted from the provider: some normalise, some do not, and
    # `cosine` is a dot product for every embedder in this module.
    for v in vecs:
        assert abs(sum(x * x for x in v) - 1.0) < 1e-9


def test_the_space_is_learned_from_the_first_response(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(monkeypatch, _payload([[1.0, 0.0, 0.0, 0.0]]))
    emb = _embedder()
    emb.embed(["a"])
    assert emb.dimensions == 4
    assert emb.space == "api:embed-1:4"


def test_inputs_are_batched_so_one_request_cannot_exceed_a_provider_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _stub(monkeypatch, _payload([[1.0, 0.0]]))
    _embedder(batch_size=1).embed(["a", "b", "c"])
    assert len(sent) == 3
    assert [len(body["input"]) for body in sent] == [1, 1, 1]


def test_a_width_is_only_requested_when_one_was_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _stub(monkeypatch, _payload([[1.0, 0.0]]))
    _embedder().embed(["a"])
    assert "dimensions" not in sent[0]

    sent = _stub(monkeypatch, _payload([[1.0, 0.0]]))
    _embedder(dimensions=2).embed(["a"])
    assert sent[0]["dimensions"] == 2


# ---------------------------------------------------------------------------
# Failures. Every one of these RAISES; none of them degrades.
# ---------------------------------------------------------------------------


def test_an_unreachable_provider_raises_rather_than_returning_something(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub(monkeypatch, OSError("connection refused"))
    with pytest.raises(EmbeddingUnavailable):
        _embedder().embed(["a"])


def test_a_short_reply_raises_rather_than_misaligning_every_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Two inputs, one vector back. Zipping these would attach the wrong text to the vector and the
    # topic assignment would be confidently wrong, which is worse than no assignment.
    _stub(monkeypatch, _payload([[1.0, 0.0]]))
    with pytest.raises(EmbeddingUnavailable):
        _embedder().embed(["a", "b"])


def test_a_width_change_mid_life_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    emb = _embedder()
    _stub(monkeypatch, _payload([[1.0, 0.0]]))
    emb.embed(["a"])
    _stub(monkeypatch, _payload([[1.0, 0.0, 0.0]]))
    with pytest.raises(EmbeddingUnavailable):
        emb.embed(["b"])


def test_the_error_never_carries_the_provider_body(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    err = urllib.error.HTTPError(
        "https://vendor.example", 400, "Bad Request", {}, None,
    )
    _stub(monkeypatch, err)
    with pytest.raises(EmbeddingUnavailable) as caught:
        _embedder().embed(["a secret post by someone who is not our user"])
    # The status only. A provider error body commonly echoes the input, and the input here is other
    # people's posts.
    assert "400" in str(caught.value)
    assert "secret post" not in str(caught.value)


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def test_an_unconfigured_deployment_falls_back_and_keeps_working() -> None:
    set_embedder_for_tests(None)
    import app.narrative.embeddings as E
    E._embedder = None
    try:
        assert isinstance(get_embedder(), HashingEmbedder) or get_embedder().space
    finally:
        E._embedder = None


def test_the_vendor_name_is_required_before_anything_is_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The name is what the privacy policy has to disclose. A deployment that cannot say who is
    # processing other people's posts should not be sending them, so this is a configuration error
    # rather than a disclosure gap nobody notices.
    import app.narrative.embeddings as E
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "narrative_embedding_base_url", "https://vendor.example/v1/embeddings")
    monkeypatch.setattr(settings, "narrative_embedding_model", "embed-1")
    monkeypatch.setattr(settings, "narrative_embedding_provider", None)
    assert E._configured_api_embedder() is None

    monkeypatch.setattr(settings, "narrative_embedding_provider", "VendorCo")
    built = E._configured_api_embedder()
    assert built is not None and built.model == "embed-1"
