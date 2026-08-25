"""The JSON error envelope, and the two properties that make it worth having.

An agent that receives a failure has to answer two questions: what kind of failure is this, and
what do I do now. FastAPI's default ``{"detail": "..."}`` answers neither in a machine-readable
way, so both answers had to come from parsing an English sentence written for a person.

The tests that matter here are the ones asserting the envelope reaches paths NOBODY registers a
handler for by hand: the router's own 404, and request validation. Those are the first two failures
an agent probing the API hits.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import (
    DOCS_URL,
    CodedHTTPException,
    error_body,
    install_error_handlers,
)


class _Body(BaseModel):
    handle: str
    count: int


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/boom")
    def boom():
        from fastapi import HTTPException
        raise HTTPException(status_code=402, detail="Not enough credits.")

    @app.get("/specific")
    def specific():
        raise CodedHTTPException(
            402, "This needs the Research plan.",
            code="plan_required", hint="Upgrade at /pricing, then retry.",
        )

    @app.get("/limited")
    def limited():
        from fastapi import HTTPException
        raise HTTPException(429, "Slow down.", headers={"Retry-After": "30"})

    @app.post("/echo")
    def echo(body: _Body):
        return {"ok": body.handle}

    return TestClient(app)


def test_the_unmatched_route_404_carries_the_envelope(client: TestClient) -> None:
    # The router raises Starlette's HTTPException, not FastAPI's. Registering only the FastAPI class
    # leaves exactly this response bare, and it is the first one an agent hits.
    res = client.get("/nothing-here")
    assert res.status_code == 404
    error = res.json()["error"]
    assert error["code"] == "not_found"
    assert error["status"] == 404
    assert error["hint"]
    assert error["docs"] == DOCS_URL


def test_detail_survives_untouched_for_every_existing_client(client: TestClient) -> None:
    # The web app reads `detail` in a dozen places. The envelope is added BESIDE it, never instead.
    res = client.get("/boom")
    assert res.json()["detail"] == "Not enough credits."
    assert res.json()["error"]["message"] == "Not enough credits."


def test_a_route_can_name_a_code_the_status_cannot_express(client: TestClient) -> None:
    # 402 covers both "out of credits" and "wrong plan". Same status, different recoveries, and a
    # client should not have to pattern-match English to tell them apart.
    generic = client.get("/boom").json()["error"]
    specific = client.get("/specific").json()["error"]
    assert generic["code"] == "payment_required"
    assert specific["code"] == "plan_required"
    assert specific["hint"] == "Upgrade at /pricing, then retry."


def test_retry_after_survives_the_handler(client: TestClient) -> None:
    # The 429 hint tells the client to read Retry-After. A handler that dropped the header would
    # make the hint a lie.
    res = client.get("/limited")
    assert res.status_code == 429
    assert res.headers["retry-after"] == "30"
    assert res.json()["error"]["code"] == "rate_limited"


def test_validation_names_every_field_that_was_wrong(client: TestClient) -> None:
    res = client.post("/echo", json={"count": "not-a-number"})
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "validation_failed"
    named = {f["field"] for f in error["fields"]}
    assert named == {"handle", "count"}
    for field in error["fields"]:
        assert field["problem"]
    # The message is readable on its own, so a log line is useful without parsing the JSON.
    assert "handle" in error["message"] and "count" in error["message"]


def test_every_documented_status_has_a_code_and_a_recovery_hint() -> None:
    # A hint that restates the status ("you were rate limited") is worthless; it has to name the
    # recovery. Length is the only mechanical proxy for that, so it is a floor, not the test.
    for status_code in (400, 401, 402, 403, 404, 409, 413, 422, 429, 500, 502, 503):
        error = error_body(status_code, "x")["error"]
        assert error["code"] and error["code"] != "error", status_code
        assert len(error["hint"]) > 20, status_code
        assert error["docs"] == DOCS_URL


def test_an_unmapped_status_still_produces_a_usable_envelope() -> None:
    error = error_body(418, "I am a teapot")["error"]
    assert error["code"] == "error"
    assert error["status"] == 418
    assert error["hint"]


def test_a_non_string_detail_is_rendered_rather_than_crashing_the_handler() -> None:
    # Some routes raise with a dict detail. An error handler that raises while reporting an error is
    # the worst possible failure mode.
    body = error_body(400, {"why": "malformed"})
    assert isinstance(body["error"]["message"], str)
    assert body["detail"] == {"why": "malformed"}
