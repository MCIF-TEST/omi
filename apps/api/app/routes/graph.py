"""User-curated named graphs — /v1/graphs/*.

Operators build named graphs by adding commenter profiles one at a time
(e.g. from the commenter detail panel). Omi draws coordination edges
between members automatically using the persistent CoordinationEdge data
accumulated across every scan.

Old auto-generated coordination graph endpoints have been superseded by
this user-managed approach.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func as sqlfunc, select
from sqlalchemy.exc import IntegrityError

from sqlalchemy import or_

from app.core.auth import CurrentUser, require_user
from app.schemas import (
    AddGraphMemberRequest,
    CreateGraphRequest,
    GraphCoordinationEdge,
    GraphSuggestion,
    RenameGraphRequest,
    UserGraphDetail,
    UserGraphMemberOut,
    UserGraphOut,
)
from app.storage.db import get_session
from app.storage.models import CoordinationEdge, UserGraph, UserGraphMember

router = APIRouter(prefix="/v1/graphs", tags=["graphs"])

#: Members rendered in one detail response. The edge query fans out over the member set, and the
#: canvas stops being readable long before this, so it is a real bound rather than a formality. A
#: capped response says so (`truncated`) instead of quietly showing a subset.
MAX_GRAPH_MEMBERS = 250
#: Accounts suggested per graph. Enough to be worth reading, few enough to stay a shortlist.
MAX_SUGGESTIONS = 12
#: A suggestion has to clear the same bar the detector uses to call a pair coordinated. Below this
#: it is a lead the evidence does not support, and offering it would train the operator to add
#: accounts on our say-so rather than on evidence.
SUGGESTION_MIN_POSTERIOR = 0.80


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _graph_out(g: UserGraph, member_count: int) -> UserGraphOut:
    return UserGraphOut(
        id=g.id,
        name=g.name,
        platform=g.platform,
        member_count=member_count,
        created_at=g.created_at,
        updated_at=g.updated_at,
    )


def _member_out(m: UserGraphMember, *, community_id: int = 0, degree: int = 0) -> UserGraphMemberOut:
    return UserGraphMemberOut(
        id=m.id,
        external_id=m.external_id,
        platform=m.platform,
        handle=m.handle,
        display_name=m.display_name,
        tier=m.tier,
        omi_score=m.omi_score,
        avatar_url=m.avatar_url,
        added_at=m.added_at,
        community_id=community_id,
        degree=degree,
    )


def _edge_posterior(e: CoordinationEdge) -> float:
    """The calibrated probability this pair is coordinated, from the accumulated evidence.

    The old code served ``min(1.0, mean_cluster_score)``, which is a per-scan average and not a
    probability of anything. The row carries ``log_lr_sum``: the accumulated log10 likelihood ratio
    across every post the pair has been seen on, already discounted for context correlation. Turning
    that into a posterior against the stated prior is exactly what the detector does to decide
    whether a pair is coordinated at all, so the graph and the detector now agree by construction
    instead of by coincidence.

    Rows written before the accumulation layer existed have ``log_lr_sum`` at 0, which correctly
    means "seen, but before we were measuring", and falls back to the old mean so an old edge still
    renders rather than collapsing to the prior.
    """
    from app.campaigns.detector.probability import (
        DEFAULT_PRIOR,
        posterior_from_log10_odds,
        prior_odds,
    )
    import math

    accumulated = float(getattr(e, "log_lr_sum", 0.0) or 0.0)
    if accumulated <= 0:
        return max(0.0, min(1.0, float(e.mean_cluster_score or 0.0)))
    return posterior_from_log10_odds(math.log10(prior_odds(DEFAULT_PRIOR)) + accumulated)


def _edge_out(e: CoordinationEdge) -> GraphCoordinationEdge:
    return GraphCoordinationEdge(
        a=e.account_a,
        b=e.account_b,
        posterior=round(_edge_posterior(e), 4),
        families=sorted(getattr(e, "families_json", None) or []),
        contexts=len(getattr(e, "contexts_json", None) or []) or int(e.observation_count or 0),
        methods=sorted(e.methods_json or []),
        first_seen=e.first_observed_at,
        last_seen=e.last_observed_at,
    )


def _require_graph(session, graph_id: int, user_id: int) -> UserGraph:
    g = session.get(UserGraph, graph_id)
    if not g or g.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Graph not found.")
    return g


# ---------------------------------------------------------------------------
# Graph CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=list[UserGraphOut])
def list_graphs(current: CurrentUser = Depends(require_user)) -> list[UserGraphOut]:
    """List all graphs owned by the current user, newest first."""
    with get_session() as session:
        rows = session.execute(
            select(UserGraph, sqlfunc.count(UserGraphMember.id).label("mc"))
            .outerjoin(UserGraphMember, UserGraphMember.graph_id == UserGraph.id)
            .where(UserGraph.user_id == current.id)
            .group_by(UserGraph.id)
            .order_by(UserGraph.updated_at.desc())
        ).all()
        return [_graph_out(row.UserGraph, row.mc) for row in rows]


@router.post("", response_model=UserGraphOut, status_code=status.HTTP_201_CREATED)
def create_graph(
    body: CreateGraphRequest,
    current: CurrentUser = Depends(require_user),
) -> UserGraphOut:
    """Create a new named graph."""
    with get_session() as session:
        g = UserGraph(user_id=current.id, name=body.name.strip(), platform=body.platform)
        session.add(g)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A graph with that name already exists.",
            )
        session.commit()
        session.refresh(g)
        return _graph_out(g, 0)


@router.get("/{graph_id}", response_model=UserGraphDetail)
def get_graph(graph_id: int, current: CurrentUser = Depends(require_user)) -> UserGraphDetail:
    """Graph detail: members, the coordination evidence between them, and who is missing.

    Three things this answers that the previous version could not.

    WHY AN EDGE EXISTS. Each link carries its calibrated posterior, the independent evidence
    families behind it, and how many distinct posts the pair has been seen under. A line with a
    single opaque strength is a claim about two named people that nobody can check.

    WHICH ACCOUNTS CLUSTER. Community detection runs over the graph's own edges, so the canvas can
    separate two operations that both happen to be in one saved graph. The client used to hardcode
    every node into community 0, which made that whole dimension of the visualisation dead.

    WHO IS MISSING. Suggestions are accounts NOT in the graph that link strongly INTO it. Without
    them a graph can only ever show its owner what they already knew to add, which is most of why
    the feature felt inert.
    """
    with get_session() as session:
        g = _require_graph(session, graph_id, current.id)

        # Newest first is how the list reads, but the CAP has to be deterministic and meaningful:
        # oldest members are the ones the operator deliberately built the graph around, so a capped
        # graph keeps those and says it truncated rather than dropping the founding set.
        total = session.execute(
            select(sqlfunc.count(UserGraphMember.id)).where(UserGraphMember.graph_id == graph_id)
        ).scalar_one()
        members = session.execute(
            select(UserGraphMember)
            .where(UserGraphMember.graph_id == graph_id)
            .order_by(UserGraphMember.added_at.asc())
            .limit(MAX_GRAPH_MEMBERS)
        ).scalars().all()
        members = list(reversed(members))
        member_ids = {m.external_id for m in members}

        raw_edges: list[CoordinationEdge] = []
        neighbour_edges: list[CoordinationEdge] = []
        if member_ids:
            # ONE query for both jobs. Every edge touching any member: those with both endpoints
            # inside are the graph's own edges, those with one endpoint outside are the leads.
            touching = session.execute(
                select(CoordinationEdge).where(
                    CoordinationEdge.platform == g.platform,
                    or_(
                        CoordinationEdge.account_a.in_(member_ids),
                        CoordinationEdge.account_b.in_(member_ids),
                    ),
                )
            ).scalars().all()
            for e in touching:
                inside_a = e.account_a in member_ids
                inside_b = e.account_b in member_ids
                if inside_a and inside_b:
                    if e.account_a != e.account_b:
                        raw_edges.append(e)
                elif inside_a or inside_b:
                    neighbour_edges.append(e)

        edges = [_edge_out(e) for e in raw_edges]
        edges.sort(key=lambda x: -x.posterior)

        communities, degrees = _communities(member_ids, edges)
        suggestions = _suggestions(member_ids, neighbour_edges)

        return UserGraphDetail(
            id=g.id,
            name=g.name,
            platform=g.platform,
            member_count=total,
            created_at=g.created_at,
            updated_at=g.updated_at,
            members=[
                _member_out(m,
                            community_id=communities.get(m.external_id, 0),
                            degree=degrees.get(m.external_id, 0))
                for m in members
            ],
            edges=edges,
            suggestions=suggestions,
            # Community 0 is the UNCONNECTED band, not a cluster. Counting it would report
            # "1 community" for a graph with no edges at all, which is the opposite of true.
            community_count=len({c for c in communities.values() if c > 0}),
            truncated=total > len(members),
        )


def _communities(
    member_ids: set[str], edges: list[GraphCoordinationEdge],
) -> tuple[dict[str, int], dict[str, int]]:
    """Cluster the members over their own edges, and count each one's links.

    Community 0 is reserved for the UNCONNECTED band: members sharing no coordination evidence with
    anything else in the graph. That is the honest and by far the most common state for a curated
    graph, and it needs to be visually distinct rather than dressed up as a cluster of one. Real
    clusters are numbered from 1.

    Reuses ``app.graph.algorithms._louvain``, which was already in the codebase and which the graph
    route had never called: the client hardcoded every node to community 0 instead.
    """
    degrees: dict[str, int] = {ext: 0 for ext in member_ids}
    for e in edges:
        degrees[e.a] = degrees.get(e.a, 0) + 1
        degrees[e.b] = degrees.get(e.b, 0) + 1

    connected = [ext for ext in member_ids if degrees.get(ext, 0) > 0]
    if len(connected) < 2:
        return ({ext: 0 for ext in member_ids}, degrees)

    from app.graph.algorithms import _louvain

    weighted = [(e.a, e.b, max(e.posterior, 1e-6)) for e in edges]
    try:
        raw = _louvain(connected, weighted)
    except Exception:  # noqa: BLE001 — a layout hint must never fail the request
        raw = {ext: 0 for ext in connected}

    # Renumber densely from 1 in a stable order, so colours do not shuffle between requests on a
    # graph that has not changed.
    order: dict[int, int] = {}
    out: dict[str, int] = {}
    for ext in sorted(connected):
        label = raw.get(ext, 0)
        if label not in order:
            order[label] = len(order) + 1
        out[ext] = order[label]
    for ext in member_ids:
        out.setdefault(ext, 0)
    return out, degrees


def _suggestions(
    member_ids: set[str], neighbour_edges: list[CoordinationEdge],
) -> list[GraphSuggestion]:
    """Accounts outside the graph with strong evidence linking them into it.

    Ranked by how many DIFFERENT members they link to first, then by the strongest single link.
    That order is the point: one strong edge can be a coincidence with a good story, while an
    account tied to three separate members of a curated set is the shape of an operation.
    """
    best: dict[str, dict] = {}
    for e in neighbour_edges:
        outside = e.account_b if e.account_a in member_ids else e.account_a
        inside = e.account_a if e.account_a in member_ids else e.account_b
        if outside in member_ids or not outside:
            continue
        p = _edge_posterior(e)
        if p < SUGGESTION_MIN_POSTERIOR:
            continue
        cur = best.get(outside)
        if cur is None:
            best[outside] = {
                "platform": e.platform, "posterior": p, "linked_to": inside,
                "families": set(getattr(e, "families_json", None) or []),
                "contexts": len(getattr(e, "contexts_json", None) or []) or int(e.observation_count or 0),
                "links": {inside},
            }
            continue
        cur["links"].add(inside)
        cur["families"].update(getattr(e, "families_json", None) or [])
        if p > cur["posterior"]:
            cur["posterior"], cur["linked_to"] = p, inside
            cur["contexts"] = max(
                cur["contexts"],
                len(getattr(e, "contexts_json", None) or []) or int(e.observation_count or 0),
            )

    rows = [
        GraphSuggestion(
            external_id=ext,
            platform=v["platform"],
            posterior=round(v["posterior"], 4),
            linked_to=v["linked_to"],
            families=sorted(v["families"]),
            contexts=v["contexts"],
            links_into_graph=len(v["links"]),
        )
        for ext, v in best.items()
    ]
    rows.sort(key=lambda r: (-r.links_into_graph, -r.posterior, r.external_id))
    return rows[:MAX_SUGGESTIONS]


@router.patch("/{graph_id}", response_model=UserGraphOut)
def rename_graph(
    graph_id: int,
    body: RenameGraphRequest,
    current: CurrentUser = Depends(require_user),
) -> UserGraphOut:
    """Rename a graph."""
    with get_session() as session:
        g = _require_graph(session, graph_id, current.id)
        g.name = body.name.strip()
        g.updated_at = datetime.now(timezone.utc)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A graph with that name already exists.",
            )
        count = session.execute(
            select(sqlfunc.count(UserGraphMember.id)).where(UserGraphMember.graph_id == graph_id)
        ).scalar_one()
        session.commit()
        return _graph_out(g, count)


@router.delete("/{graph_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_graph(graph_id: int, current: CurrentUser = Depends(require_user)) -> None:
    """Delete a graph and all its members."""
    with get_session() as session:
        g = _require_graph(session, graph_id, current.id)
        session.delete(g)
        session.commit()


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------


@router.post("/{graph_id}/members", response_model=UserGraphMemberOut, status_code=status.HTTP_201_CREATED)
def add_member(
    graph_id: int,
    body: AddGraphMemberRequest,
    current: CurrentUser = Depends(require_user),
) -> UserGraphMemberOut:
    """Add a commenter profile to a graph. Idempotent — returns existing if already present."""
    with get_session() as session:
        g = _require_graph(session, graph_id, current.id)
        m = UserGraphMember(
            graph_id=graph_id,
            external_id=body.external_id,
            platform=g.platform,
            handle=body.handle or body.external_id,
            display_name=body.display_name,
            tier=body.tier,
            omi_score=body.omi_score,
            avatar_url=body.avatar_url,
        )
        session.add(m)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            existing = session.execute(
                select(UserGraphMember).where(
                    UserGraphMember.graph_id == graph_id,
                    UserGraphMember.external_id == body.external_id,
                )
            ).scalar_one_or_none()
            if existing:
                return _member_out(existing)
            raise HTTPException(status_code=409, detail="Member already in graph.")
        g.updated_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(m)
        return _member_out(m)


@router.delete("/{graph_id}/members/{external_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    graph_id: int,
    external_id: str,
    current: CurrentUser = Depends(require_user),
) -> None:
    """Remove a profile from a graph."""
    with get_session() as session:
        g = _require_graph(session, graph_id, current.id)
        m = session.execute(
            select(UserGraphMember).where(
                UserGraphMember.graph_id == graph_id,
                UserGraphMember.external_id == external_id,
            )
        ).scalar_one_or_none()
        if not m:
            raise HTTPException(status_code=404, detail="Member not found.")
        session.delete(m)
        g.updated_at = datetime.now(timezone.utc)
        session.commit()
