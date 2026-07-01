"""Instruction-tuning dataset design (AI Readiness — Phase 6).

The SCHEMA and builder for a future OMI ANALYST instruction-tuning corpus. This module **does not
train anything** — it defines the shape of a training example and converts already-produced,
Governor-gated investigations into LoRA/SFT-ready records, so the day fine-tuning is on the table
the data pipeline already exists and is quality-gated.

Each example captures the full investigative context — raw investigation, Evidence Bundle, memory
context, reasoning trace, counter-evidence, final assessment, confidence, Governor outcome, ground
truth — and exports to the chat-format SFT record (system/user/assistant messages + metadata) that
TRL-style LoRA trainers consume directly. Quality gate: only Governor-PERMITTED examples that carry
ground truth are trainable, mirroring the institutional-memory learning loop. Deterministic
train/validation split by content hash, so the holdout is stable and replayable.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.evidence.bundle import digest

TRAINING_SCHEMA_VERSION = "v1"


@dataclass(frozen=True)
class TrainingExample:
    """One instruction-tuning example — the complete, replayable record of an investigation and its
    governed assessment, plus the ground truth needed for supervised learning. Immutable."""

    id: str
    raw_investigation: dict                    # the engine payload (ComprehensiveScanResult)
    evidence_bundle: dict                      # the projected, citable bundle the analyst saw
    memory_context: list = field(default_factory=list)   # PriorContext (background, never proof)
    reasoning_trace: str = ""                  # model <think> trace, or deterministic rationale
    counter_evidence: list = field(default_factory=list)  # evidence_against
    final_assessment: dict = field(default_factory=dict)  # the schema-shaped assessment (no governance)
    confidence: dict = field(default_factory=dict)        # {band, probability, tier}
    governor_outcome: dict = field(default_factory=dict)  # {verdict, trace_id, violation_codes, ...}
    ground_truth: dict = field(default_factory=dict)      # reviewed label + provenance source
    system_prompt: str = ""                    # the specialist/judge prompt used (SFT system msg)

    @property
    def trainable(self) -> bool:
        """A training example is admissible only if the Governor PERMITTED it and it carries ground
        truth — the same quality bar the memory learning loop applies. Rejected or unlabeled
        investigations are excluded from the tuning corpus."""
        return self.governor_outcome.get("verdict") == "permit" and bool(self.ground_truth)

    @property
    def split(self) -> str:
        """Deterministic train/validation assignment by content hash (≈15% validation), so the
        holdout is stable across runs and never leaks."""
        h = digest({"id": self.id}, prefix="")
        return "validation" if (int(h[-2:], 16) < 38) else "train"


def dataset_schema() -> dict:
    """The machine-readable schema — the required fields, their meaning, and the export format —
    that a future LoRA/SFT pipeline validates against."""
    return {
        "version": TRAINING_SCHEMA_VERSION,
        "purpose": "instruction-tuning corpus for the OMI ANALYST (evidence interpretation, not "
                   "detection); LoRA/SFT-compatible; never used at inference for detection.",
        "fields": {
            "id": "stable example id",
            "raw_investigation": "the engine payload (ComprehensiveScanResult)",
            "evidence_bundle": "the projected, citable Evidence Bundle the analyst reasoned over",
            "memory_context": "institutional PriorContext (background only, no citable id)",
            "reasoning_trace": "the model's <think> trace when available, else the deterministic rationale",
            "counter_evidence": "the evidence_against column (mandatory exculpatory reasoning)",
            "final_assessment": "the schema-valid analyst assessment (verdict, evidence_for/against, "
                                "uncertainty, coordination_label, ...)",
            "confidence": "confidence band + echoed probability + tier",
            "governor_outcome": "the mandatory Governor verdict + trace id + violation codes",
            "ground_truth": "human-reviewed label + provenance source (see corpus_design)",
            "system_prompt": "the registry-resolved specialist/judge prompt used",
        },
        "quality_gate": "trainable == Governor PERMIT AND ground_truth present",
        "export_format": "chat SFT record: messages=[system, user, assistant] + metadata",
        "split": "deterministic by content hash (~15% validation holdout)",
        "compatibility": "TRL SFTTrainer / PEFT-LoRA (messages schema) and JSONL instruction format",
    }


def build_training_example(
    *, example_id: str, payload: dict, assessment: dict, system_prompt: str,
    ground_truth: dict, memory_context: list | None = None, reasoning_trace: str | None = None,
    evidence_bundle: dict | None = None,
) -> TrainingExample:
    """Assemble a :class:`TrainingExample` from an already-produced governed assessment. Pure +
    deterministic; runs no model. ``assessment`` is the ``assess_payload`` output (its ``governance``
    block supplies the Governor outcome). Never raises on a missing optional field."""
    gov = assessment.get("governance", {}) or {}
    final = {k: v for k, v in assessment.items() if k != "governance"}
    return TrainingExample(
        id=example_id,
        raw_investigation=payload,
        evidence_bundle=evidence_bundle or {},
        memory_context=list(memory_context or []),
        reasoning_trace=reasoning_trace or str(assessment.get("confidence_rationale", "")),
        counter_evidence=list(assessment.get("evidence_against", []) or []),
        final_assessment=final,
        confidence={"band": assessment.get("confidence_band"),
                    "probability": assessment.get("suspicion_probability"),
                    "tier": assessment.get("suspicion_tier")},
        governor_outcome={"verdict": gov.get("verdict"), "trace_id": gov.get("trace_id"),
                          "violation_codes": list(gov.get("violation_codes", []) or []),
                          "constitution_version": gov.get("constitution_version")},
        ground_truth=dict(ground_truth or {}),
        system_prompt=system_prompt,
    )


def to_sft_record(ex: TrainingExample) -> dict:
    """Export one example as a chat-format SFT record consumable by TRL/PEFT-LoRA. The assistant
    target is the final assessment JSON (what we want the model to learn to produce); the user turn
    carries the evidence + memory context; the system turn is the governing prompt. Metadata rides
    alongside for filtering/weighting (ground truth, Governor outcome, split) but is not trained on."""
    user_payload = {
        "evidence_bundle": ex.evidence_bundle,
        "memory_context": ex.memory_context,
        "instruction": "Interpret this OmiSphere evidence and produce one schema-valid analyst "
                       "assessment. Cite only bundle evidence ids; echo the engine number; weigh "
                       "counter-evidence; output only the JSON object.",
    }
    return {
        "messages": [
            {"role": "system", "content": ex.system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, sort_keys=True)},
            {"role": "assistant", "content": json.dumps(ex.final_assessment, ensure_ascii=False, sort_keys=True)},
        ],
        "metadata": {
            "id": ex.id, "split": ex.split, "trainable": ex.trainable,
            "ground_truth": ex.ground_truth, "governor_outcome": ex.governor_outcome,
            "confidence": ex.confidence, "reasoning_trace": ex.reasoning_trace,
            "counter_evidence_count": len(ex.counter_evidence),
        },
    }


class TrainingDataset:
    """An accumulating, deterministic set of training examples with a Governor-gated trainable view
    and JSONL export. Holds design-time data only; it never touches a model."""

    def __init__(self) -> None:
        self._examples: dict[str, TrainingExample] = {}

    def add(self, ex: TrainingExample) -> TrainingExample:
        self._examples[ex.id] = ex
        return ex

    def all(self) -> list[TrainingExample]:
        return [self._examples[k] for k in sorted(self._examples)]

    def trainable(self) -> list[TrainingExample]:
        """Only Governor-permitted, ground-truthed examples — the admissible tuning corpus."""
        return [ex for ex in self.all() if ex.trainable]

    def to_sft_records(self, *, trainable_only: bool = True) -> list[dict]:
        src = self.trainable() if trainable_only else self.all()
        return [to_sft_record(ex) for ex in src]

    def to_jsonl(self, *, trainable_only: bool = True) -> str:
        return "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True)
                         for r in self.to_sft_records(trainable_only=trainable_only))

    def summary(self) -> dict:
        allx = self.all()
        train = [ex for ex in self.trainable() if ex.split == "train"]
        val = [ex for ex in self.trainable() if ex.split == "validation"]
        return {
            "schema_version": TRAINING_SCHEMA_VERSION,
            "total": len(allx), "trainable": len(self.trainable()),
            "excluded_governor_reject_or_unlabeled": len(allx) - len(self.trainable()),
            "train": len(train), "validation": len(val),
            "controls": sum(1 for ex in self.trainable() if ex.ground_truth.get("is_control")),
        }

    def __len__(self) -> int:
        return len(self._examples)


__all__ = [
    "TRAINING_SCHEMA_VERSION", "TrainingExample", "dataset_schema", "build_training_example",
    "to_sft_record", "TrainingDataset",
]
