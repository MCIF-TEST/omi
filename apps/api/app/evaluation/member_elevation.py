"""Member-level ELEVATION measurement — the Phase-3 residual, closed and measured.

Phase 3's corroboration gate fixed the *batch* verdict (campaign-level FPR on
legitimate controls 1.00 -> 0.49/gated), but its report (§6) documented one
residual: per-member elevation read the cluster's own score, so a human inside
a ``style_match``-only cluster (membership FPR 0.73 on the TwitterData human
control) could still be elevated *individually*. The member-level gate now
ships in :func:`app.detection.coordination.elevate.build_coordination_signal`.

This module MEASURES that path — it does not modify detection logic. For each
account: standalone engine scan -> the clusters it belongs to ->
:func:`apply_coordination` (the exact production elevation) -> adjusted tier.
An "ungated" arm reproduces the pre-fix signal composition (max cluster score,
uncapped confidence — the constants the old code used) purely so the published
report can show before vs after on identical inputs.

Metrics per scenario:

* ``membership_rate``      — fraction of accounts inside >=1 cluster (Phase-3's
                             0.73 on humans; the gate does NOT change this —
                             clustering is evidence, kept visible).
* ``standalone_elevated``  — fraction the single-account engine already scores
                             ELEVATED+ with no coordination input (the floor).
* ``elevated_gated``       — fraction ELEVATED+ after production elevation.
* ``elevated_ungated``     — fraction ELEVATED+ under the pre-fix composition.
* ``induced_gated/ungated``— among accounts the engine scored below ELEVATED
                             standalone, the fraction LIFTED to ELEVATED+ by
                             coordination. On organic controls this is the
                             member-level elevation FPR (the harm number);
                             on IO operations it is coordination rescue.

Run the standard report scenarios (TwitterData humans + novelty bots, GRU,
Iran 2020-09, Xinjiang) with::

    cd apps/api && python -m app.evaluation.member_elevation
"""

from __future__ import annotations

import csv
import glob
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.detection.coordination._types import CoordinationCluster
from app.detection.coordination.elevate import (
    COORDINATION_SIGNAL_NAME,
    apply_coordination,
    coordination_membership,
)
from app.detection.engine import analyze_account
from app.detection.scoring import aggregate
from app.evaluation.coordination_benchmark import (
    AccountEntry,
    CoordinationScenario,
    _run_detectors,
)
from app.evaluation.io_coordination import _co_tag_finding
from app.memory.fingerprint import extract_fingerprint
from app.ml.public_import import PublicRecord, _to_posts, _to_profile, coalesce_records
from app.schemas import ScanResult, SignalResult, Tier

# Pre-fix composition constants — mirrors the OLD build_coordination_signal
# exactly (max cluster score, confidence floor 0.55 + 0.20/method, no cap).
# Kept here, in the measurement module, so the production code carries only
# the fixed behaviour while the report can still show the honest "before".
_PRE_FIX_BASE_CONFIDENCE = 0.55
_PRE_FIX_PER_METHOD = 0.20

_ELEVATED_TIERS = (Tier.ELEVATED, Tier.HIGH)


def _ungated_signal(clusters: list[CoordinationCluster]) -> SignalResult | None:
    """The pre-fix per-member coordination signal (no corroboration gate)."""
    if not clusters:
        return None
    methods = sorted({c.method for c in clusters})
    return SignalResult(
        name=COORDINATION_SIGNAL_NAME,
        probability=max(c.score for c in clusters),
        confidence=min(1.0, _PRE_FIX_BASE_CONFIDENCE + _PRE_FIX_PER_METHOD * len(methods)),
        evidence=[e for c in clusters for e in c.evidence][:5],
        sub_signals={"detector_count": float(len(methods))},
    )


@dataclass
class MemberElevationRow:
    external_id: str
    role: str                       # "organic" | "bot"
    in_cluster: bool
    methods: tuple[str, ...]
    standalone_p: float
    standalone_tier: Tier
    gated_p: float
    gated_tier: Tier
    ungated_p: float
    ungated_tier: Tier


def measure_rows(
    scans_by_id: dict[str, ScanResult],
    clusters: list[CoordinationCluster],
    roles_by_id: dict[str, str],
) -> list[MemberElevationRow]:
    """Per-account elevation under the production gate vs the pre-fix path.

    Pure over its inputs (no I/O): callers supply the standalone scans, the
    detected clusters, and each account's ground-truth role.
    """
    by_member = coordination_membership(clusters)
    rows: list[MemberElevationRow] = []
    for eid, base in scans_by_id.items():
        member_clusters = by_member.get(eid, [])
        gated = apply_coordination(base, member_clusters)   # production path
        if member_clusters:
            ungated = aggregate(list(base.signals) + [_ungated_signal(member_clusters)])
        else:
            ungated = base
        rows.append(MemberElevationRow(
            external_id=eid,
            role=roles_by_id.get(eid, "organic"),
            in_cluster=bool(member_clusters),
            methods=tuple(sorted({c.method for c in member_clusters})),
            standalone_p=base.overall_probability, standalone_tier=base.tier,
            gated_p=gated.overall_probability, gated_tier=gated.tier,
            ungated_p=ungated.overall_probability, ungated_tier=ungated.tier,
        ))
    return rows


def summarize(rows: list[MemberElevationRow]) -> dict:
    """Scenario-level membership / elevation / induced-lift rates."""
    n = len(rows)
    if n == 0:
        return {"n": 0}

    def frac(pred) -> float:
        return round(sum(1 for r in rows if pred(r)) / n, 3)

    not_elevated_standalone = [r for r in rows if r.standalone_tier not in _ELEVATED_TIERS]

    def induced(tier_attr: str) -> float | None:
        if not not_elevated_standalone:
            return None
        lifted = sum(
            1 for r in not_elevated_standalone
            if getattr(r, tier_attr) in _ELEVATED_TIERS
        )
        return round(lifted / len(not_elevated_standalone), 3)

    return {
        "n": n,
        "membership_rate": frac(lambda r: r.in_cluster),
        "standalone_elevated": frac(lambda r: r.standalone_tier in _ELEVATED_TIERS),
        "elevated_gated": frac(lambda r: r.gated_tier in _ELEVATED_TIERS),
        "elevated_ungated": frac(lambda r: r.ungated_tier in _ELEVATED_TIERS),
        "n_below_elevated_standalone": len(not_elevated_standalone),
        "induced_gated": induced("gated_tier"),
        "induced_ungated": induced("ungated_tier"),
    }


# ---------------------------------------------------------------------------
# Scenario driver over real records — same load + detector path Phases 2–3 used.
# ---------------------------------------------------------------------------


def evaluate_records(
    records: list[PublicRecord], *, role: str, label: str,
    cap: int = 45, with_network: bool = True,
) -> dict:
    """Coalesce -> standalone-scan -> detectors (+co_tag) -> per-member rows.

    Mirrors :func:`app.evaluation.io_coordination.build_scenario` but keeps the
    full standalone :class:`ScanResult` per account (the elevation measurement
    needs the signals, not just the probability the AccountEntry carries).
    """
    recs = coalesce_records(records)[:cap]
    scans_by_id: dict[str, ScanResult] = {}
    entries: list[AccountEntry] = []
    for rec in recs:
        posts = _to_posts(rec)
        scan = analyze_account(_to_profile(rec), posts)
        scans_by_id[rec.external_id] = scan
        created = None
        if rec.account_age_days is not None:
            created = datetime.now(timezone.utc) - timedelta(days=max(0, rec.account_age_days))
        first_time = next((t for t in rec.post_times if t), None)
        entries.append(AccountEntry(
            external_id=rec.external_id,
            handle=rec.handle or rec.external_id,
            role=role,
            created_at=created,
            texts=list(rec.texts),
            fingerprint=extract_fingerprint(scan),
            individual_probability=scan.overall_probability,
            video_comment_id=f"{rec.external_id}:0",
            video_comment_text=(rec.texts[0] if rec.texts else None),
            video_comment_created_at=first_time,
        ))
    scn = CoordinationScenario(
        label=label, scenario_type="multi", expected_coordination="high",
        accounts=entries, planted_clusters=[],
    )
    findings = list(_run_detectors(scn))
    if with_network:
        findings.append(_co_tag_finding(scn))
    clusters = [c for f in findings for c in f.clusters]
    rows = measure_rows(scans_by_id, clusters, {e.external_id: role for e in entries})
    out = summarize(rows)
    out["label"] = label
    out["role"] = role
    return out


# ---------------------------------------------------------------------------
# Standard report scenarios (PHASE4_REPORT.md) — reproducible in one command.
# ---------------------------------------------------------------------------


def _load_io(dirpath: str, cap_rows: int = 16000) -> list[PublicRecord]:
    from app.ml.datasets.adapters import _parse_io_disclosure

    files = [
        f for f in sorted(glob.glob(f"{dirpath}/**/*.csv", recursive=True))
        if "user" not in os.path.basename(f).lower()
    ]
    recs: list[PublicRecord] = []
    seen = 0
    for path in files:
        with open(path, newline="", encoding="utf-8", errors="replace") as fh:
            for row in csv.DictReader(fh):
                r = _parse_io_disclosure(
                    {k.lower(): v for k, v in row.items()},
                    os.path.basename(dirpath), str(seen),
                )
                seen += 1
                if r:
                    recs.append(r)
                if seen >= cap_rows:
                    break
        if seen >= cap_rows:
            break
    return recs


def _load_twitterdata(path: str, *, humans: bool, cap_rows: int = 400_000) -> list[PublicRecord]:
    from app.ml.datasets.adapters import _parse_twitterdata

    recs: list[PublicRecord] = []
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            if i >= cap_rows:
                break
            r = _parse_twitterdata({k.lower(): v for k, v in row.items()}, "TwitterData_Joined", str(i))
            if r and (r.is_bot != humans):
                recs.append(r)
    return recs


def run_standard_scenarios() -> list[dict]:
    from app.ml.datasets.paths import default_datasets_dir

    base = default_datasets_dir() / "Datasets"
    td = str(base / "TwitterData_Joined.csv")
    out: list[dict] = []
    out.append(evaluate_records(
        _load_twitterdata(td, humans=True), role="organic",
        label="CONTROL — TwitterData legit humans"))
    out.append(evaluate_records(
        _load_twitterdata(td, humans=False), role="bot",
        label="CONTROL — TwitterData novelty bots"))
    out.append(evaluate_records(
        _load_io(str(base / "GRU")), role="bot", label="Russia GRU (2020-12)"))
    out.append(evaluate_records(
        _load_io(str(base / "IRA" / "2020-09")), role="bot", label="Iran (2020-09)"))
    out.append(evaluate_records(
        _load_io(str(base / "Xinjiang")), role="bot", label="China Xinjiang (CNHU)"))
    return out


if __name__ == "__main__":
    for s in run_standard_scenarios():
        print(
            f"{s['label']}: n={s['n']} membership={s['membership_rate']} "
            f"standalone_elev={s['standalone_elevated']} "
            f"gated={s['elevated_gated']} ungated={s['elevated_ungated']} "
            f"induced_gated={s['induced_gated']} induced_ungated={s['induced_ungated']}"
        )
