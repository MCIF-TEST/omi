"""Benchmark the rule-based AI-writing detector against a labeled text corpus.

Same philosophy as the other benchmarks in this package: one pure metric
function the CLI, the pytest gate, and (optionally) an admin endpoint all share.

For every labeled text sample we run :func:`app.detection.ai_writing.analyze_ai_writing`
on a single synthetic post and compare its probability to the ground-truth
human-vs-AI label.

A crucial, honest property surfaces here: the rule detector only fires on
long-form text (``MIN_WORDS_FOR_AI_WRITING`` words and >=6 sentences). Short
social comments — the bulk of these datasets — make it *abstain* (confidence
0, probability 0.5). So the report separates:

* **coverage** — fraction of samples the detector was willing to score, and
* **accuracy on covered** — how well it does when it does fire.

That separation is the finding that motivates the learned text head: the rule
detector is precise but low-coverage on short text, and the exported corpus is
what trains the head that closes the gap.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.detection.ai_writing import analyze_ai_writing
from app.ml.datasets.records import TextRecord
from app.schemas import Post

_DECISION_THRESHOLD = 0.5


@dataclass
class _Scored:
    is_ai: bool
    probability: float
    confidence: float


def _score_records(records: list[TextRecord]) -> list[_Scored]:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    out: list[_Scored] = []
    for r in records:
        if not r.text.strip():
            continue
        post = Post(id=r.external_id, author_handle="corpus", text=r.text, created_at=base)
        sig = analyze_ai_writing([post])
        out.append(_Scored(is_ai=r.is_ai, probability=sig.probability, confidence=sig.confidence))
    return out


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


def _roc_auc(scored: list[_Scored]) -> float | None:
    """Rank-based (Mann-Whitney) ROC-AUC: P(score_ai > score_human)."""
    pos = [s.probability for s in scored if s.is_ai]
    neg = [s.probability for s in scored if not s.is_ai]
    if not pos or not neg:
        return None
    ranked = sorted(((s.probability, s.is_ai) for s in scored), key=lambda x: x[0])
    rank_sum = 0.0
    i = 0
    n = len(ranked)
    while i < n:
        j = i
        while j < n and ranked[j][0] == ranked[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0  # 1-based average rank for the tie group
        for k in range(i, j):
            if ranked[k][1]:
                rank_sum += avg_rank
        i = j
    n_pos, n_neg = len(pos), len(neg)
    auc = (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    return round(auc, 4)


def evaluate_ai_writing(records: list[TextRecord]) -> dict:
    scored = _score_records(records)
    n_total = len(scored)
    covered = [s for s in scored if s.confidence > 0.0]
    n_cov = len(covered)

    def _metrics(subset: list[_Scored]) -> dict:
        if not subset:
            return {"n": 0}
        tp = sum(1 for s in subset if s.is_ai and s.probability > _DECISION_THRESHOLD)
        fp = sum(1 for s in subset if not s.is_ai and s.probability > _DECISION_THRESHOLD)
        fn = sum(1 for s in subset if s.is_ai and s.probability <= _DECISION_THRESHOLD)
        tn = sum(1 for s in subset if not s.is_ai and s.probability <= _DECISION_THRESHOLD)
        precision, recall, f1 = _prf(tp, fp, fn)
        accuracy = (tp + tn) / len(subset)
        brier = sum((s.probability - (1.0 if s.is_ai else 0.0)) ** 2 for s in subset) / len(subset)
        n_ai = sum(1 for s in subset if s.is_ai)
        majority = max(n_ai, len(subset) - n_ai) / len(subset)
        return {
            "n": len(subset),
            "accuracy": round(accuracy, 4),
            "ai_precision": round(precision, 4),
            "ai_recall": round(recall, 4),
            "ai_f1": round(f1, 4),
            "brier": round(brier, 4),
            "majority_class_rate": round(majority, 4),
            "roc_auc": _roc_auc(subset),
            "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        }

    n_ai_total = sum(1 for s in scored if s.is_ai)
    return {
        "n_total": n_total,
        "n_ai": n_ai_total,
        "n_human": n_total - n_ai_total,
        "n_covered": n_cov,
        "coverage": round(n_cov / n_total, 4) if n_total else 0.0,
        "mean_confidence": round(sum(s.confidence for s in scored) / n_total, 4) if n_total else 0.0,
        "overall": _metrics(scored),       # abstentions count as p=0.5 (predict human)
        "covered": _metrics(covered),      # only where the detector actually fired
        "decision_threshold": _DECISION_THRESHOLD,
    }


def evaluate_ai_writing_default(
    root: Path | None = None,
    *,
    limit_per_file: int | None = None,
) -> dict:
    """Load the text corpus from the datasets folder and evaluate. Returns a
    report with ``n_total == 0`` (and a message) when no text datasets exist."""
    from app.ml.datasets.paths import default_datasets_dir
    from app.ml.datasets.text_corpus import load_text_records

    root = root or default_datasets_dir()
    records = load_text_records(root, limit_per_file=limit_per_file)
    if not records:
        return {"n_total": 0, "message": f"No text datasets found under {root}."}
    report = evaluate_ai_writing(records)
    report["datasets_root"] = str(root)
    return report
