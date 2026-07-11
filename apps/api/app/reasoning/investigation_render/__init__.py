"""Investigation evidence rendering — normalize + budget the complete InvestigationPackage.

The ONE place the complete, lossless :class:`~app.reasoning.investigation_composer.InvestigationPackage`
is turned into budgeted, normalized, model-facing evidence sections (with a reversible alias legend and
an evidence-coverage manifest). Normalization is lossless; budgeting is coverage-based, never
suspicion-based. This layer builds no prompt and calls no model — it only projects evidence for the
Prompt Builder.
"""
from __future__ import annotations

from .alias import AliasLegend, build_alias_legend
from .budget import (
    COVERAGE_SIGNALS,
    AccountCoverage,
    BudgetConfig,
    compute_account_coverage,
    select_accounts,
    select_comment_groups,
)
from .dedup import (
    CommentGroup,
    RelationshipGroup,
    collapse_relationships,
    group_near_duplicate_comments,
)
from .render import RenderedEvidence, render_investigation_evidence
from .tokens import estimate_json_tokens, estimate_tokens

__all__ = [
    "AliasLegend", "build_alias_legend",
    "COVERAGE_SIGNALS", "AccountCoverage", "BudgetConfig", "compute_account_coverage",
    "select_accounts", "select_comment_groups",
    "CommentGroup", "RelationshipGroup", "collapse_relationships", "group_near_duplicate_comments",
    "RenderedEvidence", "render_investigation_evidence",
    "estimate_json_tokens", "estimate_tokens",
]
