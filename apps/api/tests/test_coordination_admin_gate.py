"""Authorisation on the coordination surface, proved against a real non-admin user.

THE TRAP THIS SUITE EXISTS FOR: every other test in this repo runs in local mode
(``OMI_REQUIRE_AUTH=false``), where ``require_user`` returns ``CurrentUser(is_admin=True)``. A test
written that way passes whether or not the gate exists. That is exactly why the campaign
enumeration leak survived its own test file until ``test_campaign_tenancy.py`` was written. So
everything here signs up a real user against a real app with auth ON.

Two surfaces are covered:

* ``/v1/admin/coordination/*``, new in this change.
* ``/v1/narratives/*``, which was ``require_user`` only while serving deployment-global narrative
  clusters built from every customer's scans. The page had always gated on ``is_admin``
  server-side; its API had not.
* ``/v1/admin/cross-narratives/*``, the cross-investigation queue. A finding there is assembled
  from many customers' scans and belongs to none of them, so it is gated for the same reason.
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def auth_client(tmp_path, monkeypatch):
    """A real app with auth enforced, and a signed-up NON-admin user."""
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "test-secret-for-the-admin-gate-suite")
    monkeypatch.setenv("OMI_DATABASE_URL", f"sqlite:///{tmp_path}/gate.db")
    monkeypatch.setenv("OMI_SUPER_ADMIN_EMAILS", "")

    from app.core.config import get_settings
    get_settings.cache_clear()
    import app.storage.db as db
    db._engine = None
    db._SessionLocal = None

    from app.main import create_app
    app = create_app()
    client = TestClient(app)

    email = f"nobody-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/v1/auth/signup", json={"email": email, "password": "hunter2hunter2"})
    assert r.status_code in (200, 201), r.text

    me = client.get("/v1/auth/me")
    assert me.status_code == 200, me.text
    assert me.json().get("is_admin") is False, "this suite is meaningless against an admin"

    yield client

    get_settings.cache_clear()
    db._engine = None
    db._SessionLocal = None
    os.environ.pop("OMI_REQUIRE_AUTH", None)


COORDINATION_ROUTES = [
    ("GET", "/v1/admin/coordination"),
    ("GET", "/v1/admin/coordination/inv_anything"),
    ("POST", "/v1/admin/coordination/inv_anything/rerun"),
    ("POST", "/v1/admin/coordination/inv_anything/reopen"),
]

CROSS_NARRATIVE_ROUTES = [
    ("GET", "/v1/admin/cross-narratives"),
    ("GET", "/v1/admin/cross-narratives/topics"),
    ("POST", "/v1/admin/cross-narratives/run"),
    ("POST", "/v1/admin/cross-narratives/1/reopen"),
]

#: The set-level detector's own surface. It reports groups of NAMED REAL PEOPLE as running
#: together on statistical evidence, and its queue carries other customers' investigation ids, so it
#: is gated for the same reason `/campaigns` is: there is no owner to scope a finding to.
NETDETECT_ROUTES = [
    ("POST", "/v1/admin/netdetect/inv_anything"),
    ("GET", "/v1/admin/netdetect/findings/all"),
    ("GET", "/v1/admin/netdetect/findings/calibration"),
]

NARRATIVE_ROUTES = [
    ("GET", "/v1/narratives"),
    ("GET", "/v1/narratives/1"),
    ("GET", "/v1/narratives/1/members"),
]


@pytest.mark.parametrize("method,path", COORDINATION_ROUTES)
def test_coordination_routes_refuse_a_signed_in_customer(auth_client, method, path):
    r = auth_client.request(method, path)
    assert r.status_code == 403, f"{method} {path} answered {r.status_code}: {r.text[:200]}"


def test_the_dismiss_route_refuses_a_signed_in_customer(auth_client):
    r = auth_client.post("/v1/admin/coordination/inv_anything/dismiss", json={"note": "x"})
    assert r.status_code == 403


@pytest.mark.parametrize("method,path", CROSS_NARRATIVE_ROUTES)
def test_cross_narrative_routes_refuse_a_signed_in_customer(auth_client, method, path):
    """These findings span every customer's scans, so there is no owner to scope them to."""
    r = auth_client.request(method, path)
    assert r.status_code == 403, f"{method} {path} answered {r.status_code}: {r.text[:200]}"


def test_the_cross_narrative_dismiss_route_refuses_a_signed_in_customer(auth_client):
    r = auth_client.post("/v1/admin/cross-narratives/1/dismiss", json={"reason": "x"})
    assert r.status_code == 403


@pytest.mark.parametrize("method,path", NETDETECT_ROUTES)
def test_netdetect_routes_refuse_a_signed_in_customer(auth_client, method, path):
    r = auth_client.request(method, path)
    assert r.status_code == 403, f"{method} {path} answered {r.status_code}: {r.text[:200]}"


def test_the_netdetect_judgement_routes_refuse_a_signed_in_customer(auth_client):
    """These dismissals are the reservoir a later calibration is fitted against. A customer able to
    write into it could steer the detector, which is a stranger attack surface than reading."""
    for verb in ("dismiss", "confirm"):
        r = auth_client.post(f"/v1/admin/netdetect/findings/1/{verb}", json={"reason": "x"})
        assert r.status_code == 403, f"{verb} answered {r.status_code}: {r.text[:200]}"


@pytest.mark.parametrize("method,path", NARRATIVE_ROUTES)
def test_narrative_routes_refuse_a_signed_in_customer(auth_client, method, path):
    """A ``Narrative`` has no owner: it is assembled across every customer's scans. So these
    cannot be scoped, and they are gated instead, matching ``/v1/campaigns``."""
    r = auth_client.request(method, path)
    assert r.status_code == 403, f"{method} {path} answered {r.status_code}: {r.text[:200]}"


def test_the_gate_is_a_403_and_not_a_404(auth_client):
    """A 404 would be a reasonable design, but it must not be reached by ACCIDENT: a missing gate
    that happens to 404 because the row does not exist reads identically in a test and is not a
    gate at all. Asserting 403 pins that authorisation ran before the lookup."""
    r = auth_client.get("/v1/admin/coordination/definitely_not_a_real_slug")
    assert r.status_code == 403


def test_an_admin_gets_through(tmp_path, monkeypatch):
    """The mirror image: with the gate satisfied the routes work, so the tests above are proving
    authorisation rather than a broken router."""
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "test-secret-for-the-admin-gate-suite")
    monkeypatch.setenv("OMI_DATABASE_URL", f"sqlite:///{tmp_path}/gate_admin.db")
    email = f"boss-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setenv("OMI_SUPER_ADMIN_EMAILS", email)

    from app.core.config import get_settings
    get_settings.cache_clear()
    import app.storage.db as db
    db._engine = None
    db._SessionLocal = None

    from app.main import create_app
    client = TestClient(create_app())
    r = client.post("/v1/auth/signup", json={"email": email, "password": "hunter2hunter2"})
    assert r.status_code in (200, 201), r.text
    assert client.get("/v1/auth/me").json().get("is_admin") is True

    listing = client.get("/v1/admin/coordination")
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["detections"] == []
    assert body["total"] == 0

    cross = client.get("/v1/admin/cross-narratives")
    assert cross.status_code == 200, cross.text

    findings = client.get("/v1/admin/netdetect/findings/all")
    assert findings.status_code == 200, findings.text
    assert findings.json() == []
    assert cross.json()["findings"] == []

    get_settings.cache_clear()
    db._engine = None
    db._SessionLocal = None
