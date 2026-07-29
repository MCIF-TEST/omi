"""The Constitutional Governor — deterministic validation pipeline (S0–S11).

Implements the decidable subset of ``OMI_CONSTITUTIONAL_GOVERNOR_V1`` §C: each
constitutional principle is a machine-checkable invariant over the (Ruling, Evidence
Bundle) pair. The Governor runs every stage, collects all violation codes, and returns a
PERMIT/REJECT :class:`ValidationTrace`. It is model-free and **never edits** the ruling —
a violation rejects to the deterministic Floor.
"""
from __future__ import annotations

from typing import Any

from app.evidence.bundle import DISCRIMINATIVE_METHODS, EvidenceBundle, digest

from .audit import ValidationTrace

CONSTITUTION_VERSION = 1

# Immutable-core banned phrasings (behavior, not persons; probabilistic, not absolute).
#: Phrasings that assert identity, intent, or certainty rather than describing measured behaviour.
#: These matter more than they look: per-account prose gets quoted publicly, about named real
#: accounts, and the difference between "is a bot" and "behaves consistently with automation" is the
#: difference between an accusation and a finding.
#:
#: NOTE ON REACH. This lint (Governor stage S9) sees the investigation-level `headline`, `assessment`
#: and evidence claims. It does NOT see `commenter_assessments[].assessment`, and the comprehensive
#: path runs with adjudication="schema_only", so on the live route the Governor is not gating the
#: model's prose at all. The protocol's `checkable_claims` block is what actually holds this line
#: today. Extending enforcement to per-account text is worth doing and is not done here.
BANNED_PHRASES = (
    "is a bot", "are bots", "is fake", "definitely fake", "this person",
    "paid troll", "confirmed bot", "100% bot", "guilty", "without a doubt",
    # Certainty
    "proves that", "proof that", "no doubt", "certainly a", "undoubtedly",
    "clearly a bot", "obviously a bot", "beyond question",
    # Identity and intent, which the evidence can never establish
    "was hired", "was paid to", "is employed by", "works for a farm",
    "is operated by", "the owner of this account", "real identity",
)

_BANDS = {"insufficient": 0, "low": 1, "moderate": 2, "high": 3}
_REQUIRED = (
    "verdict", "suspicion_tier", "suspicion_probability", "confidence_band",
    "evidence_for", "evidence_against", "uncertainty", "what_would_change_this",
)


def _engine_band(conf: float) -> str:
    if conf < 0.2:
        return "insufficient"
    if conf < 0.45:
        return "low"
    if conf < 0.7:
        return "moderate"
    return "high"


class Governor:
    """Validate a candidate assessment against its Evidence Bundle. Deterministic."""

    constitution_version = CONSTITUTION_VERSION

    def validate(
        self,
        ruling: dict[str, Any],
        bundle: EvidenceBundle,
        *,
        corroboration: dict[str, Any] | None = None,
    ) -> ValidationTrace:
        corr = corroboration or ruling.get("corroboration") or {}
        codes: list[str] = []
        stages: list[dict[str, Any]] = []

        def stage(sid: str, name: str, passed: bool, detail: str = "", code: str | None = None) -> None:
            stages.append({"stage": sid, "name": name, "pass": bool(passed), "detail": detail})
            if not passed and code:
                codes.append(code)

        headline = bundle.headline()
        ev_for = ruling.get("evidence_for") or []
        ev_against = ruling.get("evidence_against") or []
        ev_items = list(ev_for) + list(ev_against)

        # S0 — intake & integrity
        missing = [f for f in _REQUIRED if f not in ruling]
        stage("S0", "intake_integrity", not missing,
              f"missing fields: {missing}" if missing else "ok", "corrupted_input")

        # S1 — version binding (recorded, never fails here)
        stage("S1", "version_binding", True, "bound")

        # S2 — citation resolution (no fabrication)
        unresolved = [r for it in ev_items for r in (it.get("evidence_refs") or []) if not bundle.resolve(r)]
        stage("S2", "citation_resolution", not unresolved,
              f"unresolved: {unresolved[:5]}" if unresolved else "ok", "fabrication")

        # S3 — evidence integrity (every item has a claim and >=1 ref)
        bad = [it for it in ev_items if not it.get("claim") or not it.get("evidence_refs")]
        stage("S3", "evidence_integrity", not bad,
              f"{len(bad)} item(s) without claim/refs" if bad else "ok", "fabrication")

        # S4 — echo-guard (suspicion echoed from the engine, not recomputed)
        try:
            prob_ok = abs(float(ruling.get("suspicion_probability"))
                          - float(headline.get("overall_probability", -1.0))) < 1e-6
        except (TypeError, ValueError):
            prob_ok = False
        tier_ok = ruling.get("suspicion_tier") == headline.get("tier")
        stage("S4", "echo_guard", prob_ok and tier_ok,
              f"prob_ok={prob_ok} tier_ok={tier_ok}", "engine_override")

        # S5 — corroboration gate
        label = ruling.get("coordination_label")
        disc = [m for m in (corr.get("discriminative_methods") or []) if m in DISCRIMINATIVE_METHODS]
        single = bool(corr.get("single_axis_capped"))
        gate_ok = True
        if label in ("coordinated", "manipulation_network"):
            gate_ok = bool(disc) and not single
        if ruling.get("verdict") == "confirmed_bot_ring":
            # confirmed_* requires a human/platform (E1/E2) anchor — a label facet.
            gate_ok = gate_ok and bool(bundle.capabilities.get("label", False))
        stage("S5", "corroboration_gate", gate_ok,
              f"label={label} discriminative={disc} single_axis={single}", "gate_breach")

        # S6 — memory boundary (no ko: prior cited as suspicion-raising evidence)
        ko_for = [r for it in ev_for for r in (it.get("evidence_refs") or []) if str(r).startswith("ko:")]
        stage("S6", "memory_boundary", not ko_for,
              f"ko refs in evidence_for: {ko_for}" if ko_for else "ok", "memory_overreach")

        # S7 — confidence calibration (valid band; <= engine band; insufficient => inconclusive)
        band = ruling.get("confidence_band")
        conf_ok = band in _BANDS
        if conf_ok:
            max_band = _engine_band(float(headline.get("confidence", 0.0) or 0.0))
            conf_ok = _BANDS[band] <= _BANDS[max_band]
            if band == "insufficient" and ruling.get("verdict") != "inconclusive":
                conf_ok = False
        stage("S7", "confidence", conf_ok, f"band={band}", "confidence_violation")

        # S8 — uncertainty + contradiction completeness
        unc = ruling.get("uncertainty") or []
        need_unc = bool(bundle.epistemics.get("missing_evidence") or bundle.epistemics.get("unknowns"))
        bundle_has_lowers = any(it.direction == "lowers" for it in bundle.evidence.values())
        rationale = str(ruling.get("confidence_rationale") or "").lower()
        ea_ok = bool(ev_against) or ("no exculpatory" in rationale)
        s8_ok = (bool(unc) or not need_unc) and (ea_ok or not bundle_has_lowers)
        stage("S8", "uncertainty_contradiction", s8_ok,
              f"unc={len(unc)} evidence_against={len(ev_against)}", "suppressed_counter_evidence")

        # S9 — policy lints (banned phrasing; supplemental never raises suspicion)
        text = " ".join([
            str(ruling.get("headline") or ""),
            str(ruling.get("assessment") or ""),
            *[str(it.get("claim") or "") for it in ev_items],
        ]).lower()
        banned = [p for p in BANNED_PHRASES if p in text]
        supp_detectors = {it.originating_detector for it in bundle.evidence.values() if it.supplemental}
        supp_in_for = [it.get("signal") for it in ev_for if it.get("signal") in supp_detectors]
        s9_ok = not banned and not supp_in_for
        stage("S9", "policy_lints", s9_ok,
              f"banned={banned} supplemental_in_for={supp_in_for}", "policy_violation")

        # S10 — falsifiability
        wwc = ruling.get("what_would_change_this") or []
        stage("S10", "falsifiability", bool(wwc), "ok" if wwc else "empty", "non_falsifiable")

        # S11 — constitutional verdict
        verdict = "permit" if not codes else "reject"
        return ValidationTrace(
            verdict=verdict,
            violation_codes=sorted(set(codes)),
            stage_results=stages,
            version_binding={**bundle.version_binding, "constitution_version": self.constitution_version},
            input_digest=digest(ruling, prefix="in:"),
            bundle_id=bundle.bundle_id(),
            fallback_path="none" if verdict == "permit" else "floor",
        )
