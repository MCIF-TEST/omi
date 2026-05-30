"""Learned signal-correlation model (GAP-02 remaining-risk fix).

Pins the data-driven decorrelation: correlations are *measured* from observed
detector outputs, the redundancy discount and independence axes follow the
measurement, and a missing/invalid artifact falls back to the hand-tuned
defaults without changing behavior.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from app.core.config import Settings
from app.detection.correlation import (
    DETECTORS,
    CorrelationModel,
    default_prior_matrix,
    get_correlation_model,
    static_axis_of,
)
from app.detection.correlation_fit import (
    fit_correlation,
    observations_from_session,
)
from app.detection.scoring import aggregate
from app.schemas import SignalResult, Tier
from app.ml.datasets.synthetic import generate_corpus
from app.ml.public_import import ingest_records
from app.storage.db import get_session

PRIOR_LOGIT = math.log(0.15 / 0.85)


def _sig(name, p, c):
    return SignalResult(name=name, probability=p, confidence=c, evidence=[])


# --- fitter --------------------------------------------------------------

def test_fit_recovers_correlated_and_independent_pairs():
    # semantic and ai_writing move together; profile is independent noise.
    rng = [0.1, 0.3, 0.5, 0.7, 0.9, 0.2, 0.4, 0.6, 0.8, 0.35, 0.55, 0.75,
           0.15, 0.45, 0.65, 0.85, 0.25, 0.5, 0.7, 0.9, 0.6, 0.4, 0.3, 0.8]
    obs = []
    for k, v in enumerate(rng):
        obs.append({
            "semantic": v,
            "ai_writing": min(0.98, max(0.02, v + 0.02)),   # near-perfectly correlated
            "profile": rng[(k * 7 + 3) % len(rng)],          # unrelated
        })
    art = fit_correlation(obs, detectors=("semantic", "ai_writing", "profile"), min_pairs=5)
    idx = {d: i for i, d in enumerate(art["detectors"])}
    sem_ai = art["matrix"][idx["semantic"]][idx["ai_writing"]]
    sem_prof = art["matrix"][idx["semantic"]][idx["profile"]]
    assert sem_ai > 0.9
    assert sem_prof < 0.5
    assert art["matrix"][idx["semantic"]][idx["semantic"]] == 1.0
    # Symmetric.
    assert art["matrix"][idx["ai_writing"]][idx["semantic"]] == sem_ai


def test_fit_low_support_pair_is_zeroed():
    obs = [{"semantic": 0.5, "ai_writing": 0.5} for _ in range(3)]
    art = fit_correlation(obs, detectors=("semantic", "ai_writing", "profile"), min_pairs=20)
    idx = {d: i for i, d in enumerate(art["detectors"])}
    # Below min_pairs → treated as independent (0.0), and support recorded.
    assert art["matrix"][idx["semantic"]][idx["ai_writing"]] == 0.0
    assert art["pair_support"][idx["semantic"]][idx["ai_writing"]] == 3


def test_negative_correlation_clamped_to_zero():
    obs = [{"semantic": v, "voice": 1.0 - v} for v in
           (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95)]
    art = fit_correlation(obs, detectors=("semantic", "voice"), min_pairs=5)
    idx = {d: i for i, d in enumerate(art["detectors"])}
    assert art["matrix"][idx["semantic"]][idx["voice"]] == 0.0  # anti-corr not discounted


# --- empirical-Bayes shrinkage toward the curated prior ------------------

def test_default_prior_matrix_encodes_groups():
    s = Settings()
    m = default_prior_matrix(s, DETECTORS, strength=0.5)
    idx = {d: i for i, d in enumerate(DETECTORS)}
    # content pair: rho = (1 - 0.55)/0.5 = 0.9; timing pair: (1 - 0.65)/0.5 = 0.7
    assert m[idx["semantic"]][idx["ai_writing"]] == pytest.approx(0.9)
    assert m[idx["temporal"]][idx["coordination"]] == pytest.approx(0.7)
    assert m[idx["temporal"]][idx["engagement"]] == pytest.approx(0.7)
    # cross-group prior is independence; diagonal is 1.
    assert m[idx["semantic"]][idx["temporal"]] == 0.0
    assert m[idx["profile"]][idx["profile"]] == 1.0


def test_no_data_pair_falls_back_to_prior_not_zero():
    """The crux of the fix: with zero observations for the timing detectors, the
    coordination–temporal cell keeps the curated prior (0.7) instead of being
    asserted independent (0.0)."""
    prior = default_prior_matrix(Settings(), DETECTORS, strength=0.5)
    idx = {d: i for i, d in enumerate(DETECTORS)}
    # Observations only exercise the content detectors; timing never fires.
    obs = [{"semantic": v, "ai_writing": v} for v in (0.2, 0.4, 0.6, 0.8)]
    art = fit_correlation(obs, prior_matrix=prior, shrink_k=30.0)
    assert art["prior_used"] is True
    coord_temp = art["matrix"][idx["temporal"]][idx["coordination"]]
    assert coord_temp == pytest.approx(0.7, abs=1e-6)   # prior preserved, not 0
    assert art["pair_support"][idx["temporal"]][idx["coordination"]] == 0


def test_measurement_dominates_prior_with_ample_support():
    """A pair the prior calls independent (profile–voice) but the data shows
    strongly correlated should move toward the measurement once support is high."""
    prior = default_prior_matrix(Settings(), DETECTORS, strength=0.5)
    idx = {d: i for i, d in enumerate(DETECTORS)}
    obs = [{"profile": v, "voice": min(0.98, v + 0.01)}
           for v in [i / 200 for i in range(5, 196)]]  # ~190 obs, corr ~1
    art = fit_correlation(obs, prior_matrix=prior, shrink_k=30.0)
    pv = art["matrix"][idx["profile"]][idx["voice"]]
    # prior was 0.0; with ~190 obs at corr~1, shrinkage lands near n/(n+k) ≈ 0.86
    assert pv > 0.8


def test_shrinkage_disabled_without_prior_is_backward_compatible():
    obs = [{"semantic": 0.5, "ai_writing": 0.5} for _ in range(3)]
    art = fit_correlation(obs, detectors=("semantic", "ai_writing", "profile"),
                          min_pairs=20)  # no prior_matrix
    idx = {d: i for i, d in enumerate(art["detectors"])}
    assert art["prior_used"] is False
    assert art["matrix"][idx["semantic"]][idx["ai_writing"]] == 0.0  # old behavior


# --- learned model behavior ----------------------------------------------

def _learned_artifact(detectors, pairs, **over):
    """Build an artifact dict with given pairwise correlations (symmetric)."""
    n = len(detectors)
    idx = {d: i for i, d in enumerate(detectors)}
    matrix = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for (a, b), r in pairs.items():
        matrix[idx[a]][idx[b]] = matrix[idx[b]][idx[a]] = r
    return {
        "version": 1, "detectors": list(detectors), "matrix": matrix,
        "n_observations": 500, "strength": over.get("strength", 0.5),
        "floor": over.get("floor", 0.15),
        "axis_threshold": over.get("axis_threshold", 0.5),
    }


def test_learned_axes_follow_measured_correlation():
    # temporal–coordination measured as INDEPENDENT (0.1) even though the default
    # model groups them — this is the risk-3 fix in action.
    art = _learned_artifact(
        ("temporal", "coordination", "semantic", "ai_writing"),
        {("semantic", "ai_writing"): 0.9, ("temporal", "coordination"): 0.1},
    )
    model = CorrelationModel.from_artifact(art)
    assert model.axis_of("semantic") == model.axis_of("ai_writing")     # clustered
    assert model.axis_of("temporal") != model.axis_of("coordination")   # split apart


def test_learned_factor_is_continuous_in_correlation():
    art = _learned_artifact(("semantic", "ai_writing"), {("semantic", "ai_writing"): 0.6})
    model = CorrelationModel.from_artifact(art)
    signals = [_sig("semantic", 0.9, 0.9), _sig("ai_writing", 0.8, 0.8)]
    weights = {"semantic": 1.2, "ai_writing": 0.8}
    factors, notes = model.compute_factors(signals, weights, PRIOR_LOGIT)
    # Weaker member discounted by (1 - rho*strength) = 1 - 0.6*0.5 = 0.7.
    assert factors["semantic"] == 1.0
    assert factors["ai_writing"] == pytest.approx(0.7)
    assert notes and "fitted signal-correlation model" in notes[0]


def test_learned_independent_pair_gets_no_discount():
    art = _learned_artifact(("temporal", "coordination"), {("temporal", "coordination"): 0.0})
    model = CorrelationModel.from_artifact(art)
    signals = [_sig("temporal", 0.9, 0.9), _sig("coordination", 0.9, 0.9)]
    weights = {"temporal": 1.0, "coordination": 0.9}
    factors, notes = model.compute_factors(signals, weights, PRIOR_LOGIT)
    assert factors == {"temporal": 1.0, "coordination": 1.0}
    assert notes == []


def test_invalid_artifact_shape_rejected():
    with pytest.raises(ValueError):
        CorrelationModel.from_artifact({"detectors": ["a", "b"], "matrix": [[1.0]]})


# --- runtime loading + fallback ------------------------------------------

def test_loads_learned_model_from_path(tmp_path: Path):
    art = _learned_artifact(("temporal", "coordination"), {("temporal", "coordination"): 0.0})
    p = tmp_path / "corr.json"
    p.write_text(json.dumps(art), encoding="utf-8")
    s = Settings(correlation_model_path=str(p))
    model = get_correlation_model(s)
    assert model.source == "learned"


def test_falls_back_to_default_when_absent(tmp_path: Path):
    s = Settings(correlation_model_path=str(tmp_path / "does_not_exist.json"))
    model = get_correlation_model(s)
    assert model.source == "default"
    # Default axes match the static helper.
    assert model.axis_of("semantic") == static_axis_of("semantic")


def test_falls_back_to_default_when_malformed(tmp_path: Path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    s = Settings(correlation_model_path=str(p))
    assert get_correlation_model(s).source == "default"


# --- end-to-end: learned model changes aggregation -----------------------

def test_learned_model_splits_axis_allowing_high(tmp_path: Path):
    """Under the default model, temporal+coordination share an axis and two of
    them alone are capped below HIGH. With a learned model that measures them as
    independent, the same two confident signals corroborate and may reach HIGH —
    proving the axis assignment is now data-driven."""
    sigs = [_sig("temporal", 0.95, 0.95), _sig("coordination", 0.95, 0.95)]
    default_res = aggregate(sigs, Settings())
    assert default_res.tier != Tier.HIGH  # same-axis cap under defaults

    art = _learned_artifact(("temporal", "coordination"), {("temporal", "coordination"): 0.0})
    p = tmp_path / "corr.json"
    p.write_text(json.dumps(art), encoding="utf-8")
    learned_res = aggregate(sigs, Settings(correlation_model_path=str(p)))
    assert learned_res.tier == Tier.HIGH


# --- integration: fit from the real DB pipeline --------------------------

def test_fit_from_ingested_synthetic_corpus():
    """The whole loop is runnable: synthetic ground truth → ingested scans →
    fitted correlation matrix with real observations."""
    recs = generate_corpus(n_per_persona=12)
    with get_session() as session:
        ingest_records(session, recs, dataset_name="synthetic", source="synthetic")
        obs = observations_from_session(session, only_labeled=True)
    assert len(obs) > 0
    art = fit_correlation(obs, min_pairs=5)
    assert art["n_observations"] == len(obs)
    n = len(art["detectors"])
    assert n >= 8  # grows as new detectors are added
    # Diagonal is 1.0, matrix is symmetric and in range.
    for i in range(n):
        assert art["matrix"][i][i] == 1.0
        for j in range(n):
            assert art["matrix"][i][j] == art["matrix"][j][i]
            assert 0.0 <= art["matrix"][i][j] <= 1.0
