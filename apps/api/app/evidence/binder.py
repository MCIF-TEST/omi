"""The Binder — projects existing engine outputs into a canonical Evidence Bundle.

Deterministic and model-free: it **computes nothing**, it *assembles*. Given the same
investigation payload it always produces the same bundle (and the same ``bundle_id``).
It pseudonymizes references at the boundary, assigns stable ``ev:NNNN`` ids in a fixed
traversal order, emits typed entities + relationships, and derives the epistemics layer
(contradictions / missing-evidence / unknowns) from the engine's own signed
contributions and weak signals.

The input is the engine's serialized investigation payload (the same ``payload_json``
the analyst route already consumes) — so the Binder imports nothing from the detection
engine and changes no existing behavior.
"""
from __future__ import annotations

import hashlib
from typing import Any

from .bundle import (
    BUNDLE_SCHEMA_VERSION,
    DISCRIMINATIVE_METHODS,
    Entity,
    EvidenceBundle,
    EvidenceItem,
    Relationship,
)
from .enrich import enrich_bundle

BINDER_VERSION = "binder-v1"
_PLATFORMS = frozenset({"youtube", "twitter", "reddit", "unknown"})


def _pseudo(ref: str) -> str:
    """Stable pseudonymous reference — the bundle never carries a raw handle / PII."""
    if ref and ref.startswith("sub_"):
        return ref
    return "sub_" + hashlib.sha256((ref or "").encode("utf-8")).hexdigest()[:12]


class Binder:
    """Assemble a normalized :class:`EvidenceBundle` from an engine payload."""

    version = BINDER_VERSION

    def bind(
        self,
        payload: dict[str, Any],
        *,
        grain: str = "comment_section",
        subject_ref: str,
        platform: str = "unknown",
        engine_version: str = "unknown",
        feature_schema_version: int = 1,
        enrich: bool = False,
    ) -> EvidenceBundle:
        payload = payload or {}
        plat = platform if platform in _PLATFORMS else "unknown"
        prov = {
            "platform": plat,
            "engine_version": engine_version,
            "feature_schema_version": feature_schema_version,
            "binder_version": BINDER_VERSION,
            "redaction": "pseudonymous-v1",
        }
        bundle = EvidenceBundle(
            grain=grain,
            subject={"ref": _pseudo(subject_ref), "platform": plat},
            version_binding={
                "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
                "engine_version": engine_version,
                "feature_schema_version": feature_schema_version,
                "binder_version": BINDER_VERSION,
            },
        )

        counter = {"ev": 0, "rel": 0}

        def next_ev() -> str:
            counter["ev"] += 1
            return f"ev:{counter['ev']:04d}"

        def next_rel() -> str:
            counter["rel"] += 1
            return f"rel:{counter['rel']:04d}"

        subject_id = "content:001" if grain in ("comment_section", "investigation") else "acct:001"
        subject_kind = "content" if subject_id.startswith("content") else "account"

        # --- headline (the echo source) ------------------------------------- #
        prob = float(payload.get("overall_probability") or 0.0)
        tier = str(payload.get("overall_tier") or payload.get("tier") or "low")
        conf = float(payload.get("confidence") or 0.0)
        hid = next_ev()
        bundle.evidence[hid] = EvidenceItem(
            id=hid, facet="behavioral", kind="headline", source="detection.scoring",
            originating_detector="aggregate",
            value={"overall_probability": prob, "tier": tier, "confidence": conf},
            confidence=conf, direction="neutral", subject_refs=[subject_id],
            label="headline suspicion", provenance=prov,
        )
        headline_refs = [hid]

        # --- per-detector signed contributions ------------------------------ #
        raises: list[str] = []
        lowers: list[str] = []
        for c in payload.get("contributions") or []:
            name = str(c.get("name") or "?")
            direction = c.get("direction") or "neutral"
            supplemental = bool(c.get("supplemental", False))
            eid = next_ev()
            bundle.evidence[eid] = EvidenceItem(
                id=eid, facet="behavioral", kind="contribution",
                source=f"detection.{name}", originating_detector=name,
                value={
                    "impact": float(c.get("impact") or 0.0),
                    "logit_delta": float(c.get("logit_delta") or 0.0),
                    "decorrelation_factor": float(c.get("decorrelation_factor") or 1.0),
                },
                confidence=conf, direction=direction, supplemental=supplemental,
                subject_refs=[subject_id], note=str(c.get("headline") or "")[:200],
                provenance=prov,
            )
            if not supplemental and direction == "raises":
                raises.append(eid)
            elif not supplemental and direction == "lowers":
                lowers.append(eid)

        # --- raw detector signals (optional) -------------------------------- #
        for s in payload.get("signals") or []:
            name = str(s.get("name") or "?")
            eid = next_ev()
            bundle.evidence[eid] = EvidenceItem(
                id=eid, facet="detector", kind="detector_signal",
                source=f"detection.{name}", originating_detector=name,
                value={
                    "probability": float(s.get("probability") or 0.0),
                    "confidence": float(s.get("confidence") or 0.0),
                },
                confidence=float(s.get("confidence") or 0.0),
                supplemental=bool(s.get("supplemental", False)),
                subject_refs=[subject_id], provenance=prov,
            )

        # --- coordination methods + member entities/edges ------------------- #
        coord = payload.get("coordination") or {}
        clusters = (
            (coord.get("clusters") if isinstance(coord, dict) else None)
            or ((payload.get("video") or {}).get("clusters"))
            or payload.get("clusters")
            or []
        )
        discriminative_present: list[str] = []
        for cl in clusters:
            method = cl.get("method")
            if not method:
                continue
            members = cl.get("members")
            member_count = len(members) if isinstance(members, list) else (members or 0)
            disc = method in DISCRIMINATIVE_METHODS
            eid = next_ev()
            bundle.evidence[eid] = EvidenceItem(
                id=eid, facet="coordination", kind="coordination_method",
                source="coordination.aggregate", originating_detector=method,
                value={"method": method, "members": member_count, "score": cl.get("score")},
                confidence=conf, direction="raises", discriminative=disc,
                subject_refs=[subject_id], provenance=prov,
            )
            if disc:
                discriminative_present.append(method)
            # member entities + member_of edges (pseudonymous)
            if isinstance(members, list):
                for m in members[:25]:
                    aref = _pseudo(str(m))
                    acct_id = _ensure_account(bundle, aref, plat)
                    rid = next_rel()
                    bundle.relationships.append(Relationship(
                        id=rid, type="member_of", from_=acct_id, to=eid,
                        evidence_refs=[eid],
                    ))

        # --- member commenters (pseudonymous) ------------------------------- #
        # Project commenters as member entities so component-level citations
        # (e.g. ``components.commenter.<ref>``) resolve against the bundle.
        commenters = (payload.get("video") or {}).get("commenters") or payload.get("commenters") or []
        for c in commenters[:25]:
            handle = c.get("handle") or c.get("external_id") or ""
            if handle:
                _ensure_account(bundle, _pseudo(str(handle)), plat)

        # --- subject entity -------------------------------------------------- #
        bundle.entities[subject_id] = Entity(
            id=subject_id, kind=subject_kind, ref=_pseudo(subject_ref),
            grain_role="subject", platform=plat,
            headline={"overall_probability": prob, "tier": tier, "confidence": conf},
            evidence_refs=headline_refs,
        )

        # --- epistemics ------------------------------------------------------ #
        contradictions: list[dict] = []
        if raises and lowers:
            contradictions.append({
                "between": [raises[0], lowers[0]], "kind": "raises_vs_lowers",
                "note": "the engine recorded both raising and lowering evidence",
            })
        missing = [
            {"what": str(w), "why": "weak_signal", "expected_facet": "behavioral"}
            for w in (payload.get("weak_signals") or [])
        ]
        unknowns: list[dict] = []
        single_axis = bool(
            (coord.get("single_axis_capped") if isinstance(coord, dict) else False)
            or payload.get("single_axis_capped")
        )
        if single_axis:
            unknowns.append({
                "statement": "Score was single-axis-capped; corroboration is absent.",
                "basis": "single_axis",
            })
        if clusters and not discriminative_present:
            unknowns.append({
                "statement": "Coordination signals fired but none are discriminative "
                             "(gated) — cannot distinguish hostile from benign coordination.",
                "basis": "non_discriminative_coordination",
            })
        bundle.epistemics = {
            "contradictions": contradictions,
            "missing_evidence": missing,
            "unknowns": unknowns,
        }

        # --- evidence enrichment (opt-in, additive, derived-only) ------------ #
        # Project richer structured facets from the SAME engine output. Off by default so the
        # bundle_id is unchanged; on -> derived items/edges are appended deterministically.
        if enrich:
            enrich_bundle(
                bundle, payload, mint_ev=next_ev, mint_rel=next_rel,
                subject_id=subject_id, prov=prov,
            )

        # --- capabilities ---------------------------------------------------- #
        present = {it.facet for it in bundle.evidence.values()}
        bundle.capabilities = {f: (f in present) for f in (
            "behavioral", "detector", "coordination", "narrative", "graph",
            "metadata", "historical", "risk", "ml", "label",
        )}
        return bundle


def _ensure_account(bundle: EvidenceBundle, ref: str, platform: str) -> str:
    """Return the entity id for a member account, deduped by pseudonymous ref."""
    for eid, ent in bundle.entities.items():
        if ent.kind == "account" and ent.ref == ref:
            return eid
    idx = sum(1 for e in bundle.entities.values() if e.kind == "account") + 1
    acct_id = f"acct:{idx:03d}"
    bundle.entities[acct_id] = Entity(
        id=acct_id, kind="account", ref=ref, grain_role="member", platform=platform,
    )
    return acct_id
