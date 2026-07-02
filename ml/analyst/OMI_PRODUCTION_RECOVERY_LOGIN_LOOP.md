# Omi — Production Recovery: the /login ↔ /dashboard Redirect Loop

> **Priority-1 production failure.** Users observed `Landing → Login → Dashboard → Login → …`
> ending in Chrome's `ERR_TOO_MANY_REDIRECTS`, with the network trace showing repeated **307**s
> between `/login` and `/dashboard`. This sprint reproduced the loop from the actual code, found
> the first incorrect decision, fixed it, and re-verified the complete user journey.

---

## 1. Root cause

**Two contradictory definitions of "authenticated," with no reconciliation and no cookie
hygiene** — triggered whenever a browser holds an `omi_session` cookie that no longer resolves
server-side:

- `apps/web/middleware.ts` treated **cookie existence** as "logged in" and bounced
  `/login → /dashboard` (307).
- `apps/web/app/(app)/layout.tsx` treats **backend validation** as the authority
  (`getCurrentUser()` → `GET /v1/auth/me`); when `/me` returns null it bounces
  `/dashboard → /login` (307).

A cookie that **exists but doesn't validate** satisfies the first check and fails the second →
infinite 307 ping-pong. The user can never reach the login form to fix their own state, and
nothing ever clears the dead cookie (30-day `Max-Age`).

**What makes the cookie stale in production (all reproduced):**
- **Ephemeral-disk redeploy (the primary trigger).** The API's default store is sqlite on Render's
  ephemeral disk (`/v1/status` reports `storage_ephemeral: true`). Every redeploy/restart wipes the
  `users` table; `_decode_session` still verifies the signature, but `session.get(User, uid)` finds
  no row → `/me` → null. Every previously-logged-in browser then loops.
- **Session-secret rotation** (`OMI_SESSION_SECRET` changed between deploys) → `BadSignature` →
  same loop.
- (Any expired/garbled cookie behaves identically.)

**The first incorrect decision in the chain:** the middleware's `/login → /dashboard` redirect —
it asserts authentication from existence-only evidence. The layout's redirect is correct policy;
the middleware's is not, and it is the hop that locks users out of the form.

## 2. Files changed

| File | Change |
|---|---|
| `apps/web/middleware.ts` | Removed the existence-only `/login|/signup → /dashboard` bounce. Cookie existence now only ever gates **toward** `/login` (the protective half), never asserts auth. |
| `apps/web/app/(auth)/login/page.tsx` | Restored the "already logged in → dashboard" convenience as a **validated** server-side check (`getCurrentUser()`); honors `?next=` only for same-origin paths (no open redirect). A stale cookie now renders the form. |
| `apps/web/app/(auth)/signup/page.tsx` | Same validated guard. |
| `apps/api/app/routes/auth.py` | `/v1/auth/me` now **clears** a session cookie that was presented but did not resolve (rotated secret / expired / user row gone), so clients self-heal instead of carrying a dead cookie for 30 days. |
| `apps/api/tests/test_auth_session_loop.py` | 5 regression tests pinning the backend contract (stale-uid clear, rotated-secret clear, valid-session keep, no-cookie no-op, full re-login recovery). |

## 3. The fix (essence)

```
middleware.ts   — delete:  if ((pathname==='/login'||'/signup') && hasSession) redirect('/dashboard')
login/page.tsx  — add:     const user = await getCurrentUser(); if (user) redirect(safeNext)
signup/page.tsx — add:     const user = await getCurrentUser(); if (user) redirect('/dashboard')
auth.py /me     — add:     if cookie-was-presented and current is None: clear_session(response)
```

One authority (backend validation) now drives every "you are logged in" decision; cookie existence
is only ever used to gate unauthenticated access; dead cookies are actively cleared.

## 4. Why the loop occurred (exact chain, reproduced)

Reproduction: sign up (cookie set) → simulate a Render redeploy (`rm` sqlite DB, restart API, same
secret) → request with the surviving cookie:

```
BEFORE THE FIX
GET /dashboard              -> 307 -> /login        ((app)/layout: /me = null)
GET /login?next=%2Fdashboard-> 307 -> /dashboard    (middleware: cookie exists)
GET /dashboard              -> 307 -> /login        ... repeat ...
curl: (47) Maximum (8) redirects followed           == Chrome ERR_TOO_MANY_REDIRECTS
```

```
AFTER THE FIX (same stale-cookie state)
GET /dashboard              -> 307 -> /login
GET /login                  -> 200  (form renders; num_redirects=1)
GET /v1/auth/me             -> 200 null + Set-Cookie: omi_session=""; Max-Age=0   (self-heal)
```

Also verified after the fix: a **valid** session still gets the convenience redirect
(`/login → 307 → /dashboard`, now backed by validation) and `/dashboard → 200`; a rotated-secret
cookie lands on the form in one hop.

## 5. Verification that login now succeeds (browser, production build)

**Recovery journey** (Chromium, starting from the loop-trigger state — stale signed cookie in the
jar): 7/7 PASS — landing → `/dashboard` resolves to the **login form** (no
`ERR_TOO_MANY_REDIRECTS`) → **login (200) → dashboard** → investigate → run scan (202 job →
persisted `inv_909046ba`) → AI analysis renders (Governor **permit** badge) → results page with
evidence sections; zero page errors.

**Full regression journey** (fresh DB): 10/10 PASS — signup → dashboard → scan 202 →
permalink → investigations list → detail (152 KB render) → AI assessment (Governor permit) →
share mint → public report logged-out → logout re-gates → **login → dashboard**. Zero 4xx/5xx.

**Gates:** backend suite green including the 5 new loop tests (count in the PR/commit);
`next build` passed; `tsc --noEmit` passed.

## 6. Remaining production blockers (unchanged by this fix, operator-side)

1. **Persistent database.** The loop's primary trigger is the root issue: sqlite on an ephemeral
   disk loses **all users and investigations on every redeploy**. The fix makes auth degrade
   gracefully (users can always re-register/log in), but production needs `OMI_DATABASE_URL`
   pointed at a persistent Postgres (the Supabase instance already provisioned for memory is a
   candidate) — otherwise accounts and saved investigations remain redeploy-scoped.
2. **Pin `OMI_SESSION_SECRET`** in Render env (never rely on the dev default; never rotate
   casually — rotation logs everyone out, though it no longer loops them).
3. **Set `OMI_PUBLIC_BASE_URL`** to the real `https://…` origin on the API service so the session
   cookie is issued with `Secure` in production.
4. **Platform credentials** (`OMI_YOUTUBE_API_KEY`) for real scans, and the live-analyst env
   (endpoint URL/token) for model-backed AI analysis — both have ready verification instruments
   from the prior sprints.

---

*No new features; no redesign. The change is confined to the auth seam: one deleted middleware
branch, two validated page guards, one self-healing response header, five regression tests.*
