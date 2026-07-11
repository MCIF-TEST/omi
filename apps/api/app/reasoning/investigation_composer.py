"""The Investigation Composer (frozen architecture) — assembles the ONE InvestigationPackage.

The Composer is the single place the reasoning path turns read evidence into the canonical,
**complete, model-facing evidence object**. It consumes ONLY an immutable :class:`EvidenceSnapshot`
(the Evidence Repository's projection) and outputs ONLY an immutable, content-addressed
:class:`InvestigationPackage` — the full-fidelity seven-bundle :class:`EvidenceBundleSet` plus clean
provenance metadata and a stable evidence index.

It is PURE ASSEMBLY. It performs no reasoning, no heuristic interpretation, no detector execution, no
scoring, no endpoint call, no prompt construction, no transport serialization, and no UI formatting. It
knows nothing about Hugging Face, GitHub, Mistral, the Runtime, the Governor, the Website, or any API
route — it imports only the evidence-bundle layer and the content-addressing primitive.

The package it emits is the model-facing evidence input for the single AI investigation inference: the
Prompt Builder renders THIS package (budgeted + normalized) into exactly one request. The package
itself is **complete and lossless** — token budgeting and normalization are downstream *rendering*
concerns, never Composer concerns, so the package never pre-decides what the model is allowed to see.

The package must NEVER carry a conclusion: no ``intent_label``, ``suspected_intent``, ``risk_level``,
heuristic summary, verdict, recommendation, or any deterministic prose interpretation. The
evidence-bundle layer already upholds this (Ruling 3 + the P3.0 no-prose invariant); the Composer only
assembles those bundles, so the property holds by construction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.evidence.bundle import digest
from app.reasoning.evidence_bundles import (
    EvidenceBundleSet,
    InvestigationSummaryBundle,
    build_evidence_bundles,
)

if TYPE_CHECKING:  # decouple at runtime — the Composer transforms any snapshot-shaped projection
    from app.reasoning.evidence_repository import EvidenceSnapshot

INVESTIGATION_PACKAGE_SCHEMA_VERSION = 1


def _sampling_disclosure(payload: dict, bundles: EvidenceBundleSet) -> dict:
    """A data-quality DISCLOSURE (not interpretation): how many raw entities the snapshot observed vs
    how many the evidence carries. The upstream Evidence layer caps very large investigations (a fixed
    per-section limit); when it does, that truncation must be DISCLOSED — the contract forbids a hard
    truncation without disclosure, and names 'sampling disclosure' as evidence to preserve. Pure counts.
    """
    payload = payload or {}
    video = payload.get("video") if isinstance(payload.get("video"), dict) else {}
    raw_commenters = (video.get("commenters") or payload.get("commenters") or [])
    coord = payload.get("coordination") if isinstance(payload.get("coordination"), dict) else {}
    raw_clusters = (coord.get("clusters") or video.get("clusters") or payload.get("clusters") or [])
    raw_comments = 0
    for c in raw_commenters if isinstance(raw_commenters, list) else []:
        if isinstance(c, dict):
            raw_comments += len(c.get("recent_activity") or [])

    def _obs(seq) -> int:
        return len(seq) if isinstance(seq, list) else 0

    domains = {
        "accounts": {"observed": _obs(raw_commenters), "carried": bundles.account.count},
        "clusters": {"observed": _obs(raw_clusters), "carried": bundles.coordination.cluster_count},
        "comments": {"observed": raw_comments, "carried": bundles.comment.comment_count},
    }
    truncated = any(d["observed"] > d["carried"] for d in domains.values())
    return {"truncated_upstream": truncated, "domains": domains}


def _evidence_index(bundles: EvidenceBundleSet) -> tuple[str, ...]:
    """The complete set of stable, citable evidence ids in the package — every bundle id plus every
    structural entity ref (account ``sub_``, cluster ``cl:``, narrative ``nr:``). Deterministically
    ordered (sorted) so it is a pure function of the evidence. It is the package's self-contained
    manifest of what a model citation may resolve against; it invents nothing not already in a bundle.
    """
    ids: set[str] = set()
    for b in bundles.stage_bundles().values():
        ids.add(b.bundle_id())
    for a in bundles.account.accounts:
        ids.add(a.author_ref)
    for c in bundles.commenter_history.commenters:
        ids.add(c.author_ref)
    for cl in bundles.coordination.clusters:
        ids.add(cl.cluster_ref)
    for n in bundles.narrative.narratives:
        ids.add(n.narrative_ref)
    return tuple(sorted(ids))


@dataclass(frozen=True)
class InvestigationPackage:
    """The complete, immutable, content-addressed evidence package for ONE investigation — the
    model-facing evidence input to the single AI investigation inference.

    Holds the full-fidelity seven-bundle :class:`EvidenceBundleSet` (the complete measured evidence,
    losslessly — nothing budgeted away, no provenance dropped) plus clean provenance metadata (the
    platform, the post identity, the inputs actually provided, the source context id and snapshot id)
    and a stable :attr:`evidence_index`.

    Content-addressed by :attr:`package_id` (``ipkg:``) — a pure function of the evidence identity (the
    seven bundle ids + the metadata + the source snapshot id), excluding wall-clock — so any assessment
    can name exactly which evidence package it reasoned from. Carries ONLY measured evidence: no
    verdict, no heuristic interpretation, no prose conclusion (upheld by the bundle layer).
    """

    bundles: EvidenceBundleSet
    platform: str
    post_content_id: str | None
    inputs_provided: tuple[str, ...]
    context_id: str
    snapshot_id: str
    evidence_index: tuple[str, ...]
    sampling: dict = field(default_factory=dict)   # upstream-truncation DISCLOSURE (pure counts)
    schema_version: int = INVESTIGATION_PACKAGE_SCHEMA_VERSION
    package_id: str = ""

    # --- accessors (the package is the sole handle a downstream layer needs) --------------------- #
    def summary_bundle(self) -> InvestigationSummaryBundle:
        """The DAG-root investigation-summary bundle (the whole-investigation synthesis evidence)."""
        return self.bundles.summary

    def stage_bundles(self) -> dict[str, Any]:
        """The seven canonical bundles keyed by stage name (summary included)."""
        return self.bundles.stage_bundles()

    def stage_bundle(self, stage: str) -> Any:
        """One stage's evidence bundle by name (e.g. ``"account_analysis"``)."""
        bundles = self.bundles.stage_bundles()
        try:
            return bundles[stage]
        except KeyError:
            raise KeyError(f"no evidence bundle for stage {stage!r}; "
                           f"stages: {tuple(sorted(bundles))}") from None

    def component_ids(self) -> dict[str, str]:
        """The content address of every bundle keyed by stage — the package's DAG in id form."""
        return {name: b.bundle_id() for name, b in self.bundles.stage_bundles().items()}

    def to_dict(self) -> dict[str, Any]:
        """A fully serializable projection of the complete package (bundles + metadata + index)."""
        return {
            "package_id": self.package_id,
            "schema_version": self.schema_version,
            "platform": self.platform,
            "post_content_id": self.post_content_id,
            "inputs_provided": list(self.inputs_provided),
            "context_id": self.context_id,
            "snapshot_id": self.snapshot_id,
            "evidence_index": list(self.evidence_index),
            "sampling": self.sampling,
            "bundles": self.bundles.to_dict(),
        }


class InvestigationComposer:
    """The ONE composer: assembles an immutable :class:`InvestigationPackage` from an
    :class:`EvidenceSnapshot`. Pure assembly — no reasoning, no scoring, no model, no prompt, no
    endpoint, no UI. Imports only the evidence-bundle layer and the content hash."""

    def compose(self, snapshot: "EvidenceSnapshot") -> InvestigationPackage:
        """Assemble the complete, content-addressed InvestigationPackage from a frozen evidence
        snapshot. Deterministic + side-effect free: the same snapshot yields the same ``package_id``.
        The full seven-bundle evidence set is carried losslessly — budgeting happens downstream."""
        context = snapshot.context
        bundles = build_evidence_bundles(context)
        inv = context.investigation
        index = _evidence_index(bundles)
        sampling = _sampling_disclosure(snapshot.payload, bundles)
        package_id = digest(
            {
                "bundles": {name: b.bundle_id()
                            for name, b in bundles.stage_bundles().items()},
                "platform": inv.platform,
                "post_content_id": context.post.content_id,
                "inputs_provided": list(inv.inputs_provided),
                "context_id": context.context_id,
                "snapshot_id": snapshot.snapshot_id,
                "sampling": sampling,
                "schema_version": INVESTIGATION_PACKAGE_SCHEMA_VERSION,
            },
            prefix="ipkg:",
        )
        return InvestigationPackage(
            bundles=bundles,
            platform=inv.platform,
            post_content_id=context.post.content_id,
            inputs_provided=tuple(inv.inputs_provided),
            context_id=context.context_id,
            snapshot_id=snapshot.snapshot_id,
            evidence_index=index,
            sampling=sampling,
            package_id=package_id,
        )


def compose_investigation_package(snapshot: "EvidenceSnapshot") -> InvestigationPackage:
    """Convenience entry — compose the InvestigationPackage for one evidence snapshot."""
    return InvestigationComposer().compose(snapshot)


__all__ = [
    "INVESTIGATION_PACKAGE_SCHEMA_VERSION",
    "InvestigationPackage",
    "InvestigationComposer",
    "compose_investigation_package",
]
