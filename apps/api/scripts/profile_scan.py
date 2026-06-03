"""Profiling harness for large-investigation scaling (Tier-1 reliability).

Measures, for N in {10,20,50} commenters, against a seeded fingerprint store:
  * upstream API calls (a paginating fake client, ~20/page like twitterapi.io)
  * all_with_fingerprints() invocations + total time (the per-commenter reload)
  * coordination (_compute_cross_links) time
  * total wall time (engine+DB only; network is instant here)
  * peak memory (tracemalloc)
Plus a micro-benchmark of all_with_fingerprints() at store sizes 10..1000.

Network LATENCY is NOT modelled (fake = instant); the API *call count* is the
real telemetry. Run:  python -m scripts.profile_scan
"""
from __future__ import annotations

import time
import tracemalloc

from app.storage.db import reset_db_for_tests, get_session
from app.storage.repository import AccountRepository
from app.schemas import Profile, Post, ScanResult, SignalResult, Tier
from app.detection.engine import analyze_account
from app.memory.fingerprint import extract_fingerprint
import app.orchestrator as orch
from app.integrations.source import TwitterSource

PAGE = 20  # twitterapi.io-style page size


def _fp_dim() -> int:
    import datetime as dt
    when = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    p = Profile(platform="x", handle="dim", display_name="d", follower_count=10)
    posts = [Post(id=str(i), author_handle="dim", text="hello world " * 5,
                  created_at=when) for i in range(3)]
    return len(extract_fingerprint(analyze_account(p, posts)))


def seed_store(n: int, dim: int) -> None:
    import random
    random.seed(7)
    with get_session() as s:
        repo = AccountRepository(s)
        for i in range(n):
            fp = [random.random() for _ in range(dim)]
            prof = Profile(platform="x", handle=f"seed_{i}", display_name=f"s{i}",
                           follower_count=100)
            scan = ScanResult(overall_probability=random.random(), confidence=0.6,
                              tier=Tier.LOW, signals=[], summary="seed")
            repo.upsert_with_scan(platform="x", external_id=f"seed_{i}",
                                  profile=prof, scan=scan, fingerprint=fp)
        s.commit()


class CountingFake:
    """Paginating twitterapi.io fake; counts every .get (= 1 upstream call)."""
    def __init__(self) -> None:
        self.calls = 0

    def get(self, path: str, params: dict) -> dict:
        self.calls += 1
        if "user/info" in path:
            h = params.get("userName") or "u"
            return {"data": {"user": {"userName": h, "name": h, "followers": 120,
                    "following": 80, "createdAt": "Mon Jan 15 00:00:00 +0000 2018"}}}
        if "user/last_tweets" in path:
            cur = int(params.get("cursor") or 0)
            tweets = [{"id": f"t{cur}_{i}", "text": "just my normal opinion here friends",
                       "createdAt": "2024-02-01T00:00:00Z"} for i in range(PAGE)]
            return {"has_next_page": cur + 1 < 3, "next_cursor": str(cur + 1),
                    "data": {"tweets": tweets}}
        # tweet/replies — 20 distinct authors per page
        cur = int(params.get("cursor") or 0)
        tweets = [{"id": f"r{cur}_{i}", "text": "great point, totally agree!!",
                   "createdAt": "2024-03-01T12:00:00Z",
                   "author": {"userName": f"replier_{cur}_{i}"}} for i in range(PAGE)]
        return {"has_next_page": True, "next_cursor": str(cur + 1),
                "data": {"tweets": tweets}}


def profile_scan(n: int, seed_size: int, dim: int) -> dict:
    reset_db_for_tests("sqlite:///:memory:")
    seed_store(seed_size, dim)

    fake = CountingFake()
    src = TwitterSource(fake)

    # instrument all_with_fingerprints
    orig_afp = AccountRepository.all_with_fingerprints
    stats = {"afp_calls": 0, "afp_time": 0.0, "coord_time": 0.0}

    def counting_afp(self):
        t = time.perf_counter()
        r = orig_afp(self)
        stats["afp_time"] += time.perf_counter() - t
        stats["afp_calls"] += 1
        return r
    AccountRepository.all_with_fingerprints = counting_afp

    orig_cross = orch._compute_cross_links

    def timed_cross(*a, **k):
        t = time.perf_counter()
        r = orig_cross(*a, **k)
        stats["coord_time"] += time.perf_counter() - t
        return r
    orch._compute_cross_links = timed_cross

    tracemalloc.start()
    t0 = time.perf_counter()
    with get_session() as s:
        out = orch.scan_comprehensive(
            s, account_url_or_handle=None, video_url_or_id="1788888888888888",
            comments_text=None, max_commenters=n, force_refresh=False, source=src,
        )
    wall = time.perf_counter() - t0
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    AccountRepository.all_with_fingerprints = orig_afp
    orch._compute_cross_links = orig_cross

    n_comm = len(out.video_output.commenter_records) if out.video_output else 0
    return {"N": n, "commenters_scanned": n_comm, "api_calls": fake.calls,
            "afp_calls": stats["afp_calls"], "afp_time_ms": round(stats["afp_time"] * 1000, 1),
            "coord_ms": round(stats["coord_time"] * 1000, 1),
            "wall_ms": round(wall * 1000, 1), "peak_mb": round(peak / 1e6, 1)}


def microbench_afp(dim: int) -> list[dict]:
    rows = []
    for size in (10, 100, 300, 1000):
        reset_db_for_tests("sqlite:///:memory:")
        seed_store(size, dim)
        with get_session() as s:
            repo = AccountRepository(s)
            # warm + time 20 loads
            repo.all_with_fingerprints()
            t = time.perf_counter()
            for _ in range(20):
                repo.all_with_fingerprints()
            per = (time.perf_counter() - t) / 20
        rows.append({"store_size": size, "per_call_ms": round(per * 1000, 2)})
    return rows


if __name__ == "__main__":
    dim = _fp_dim()
    print(f"fingerprint dim = {dim}\n")
    print("=== all_with_fingerprints() per-call cost vs store size ===")
    for r in microbench_afp(dim):
        print(f"  store={r['store_size']:>5}  {r['per_call_ms']:>7} ms/call")
    print("\n=== scan profile (seed store = 300 accounts) ===")
    hdr = ("N", "scanned", "api_calls", "afp_calls", "afp_ms", "coord_ms", "wall_ms", "peak_mb")
    print("  " + "  ".join(f"{h:>10}" for h in hdr))
    for n in (10, 20, 50):
        r = profile_scan(n, seed_size=300, dim=dim)
        print("  " + "  ".join(f"{str(r[k]):>10}" for k in
              ("N", "commenters_scanned", "api_calls", "afp_calls", "afp_time_ms", "coord_ms", "wall_ms", "peak_mb")))
    from app.core import background
    background.shutdown(wait_seconds=10.0)
