"""Intelligence Library — category taxonomy (Sprint 025, Phase 2).

The shelves of the Library. Each :class:`KnowledgeCategory` groups entries of one kind of
investigative expertise. Categories are stable, content-addressed, and map to the lookup dimension
used by retrieval. Entries live in ``entries.py``; the store in ``library.py``.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.evidence.bundle import digest

CATEGORY_TAXONOMY_VERSION = "v1"


@dataclass(frozen=True)
class KnowledgeCategory:
    id: str
    name: str
    description: str
    purpose: str


CATEGORIES: tuple[KnowledgeCategory, ...] = (
    KnowledgeCategory("behavioral_archetypes", "Behavioral Archetypes",
                      "Recurring account/user behavior profiles, authentic and inauthentic.",
                      "Give behavior/temporal specialists a named vocabulary of how accounts behave."),
    KnowledgeCategory("coordination_techniques", "Coordination Techniques",
                      "The mechanisms by which accounts act together.",
                      "Anchor the corroboration gate: which techniques are discriminative vs not."),
    KnowledgeCategory("bot_behaviors", "Bot Behaviors",
                      "Automation signatures — and, critically, benign automation.",
                      "Separate botnets from disclosed schedulers and power users."),
    KnowledgeCategory("legitimate_community_patterns", "Legitimate Community Patterns",
                      "How authentic communities coordinate openly and organically.",
                      "Protect the precision frontier: legitimate coordination is not hostile."),
    KnowledgeCategory("campaign_types", "Campaign Types",
                      "Kinds of materialized multi-account campaigns, hostile and legitimate.",
                      "Frame the legitimate-coordination hypothesis before any hostile read."),
    KnowledgeCategory("narrative_amplification", "Narrative Amplification",
                      "How messages are amplified — organic vs manufactured.",
                      "Separate viral reach from coordinated amplification at the narrative grain."),
    KnowledgeCategory("influence_operations", "Influence Operations",
                      "Multi-method, cross-narrative coordinated influence.",
                      "Connect sub-concepts (astroturf, sockpuppets, pods) into operations."),
    KnowledgeCategory("platform_behaviors", "Platform-specific Behaviors",
                      "Norms and signal meanings that differ by platform.",
                      "Prevent cross-platform false reads (YouTube != X != Reddit != TikTok)."),
    KnowledgeCategory("deception_indicators", "Deception Indicators",
                      "Signals consistent with deliberate inauthentic presentation.",
                      "Catalog the raising signals with their evidentiary weight and gates."),
    KnowledgeCategory("false_positive_patterns", "False-positive Patterns",
                      "Legitimate look-alikes that get mistaken for hostile behavior.",
                      "The precision frontier as knowledge: every hostile pattern's benign twin."),
    KnowledgeCategory("organic_viral_signatures", "Organic Viral Signatures",
                      "What genuine virality looks like structurally.",
                      "Give specialists a positive model of authentic breadth to weigh against."),
    KnowledgeCategory("investigative_heuristics", "Known Investigative Heuristics",
                      "Reusable analytic rules of thumb, with their failure modes.",
                      "Encode hard-won tradecraft while naming when each heuristic breaks."),
    KnowledgeCategory("osint_techniques", "Known OSINT Techniques",
                      "Open-source-intelligence methods applicable to social evidence.",
                      "Ground the council in disciplined, sourceable analyst method."),
    KnowledgeCategory("confidence_calibration", "Confidence Calibration Guidelines",
                      "How confidence should track evidence strength and quantity.",
                      "Prevent thin-data over-confidence and single-axis inflation."),
)

CATEGORIES_BY_ID: dict[str, KnowledgeCategory] = {c.id: c for c in CATEGORIES}


def category_ids() -> tuple[str, ...]:
    return tuple(c.id for c in CATEGORIES)


def taxonomy_hash() -> str:
    return digest(
        {"version": CATEGORY_TAXONOMY_VERSION,
         "categories": [{"id": c.id, "name": c.name, "description": c.description,
                         "purpose": c.purpose} for c in CATEGORIES]},
        prefix="kc:",
    )


__all__ = [
    "CATEGORY_TAXONOMY_VERSION", "KnowledgeCategory", "CATEGORIES", "CATEGORIES_BY_ID",
    "category_ids", "taxonomy_hash",
]
