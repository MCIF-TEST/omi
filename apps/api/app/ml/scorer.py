"""Serving-side learned scorer.

Loads a trained model artifact and re-scores a rule-engine ScanResult by
blending the model's inauthenticity probability with the hand-tuned score.
Everything here degrades gracefully:

* No model file configured            → returns the input ScanResult unchanged.
* Model libs (lightgbm/joblib) absent → logs once, returns input unchanged.
* Schema-version mismatch             → refuses the model, returns input.

So this module is safe to ship and wire into the hot path *before* any model
exists: it is a no-op until an artifact is present and the feature flag is on.

The artifact is a small bundle (dict) saved with ``joblib``:

    {
      "feature_schema_version": 1,
      "model": <lightgbm.Booster or sklearn classifier with predict_proba>,
      "kind": "lightgbm" | "sklearn",
      "trained_at": "2026-...",
      "metrics": {...},          # held-out metrics for provenance
    }

The DistilBERT text head is optional and loaded separately via
``transformers`` only when ``ml_text_model_path`` is set; if unavailable the
scorer uses the tabular model alone.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.ml.features import FEATURE_SCHEMA_VERSION, build_feature_vector
from app.schemas import Profile, ScanResult, SignalResult, Tier

_log = logging.getLogger("omi.ml.scorer")

# Tier cutoffs — identical to app.detection.scoring._tier_for so a blended
# probability maps to tiers the rest of the system already understands.
_TIER_CUTS = [(0.25, Tier.LOW), (0.50, Tier.MODERATE), (0.75, Tier.ELEVATED)]


def _tier_for(p: float) -> Tier:
    for cut, tier in _TIER_CUTS:
        if p < cut:
            return tier
    return Tier.HIGH


@dataclass
class _LoadedModel:
    model: object
    kind: str
    schema_version: int
    metrics: dict


class MLScorer:
    """Singleton-ish loader + re-scorer. Thread-safe lazy load."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded: _LoadedModel | None = None
        self._load_attempted = False
        self._text_pipeline = None
        self._text_load_attempted = False

    # -- loading -----------------------------------------------------------

    def _ensure_loaded(self, settings: Settings) -> _LoadedModel | None:
        if self._loaded is not None:
            return self._loaded
        if self._load_attempted:
            return None  # already failed once; don't spam retries
        with self._lock:
            if self._loaded is not None:
                return self._loaded
            if self._load_attempted:
                return None
            self._load_attempted = True
            path = (settings.ml_model_path or "").strip()
            if not path:
                return None
            try:
                import joblib  # type: ignore
            except Exception:  # noqa: BLE001
                _log.warning("ml_model_path set but joblib not installed; ML scoring disabled.")
                return None
            try:
                bundle = joblib.load(path)
                schema = int(bundle.get("feature_schema_version", -1))
                if schema != FEATURE_SCHEMA_VERSION:
                    _log.error(
                        "ML model schema v%s != serving schema v%s; refusing to load %s",
                        schema, FEATURE_SCHEMA_VERSION, path,
                    )
                    return None
                self._loaded = _LoadedModel(
                    model=bundle["model"],
                    kind=bundle.get("kind", "lightgbm"),
                    schema_version=schema,
                    metrics=bundle.get("metrics", {}),
                )
                _log.info("Loaded ML model (kind=%s, schema=v%s) from %s",
                          self._loaded.kind, schema, path)
                return self._loaded
            except Exception as e:  # noqa: BLE001
                _log.exception("Failed to load ML model from %s: %s", path, e)
                return None

    def _predict_proba(self, model: _LoadedModel, features: list[float]) -> float | None:
        """Return P(inauthentic) in [0, 1], or None if prediction fails."""
        try:
            X = [features]
            if model.kind == "lightgbm":
                # Booster.predict returns the positive-class probability for
                # binary objective.
                pred = model.model.predict(X)  # type: ignore[attr-defined]
                return float(pred[0])
            # sklearn-style classifier with predict_proba
            proba = model.model.predict_proba(X)  # type: ignore[attr-defined]
            return float(proba[0][1])
        except Exception as e:  # noqa: BLE001
            _log.warning("ML prediction failed, falling back to rule score: %s", e)
            return None

    # -- text head (optional) ---------------------------------------------

    def _ensure_text(self, settings: Settings):
        if self._text_pipeline is not None or self._text_load_attempted:
            return self._text_pipeline
        self._text_load_attempted = True
        path = (settings.ml_text_model_path or "").strip()
        if not path:
            return None
        try:
            from transformers import pipeline  # type: ignore
            self._text_pipeline = pipeline("text-classification", model=path, truncation=True)
            _log.info("Loaded ML text head from %s", path)
        except Exception as e:  # noqa: BLE001
            _log.warning("Text head unavailable (%s); using tabular model only.", e)
            self._text_pipeline = None
        return self._text_pipeline

    def _text_proba(self, settings: Settings, texts: list[str]) -> float | None:
        pipe = self._ensure_text(settings)
        if pipe is None or not texts:
            return None
        try:
            sample = "\n".join(t for t in texts if t)[:2000]
            if not sample:
                return None
            out = pipe(sample)[0]
            label = str(out.get("label", "")).lower()
            score = float(out.get("score", 0.0))
            # Convention: positive class label contains "ai" / "bot" / "1" /
            # "inauthentic". Map to P(inauthentic).
            positive = any(k in label for k in ("ai", "bot", "fake", "inauthentic", "label_1", "1"))
            return score if positive else 1.0 - score
        except Exception as e:  # noqa: BLE001
            _log.warning("Text-head prediction failed: %s", e)
            return None

    # -- public API --------------------------------------------------------

    def is_active(self, settings: Settings | None = None) -> bool:
        settings = settings or get_settings()
        return bool(settings.use_ml_scorer) and self._ensure_loaded(settings) is not None

    def rescore(
        self,
        scan: ScanResult,
        *,
        profile: Profile | None = None,
        post_count: int = 0,
        texts: list[str] | None = None,
        settings: Settings | None = None,
    ) -> ScanResult:
        """Return a possibly re-scored copy of ``scan``.

        Blends the model's P(inauthentic) with the rule engine's
        ``overall_probability`` using ``ml_blend_weight`` (0 = ignore model,
        1 = trust model fully). Tier is recomputed from the blended value. The
        original rule score is preserved in a ``ml_meta`` signal for audit.
        """
        settings = settings or get_settings()
        if not settings.use_ml_scorer:
            return scan
        loaded = self._ensure_loaded(settings)
        if loaded is None:
            return scan

        features = build_feature_vector(scan, profile=profile, post_count=post_count)
        tab_p = self._predict_proba(loaded, features)
        if tab_p is None:
            return scan

        # Optional text head: average with tabular when present.
        txt_p = self._text_proba(settings, texts or [])
        model_p = tab_p if txt_p is None else (0.6 * tab_p + 0.4 * txt_p)

        w = max(0.0, min(1.0, settings.ml_blend_weight))
        blended = (1.0 - w) * scan.overall_probability + w * model_p
        blended = max(0.0, min(1.0, blended))

        new_signals = list(scan.signals)
        new_signals.append(SignalResult(
            name="ml_meta",
            probability=model_p,
            confidence=min(1.0, 0.5 + 0.5 * w),
            evidence=[
                f"Learned model P(inauthentic)={model_p:.2f} "
                f"(tabular={tab_p:.2f}" + (f", text={txt_p:.2f}" if txt_p is not None else "") + ")",
                f"Blended with rule engine at weight {w:.2f}: "
                f"{scan.overall_probability:.2f} → {blended:.2f}",
            ],
            sub_signals={
                "model_probability": round(model_p, 4),
                "tabular_probability": round(tab_p, 4),
                "rule_probability": round(scan.overall_probability, 4),
                "blend_weight": round(w, 4),
            },
        ))

        return scan.model_copy(update={
            "overall_probability": blended,
            "tier": _tier_for(blended),
            "signals": new_signals,
        })


# Process-wide singleton.
_SCORER = MLScorer()


def get_scorer() -> MLScorer:
    return _SCORER
