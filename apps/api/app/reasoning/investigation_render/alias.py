"""Lossless, reversible aliasing of stable evidence ids for compact rendering.

The evidence bundles reference entities by long, stable, pseudonymous ids: accounts as ``sub_<hash>``,
clusters as ``cl:<hash>``, narratives as ``nr:<hash>``. Repeated verbatim across a large investigation,
those ids dominate the token budget while carrying no investigative signal (they are already
pseudonyms). The alias legend maps each to a short local handle — accounts ``A1..An``, clusters
``C1..Cn``, narratives ``N1..Nn`` — used in the *rendered prompt text* only.

The mapping is **lossless and reversible**: the full legend (alias → real ref) rides in the prompt
manifest (never in the prompt text), so the Governor can resolve a model citation of ``A3`` back to the
real ``sub_...`` ref for citation checking. The numbering is **evidence-neutral**: aliases are assigned
in sorted-ref order, NOT by suspicion / probability / tier — the alias index must never encode a
ranking the model could read as a conclusion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.reasoning.investigation_composer import InvestigationPackage


def _assign(prefix: str, refs: set[str]) -> dict[str, str]:
    """Assign ``prefix1..prefixN`` to refs in sorted order (evidence-neutral, deterministic)."""
    return {ref: f"{prefix}{i}" for i, ref in enumerate(sorted(refs), start=1)}


@dataclass(frozen=True)
class AliasLegend:
    """A reversible alias map for one investigation's entities. ``*_to_alias`` renders ids compactly;
    ``resolve`` reverses an alias for citation checking; ``to_manifest`` carries the full legend."""

    account: dict[str, str] = field(default_factory=dict)      # sub_... -> A{n}
    cluster: dict[str, str] = field(default_factory=dict)      # cl:...  -> C{n}
    narrative: dict[str, str] = field(default_factory=dict)    # nr:...  -> N{n}

    def account_alias(self, ref: str) -> str:
        return self.account.get(ref, ref)

    def cluster_alias(self, ref: str) -> str:
        return self.cluster.get(ref, ref)

    def narrative_alias(self, ref: str) -> str:
        return self.narrative.get(ref, ref)

    def alias_tokens(self) -> set[str]:
        """Every short alias (A*/C*/N*) — the alias half of the citation universe the model may cite."""
        return set(self.account.values()) | set(self.cluster.values()) | set(self.narrative.values())

    def resolve(self, alias: str) -> str | None:
        """Reverse any alias back to its real stable ref (for Governor citation resolution)."""
        for m in (self.account, self.cluster, self.narrative):
            for ref, al in m.items():
                if al == alias:
                    return ref
        return None

    def to_manifest(self) -> dict[str, dict[str, str]]:
        """The full reversible legend for the prompt manifest — alias → real ref, per entity kind."""
        return {
            "accounts": {al: ref for ref, al in sorted(self.account.items(), key=lambda kv: kv[1])},
            "clusters": {al: ref for ref, al in sorted(self.cluster.items(), key=lambda kv: kv[1])},
            "narratives": {al: ref for ref, al in sorted(self.narrative.items(), key=lambda kv: kv[1])},
        }


def build_alias_legend(package: "InvestigationPackage") -> AliasLegend:
    """Assemble the reversible alias legend for a complete investigation package. Collects every
    stable entity ref that appears across the bundles and assigns a short handle in sorted-ref order."""
    b = package.bundles
    accounts: set[str] = set()
    for a in b.account.accounts:
        accounts.add(a.author_ref)
    for c in b.commenter_history.commenters:
        accounts.add(c.author_ref)
    for cm in b.comment.comments:
        accounts.add(cm.author_ref)
    clusters = {cl.cluster_ref for cl in b.coordination.clusters}
    # campaign candidates reference coordination clusters by the same ref — already covered above
    narratives = {n.narrative_ref for n in b.narrative.narratives}
    return AliasLegend(
        account=_assign("A", accounts),
        cluster=_assign("C", clusters),
        narrative=_assign("N", narratives),
    )


__all__ = ["AliasLegend", "build_alias_legend"]
