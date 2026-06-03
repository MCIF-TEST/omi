"""Runtime quality gate — refuse to ingest a dataset that would poison training.

The manifest excludes *known*-bad files; this gate is the generic safety net for
everything else, including future uploads not yet in the manifest. It runs on the
parsed records right before they would be persisted and HARD-FAILS only on
unambiguous poison signatures, so legitimate-but-weak sets still pass:

* **Random-label noise** — a large, ~balanced account file whose label has
  effectively zero correlation with any available feature (the 50k-row
  ``bot_detection_data.csv`` signature; corr ~0.001). The single biggest dataset
  trap in the repo.
* **Error-string contamination** — a text corpus whose "AI" class is full of API
  / HTTP error bodies labelled as AI writing.
* **Degenerate single-class** — a 2-class file collapsed to one class (untrainable).

Everything else is reported as advisory ``stats`` and never blocks. Pure stdlib.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from app.ml.datasets.records import TextRecord
from app.ml.public_import import PublicRecord

# An AI-labelled text that looks like an API/HTTP error is contamination, not AI
# writing. Conservative: requires an explicit error/status tell, not just the
# word "error" (which appears in plenty of genuine prose).
_ERROR_PATTERNS = re.compile(
    r"(error:\s*\d{3}\b|\b[45]\d{2}\s+(?:client|server)\s+error\b|client error|"
    r"server error|\btraceback \(most recent call last\)|rate limit exceeded|"
    r"quota exceeded|api\.[a-z0-9.-]+\.(?:com|org|ai|io)|"
    r"https?://\S*api\S*/v\d)",
    re.IGNORECASE,
)

_MIN_N_FOR_NOISE = 1000    # below this, "no correlation" is just a small sample
_NOISE_SIGMAS = 4.0        # best |corr| within 4σ of zero (≈ 4/√n) → random label.
                           # Chance-relative so it is correct at any N: a uniform
                           # random feature correlates with a label at ~1/√n, so a
                           # fixed cutoff would miss noise at small N and false-flag
                           # at huge N. At 50k rows the bar is ~0.018 (catches the
                           # corr≈0.001 noise file); at 1k rows it is ~0.126.
_BALANCED_MIN = 0.35       # only call it "random" when classes are ~balanced
_MIN_MINORITY_FRAC = 0.01  # < 1% minority on a 2-class file → degenerate
_ERROR_POISON_FRAC = 0.03  # ≥3% of AI texts are error strings → contaminated
_MIN_AI_FOR_POISON = 20    # need enough AI samples before judging contamination


@dataclass
class QualityReport:
    passed: bool
    kind: str
    n: int
    reasons: list[str] = field(default_factory=list)   # why it FAILED (empty if passed)
    stats: dict = field(default_factory=dict)           # advisory metrics

    @property
    def summary(self) -> str:
        if self.passed:
            return f"quality gate passed ({self.n} records)"
        return f"quality gate FAILED ({self.n} records): " + "; ".join(self.reasons)


def _abs_corr(xs: list[float], ys: list[float]) -> float:
    """|Pearson r| over paired samples; 0.0 when undefined (no variance)."""
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return 0.0
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return abs(sxy / math.sqrt(sxx * syy))


def assess_accounts(records: list[PublicRecord]) -> QualityReport:
    n = len(records)
    rep = QualityReport(passed=True, kind="accounts", n=n)
    if n == 0:
        return rep

    labels = [1.0 if r.is_bot else 0.0 for r in records]
    pos = sum(labels)
    minority = min(pos, n - pos) / n
    rep.stats["minority_frac"] = round(minority, 4)

    # Best label↔feature association across the numeric features we carry. A
    # feature is only judged when it is present on at least half the rows.
    feats: dict[str, list] = {
        "follower_count": [r.follower_count for r in records],
        "following_count": [r.following_count for r in records],
        "account_age_days": [r.account_age_days for r in records],
        "text_len": [float(sum(len(t) for t in (r.texts or []))) for r in records],
    }
    best, best_name = 0.0, ""
    for name, col in feats.items():
        paired = [(float(v), labels[i]) for i, v in enumerate(col) if v is not None]
        if len(paired) < max(2, n // 2):
            continue
        c = _abs_corr([p[0] for p in paired], [p[1] for p in paired])
        if c > best:
            best, best_name = c, name
    rep.stats["max_label_feature_corr"] = round(best, 4)
    rep.stats["max_corr_feature"] = best_name
    noise_threshold = _NOISE_SIGMAS / math.sqrt(n)
    rep.stats["noise_threshold"] = round(noise_threshold, 4)

    # Random-label poison: large, ~balanced, and nothing separates the classes
    # beyond chance (best |corr| within 4σ of zero).
    if n >= _MIN_N_FOR_NOISE and minority >= _BALANCED_MIN and best < noise_threshold:
        rep.passed = False
        rep.reasons.append(
            f"label has ~no signal (max |corr| {best:.3f} < chance {noise_threshold:.3f} "
            f"over {n} rows) — looks like random-label noise that would poison training"
        )
    # Degenerate single-class: a real 2-class file collapsed to one class.
    if 0.0 < minority < _MIN_MINORITY_FRAC:
        rep.passed = False
        rep.reasons.append(
            f"degenerate class balance (minority {minority:.2%}) — untrainable"
        )
    return rep


def assess_text(records: list[TextRecord]) -> QualityReport:
    n = len(records)
    rep = QualityReport(passed=True, kind="text", n=n)
    if n == 0:
        return rep

    ai = [r for r in records if r.is_ai]
    n_ai = len(ai)
    n_err = sum(1 for r in ai if r.text and _ERROR_PATTERNS.search(r.text))
    frac = (n_err / n_ai) if n_ai else 0.0
    rep.stats["n_ai"] = n_ai
    rep.stats["ai_error_string_frac"] = round(frac, 4)

    if n_ai >= _MIN_AI_FOR_POISON and frac >= _ERROR_POISON_FRAC:
        rep.passed = False
        rep.reasons.append(
            f"{frac:.1%} of AI-labelled texts are API/HTTP error strings — "
            "contamination that teaches 'contains an error' = AI"
        )
    return rep


def assess_records(records, kind: str) -> QualityReport:
    """Dispatch by dataset kind. Unknown kinds pass (nothing to assert)."""
    if kind == "accounts":
        return assess_accounts([r for r in records if isinstance(r, PublicRecord)])
    if kind == "text":
        return assess_text([r for r in records if isinstance(r, TextRecord)])
    return QualityReport(passed=True, kind=kind, n=len(records))
