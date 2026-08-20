"""Pre-launch lockdown: the product works, but only for admins.

WHY THIS EXISTS. The site is public and being promoted (a Kickstarter drives traffic to it) before
the product is open. Visitors need to be able to read the marketing pages and join a waitlist; what
they must not be able to do is USE the product, because every scan and every comment-section compile
spends real upstream money against a plan nobody has bought yet.

THE GATE IS ON THE API, NOT ONLY IN THE UI, AND THAT IS THE WHOLE POINT.

A redirect in the Next.js layout stops somebody *browsing* to the app. It does nothing about a
signed-in non-admin who calls ``POST /v1/scan/link/score`` directly with the session cookie their
browser already holds, which is exactly the person this is meant to stop: the cost is incurred by
the API, so the refusal has to live there. The web redirect is the courtesy; this is the control.

WHAT STAYS OPEN, and why each one has to:

* ``/v1/auth/*`` — the web app must be able to ask who you are in order to redirect you, and people
  are still allowed to create accounts (a signup during lockdown becomes a waitlist entry).
* ``/v1/waitlist`` — the entire point of the coming-soon page.
* health — an unreachable health check reads as an outage.
* Anything unauthenticated never reaches ``require_user`` at all. Shared reports at ``/r/<token>``
  therefore keep working by construction, which is deliberate: they cost nothing to serve (the scan
  was paid for long ago) and they are the best available proof the product does what it claims.

The demo scan is handled separately, because it is unauthenticated and so is never seen by
``require_user``. It is turned OFF during lockdown: at campaign traffic it is a real bill (a demo
runs the true engine and a true model call) with no way to convert anyone until launch.

LIFTING IT IS ONE ENV VAR. ``OMI_LOCKDOWN=false`` on the API service, then redeploy. The code
default is False on purpose: when the variable is eventually deleted the site opens rather than
silently staying shut, and a stale lockdown outliving its launch date would be its own outage.
``render.yaml`` commits ``'true'`` explicitly, and the boot log states which mode is active on every
start, so this is never something anyone has to guess at.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, status

log = logging.getLogger("omi.lockdown")

#: Path prefixes a signed-in non-admin may still reach while the product is locked. Deliberately a
#: SHORT allowlist rather than a blocklist of product routes: a route added later is refused by
#: default, which is the safe direction. Getting this wrong the other way silently reopens the
#: product on whichever endpoint somebody forgot to list.
OPEN_PREFIXES: tuple[str, ...] = (
    "/v1/auth",
    "/v1/waitlist",
    "/v1/health",
    "/healthz",
    "/v1/status",
)

#: What the API answers with. 403 rather than 402: this is not something a customer can pay to fix
#: today, and offering to take their money for a product they cannot use would be worse than the
#: refusal. The web app keys on this code to send them to the coming-soon page.
LOCKED_DETAIL = (
    "OmiSphere is not open yet. Join the waitlist and we will email you the moment it is."
)


def is_locked(settings) -> bool:
    return bool(getattr(settings, "lockdown", False))


def path_is_open(path: str) -> bool:
    return any(path.startswith(p) for p in OPEN_PREFIXES)


def enforce(*, path: str, is_admin: bool, settings) -> None:
    """Refuse a non-admin request for a product route while the product is locked.

    Never refuses an admin, so the operator can use and demonstrate the whole product while it is
    shut to everyone else. Local mode resolves to ``is_admin=True`` and is therefore unaffected,
    which keeps every existing test running unchanged.
    """
    if not is_locked(settings) or is_admin or path_is_open(path):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=LOCKED_DETAIL)


def boot_line(settings) -> str:
    """One line for the startup log. An operator must never have to guess which mode is live."""
    if is_locked(settings):
        return (
            "LOCKDOWN ACTIVE: only admins can use the product. Everyone else gets the waitlist. "
            "Set OMI_LOCKDOWN=false and redeploy to open the site."
        )
    return "Lockdown: off (the product is open to all signed-in users)."
