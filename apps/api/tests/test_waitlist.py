"""The waitlist, and the launch email it exists to send.

A pre-launch campaign drives somebody to this form ONCE. Everything here is about that being enough:
the join cannot fail in a way that loses them, and the launch email cannot be sent twice.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.main import app
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import WaitlistEntry

ADMIN = "boss@omi.test"


@pytest.fixture
def tc(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_SUPER_ADMIN_EMAILS", ADMIN)
    monkeypatch.delenv("OMI_LOCKDOWN", raising=False)
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    from app.core.rate_limit import reset_all_limiters_for_tests

    reset_all_limiters_for_tests()
    with TestClient(app) as c:
        yield c
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def _as_admin(c: TestClient) -> None:
    c.post("/v1/auth/signup", json={"email": ADMIN, "password": "password12345"})


# --------------------------------------------------------------------------------------------- #
# Joining
# --------------------------------------------------------------------------------------------- #
def test_the_address_is_normalised_so_one_person_is_one_row(tc):
    """Foo@Bar.com and foo@bar.com are the same human, and the launch blast must mail them once."""
    assert tc.post("/v1/waitlist", json={"email": "  Foo@Bar.COM "}).status_code == 200
    assert tc.post("/v1/waitlist", json={"email": "foo@bar.com"}).status_code == 200
    with get_session() as s:
        rows = [r.email for r in s.execute(select(WaitlistEntry)).scalars()]
    assert rows == ["foo@bar.com"]


def test_joining_twice_is_a_success_not_an_error(tc):
    """Telling somebody "you are already on the list" as an ERROR reads as rejection at the exact
    moment you want them to feel welcomed, and the response is identical either way so the endpoint
    cannot be used to check whether a particular person signed up."""
    first = tc.post("/v1/waitlist", json={"email": "dup@t.test"})
    second = tc.post("/v1/waitlist", json={"email": "dup@t.test"})
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


def test_a_junk_address_is_refused_without_a_row(tc):
    assert tc.post("/v1/waitlist", json={"email": "not-an-email"}).status_code == 400
    with get_session() as s:
        assert s.execute(select(WaitlistEntry)).scalars().all() == []


def test_the_list_is_admin_only(tc):
    tc.post("/v1/auth/signup", json={"email": "nosy@t.test", "password": "password12345"})
    assert tc.get("/v1/admin/waitlist").status_code == 403
    assert tc.get("/v1/admin/waitlist/export.csv").status_code == 403


def test_an_admin_sees_the_list_and_can_export_it(tc):
    tc.post("/v1/waitlist", json={"email": "one@t.test"})
    _as_admin(tc)
    body = tc.get("/v1/admin/waitlist").json()
    assert body["total"] >= 1 and body["pending"] >= 1

    csv = tc.get("/v1/admin/waitlist/export.csv")
    assert csv.status_code == 200
    # A BOM, because Excel on Windows reads a BOM-less UTF-8 file as the local codepage and mangles
    # every non-Latin address. This is a list of real people's contact details.
    assert csv.text.startswith("﻿")
    assert "one@t.test" in csv.text


# --------------------------------------------------------------------------------------------- #
# The launch email
# --------------------------------------------------------------------------------------------- #
@pytest.fixture
def outbox(monkeypatch):
    """Intercept mail through the same hook alert delivery uses. No SMTP, no network."""
    sent: list[dict] = []
    monkeypatch.setenv("OMI_SMTP_HOST", "smtp.test")
    get_settings.cache_clear()
    from app.notifications import delivery

    monkeypatch.setattr(delivery, "_email_sender_for_tests", sent.append, raising=False)
    yield sent
    get_settings.cache_clear()


def test_everyone_pending_gets_exactly_one_email_however_often_it_is_run(tc, outbox):
    """The operator WILL run this twice, either because the first run errored or because they are
    not sure it worked. Mailing the whole waitlist twice on launch day is the most visible possible
    way to look careless, so the guard is per address rather than per run."""
    for e in ("a@t.test", "b@t.test", "c@t.test"):
        tc.post("/v1/waitlist", json={"email": e})
    _as_admin(tc)

    first = tc.post("/v1/admin/waitlist/notify").json()
    assert first["sent"] == 4          # three joins plus the admin's own signup
    assert first["remaining"] == 0

    second = tc.post("/v1/admin/waitlist/notify").json()
    assert second["sent"] == 0, "a second run must mail nobody"

    recipients = [m["to"] for m in outbox]
    assert len(recipients) == len(set(recipients)) == 4


def test_somebody_who_joins_after_the_blast_still_gets_theirs(tc, outbox):
    _as_admin(tc)
    tc.post("/v1/admin/waitlist/notify")
    outbox.clear()

    tc.post("/v1/waitlist", json={"email": "latecomer@t.test"})
    assert tc.post("/v1/admin/waitlist/notify").json()["sent"] == 1
    assert [m["to"] for m in outbox] == ["latecomer@t.test"]


def test_without_smtp_nothing_is_sent_AND_nobody_is_marked_notified(tc, monkeypatch):
    """The trap this avoids: marking the list as done on a run that sent nothing, so the real blast
    later skips everybody and the whole waitlist never hears from you."""
    monkeypatch.delenv("OMI_SMTP_HOST", raising=False)
    get_settings.cache_clear()
    tc.post("/v1/waitlist", json={"email": "unsent@t.test"})
    _as_admin(tc)

    body = tc.post("/v1/admin/waitlist/notify").json()
    assert body["sent"] == 0 and body["smtp_configured"] is False
    assert "SMTP is not configured" in body["detail"]
    with get_session() as s:
        assert all(
            r.notified_at is None for r in s.execute(select(WaitlistEntry)).scalars()
        )


def test_the_blast_is_admin_only(tc):
    tc.post("/v1/auth/signup", json={"email": "nobody@t.test", "password": "password12345"})
    assert tc.post("/v1/admin/waitlist/notify").status_code == 403
