#!/usr/bin/env python3
"""Run the working Omi Analyst on sample evidence (OMI_ANALYST_IMPLEMENTATION_V1).

Builds representative engine outputs (an account scan, a campaign, a narrative),
produces all four assessment types through the deterministic (always-on) provider,
validates each against analyst_response_schema.json, stores them for future training
data, and prints a summary. No GPU, no network, no training. Exit 0 iff all valid.

    python ml/analyst/run_analyst_demo.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from omi_analyst import AnalystOutputStore, OmiAnalyst, load_analyst_config  # noqa: E402


def sample_account_scan_suspicious() -> dict:
    return {
        "overall_probability": 0.68, "confidence": 0.55, "tier": "elevated",
        "summary": "Posting cadence is unusually regular; limited interaction history.",
        "signals": [
            {"name": "temporal", "probability": 0.81, "confidence": 0.6,
             "evidence": ["Inter-post interval variance in the bottom 8% of accounts."]},
            {"name": "engagement", "probability": 0.55, "confidence": 0.4,
             "evidence": ["Reply/like ratio skewed toward broadcast."]},
            {"name": "community", "probability": 0.2, "confidence": 0.5,
             "evidence": ["A modest established interaction footprint."]},
            {"name": "ai_writing", "probability": 0.7, "confidence": 0.6,
             "evidence": ["Some AI-assisted phrasing."], "supplemental": True},
        ],
        "contributions": [
            {"name": "temporal", "impact": 0.61, "direction": "raises", "logit_delta": 0.9,
             "headline": "Inter-post intervals show low variation, consistent with scheduling."},
            {"name": "engagement", "impact": 0.18, "direction": "raises", "logit_delta": 0.25,
             "headline": "Engagement pattern skews toward broadcast over conversation."},
            {"name": "community", "impact": 0.21, "direction": "lowers", "logit_delta": -0.3,
             "headline": "An established interaction footprint is more consistent with an organic account."},
            {"name": "ai_writing", "impact": 0.0, "direction": "neutral", "logit_delta": 0.0,
             "supplemental": True, "headline": "AI-assisted phrasing observed."},
        ],
        "score_breakdown": {"single_axis_capped": True, "convergence_bonus_logit": 0.0,
                            "final_probability": 0.68},
        "reasons": ["Unusually regular posting cadence (temporal detector)."],
        "weak_signals": ["Only 9 posts available — engagement and semantic detectors abstained."],
        "intelligence": {"authenticity_score": 0.34, "risk_level": "medium",
                         "dimensions": [{"name": "behavior", "score": 0.7}]},
    }


def sample_account_scan_clean() -> dict:
    return {
        "overall_probability": 0.12, "confidence": 0.82, "tier": "low",
        "summary": "Patterns broadly consistent with organic activity.",
        "signals": [{"name": "temporal", "probability": 0.15, "confidence": 0.8,
                     "evidence": ["Natural posting-interval variation."]}],
        "contributions": [
            {"name": "community", "impact": 0.5, "direction": "lowers", "logit_delta": -0.6,
             "headline": "A long, established interaction history is consistent with an organic account."},
            {"name": "temporal", "impact": 0.2, "direction": "lowers", "logit_delta": -0.1,
             "headline": "Posting cadence shows natural variation."},
        ],
        "score_breakdown": {"single_axis_capped": False, "final_probability": 0.12},
        "intelligence": {"authenticity_score": 0.88, "risk_level": "low"},
    }


def sample_campaign() -> dict:
    return {
        "coordination_score": 0.72, "member_count": 6,
        "methods": ["co_tag", "temporal_semantic"], "hashtags": ["#launch", "#nowlive"],
        "coordination_label": "coordinated",
        "members": [{"authenticity_score": 0.7}, {"authenticity_score": 0.66}],
        "single_axis_capped": False, "convergence": True,
    }


def sample_narrative() -> dict:
    return {
        "label": "Identical praise for a product launch posted across unrelated videos",
        "member_count": 240, "distinct_authors": 180, "spread_ratio": 0.62,
        "inauthenticity_score": 0.58, "coordination_label": "suspicious",
        "signals": {"burstiness": 0.7, "template_similarity": 0.66},
        "sample_texts": ["Best launch ever, buying now!", "Absolutely incredible, instant buy!"],
    }


def main() -> int:
    cfg = load_analyst_config()
    print(f"Config: repo={cfg.repo_id} base={cfg.base_model} source={cfg.source} "
          f"prompt={cfg.prompt_version} model_revision={cfg.model_revision}\n")

    with tempfile.TemporaryDirectory() as d:
        store = AnalystOutputStore(path=Path(d) / "demo_outputs.jsonl")
        analyst = OmiAnalyst(config=cfg, store=store)  # deterministic provider (off by default)

        acct_sus = analyst.assess_account(ref="acct_sus_9f3a", platform="youtube",
                                          scan=sample_account_scan_suspicious())
        acct_clean = analyst.assess_account(ref="acct_clean_22b1", platform="youtube",
                                            scan=sample_account_scan_clean())
        campaign = analyst.assess_campaign(ref="camp_7c10", platform="twitter",
                                           campaign=sample_campaign())
        narrative = analyst.assess_narrative(ref="narr_4d2e", platform="youtube",
                                             narrative=sample_narrative())
        investigation = analyst.summarize_investigation(
            ref="scan_abc123", platform="youtube",
            scan={"overall_probability": 0.61, "tier": "elevated", "confidence": 0.6,
                  "summary": "Comment section shows clustered praise and one elevated account."},
            components=[acct_sus, acct_clean, campaign, narrative],
        )

        outcomes = [
            ("A. Account (suspicious)", acct_sus),
            ("A. Account (clean)", acct_clean),
            ("B. Campaign", campaign),
            ("C. Narrative", narrative),
            ("D. Investigation Summary", investigation),
        ]
        all_valid = True
        for label, oc in outcomes:
            r = oc.response
            all_valid &= oc.valid
            print(f"=== {label} ===")
            print(f"  provider     : {oc.provider}")
            print(f"  verdict      : {r['verdict']}  | tier {r['suspicion_tier']} | "
                  f"~{int(round(r['suspicion_probability']*100))}% | conf {r['confidence_band']}")
            print(f"  evidence_for : {len(r['evidence_for'])}  evidence_against: {len(r['evidence_against'])}")
            print(f"  uncertainty  : {len(r['uncertainty'])}  next_steps: {len(r['what_would_change_this'])}")
            if r.get("coordination_label") is not None:
                print(f"  coordination : {r['coordination_label']}")
            print(f"  next step    : {r['what_would_change_this'][0]}")
            print(f"  valid        : {oc.valid}" + (f"  ERRORS: {oc.errors}" if oc.errors else ""))
            print()

        print(f"Stored {store.count()} analyst outputs for future training data "
              f"(grains: {[row['grain'] for row in store.read_all()]}).")
        print("\nALL VALID ✓" if all_valid else "\nSOME INVALID ✗")
        return 0 if all_valid else 1


if __name__ == "__main__":
    sys.exit(main())
