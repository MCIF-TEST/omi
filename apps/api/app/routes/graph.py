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

from app.core.auth import CurrentUser, require_user
from app.schemas import (
    AddGraphMemberRequest,
    CreateGraphRequest,
    GraphEdge,
    RenameGraphRequest,
    UserGraphDetail,
    UserGraphMemberOut,
    UserGraphOut,
)
from app.storage.db import get_session
from app.storage.models import CoordinationEdge, UserGraph, UserGraphMember

router = APIRouter(prefix="/v1/graphs", tags=["graphs"])


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


def _member_out(m: UserGraphMember) -> UserGraphMemberOut:
    return UserGraphMemberOut(
        id=m.id,
        external_id=m.external_id,
        platform=m.platform,
        handle=m.handle,
        display_name=m.display_name,
        tier=m.tier,
        avatar_url=m.avatar_url,
        added_at=m.added_at,
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
    """Graph detail with members and coordination edges between them."""
    with get_session() as session:
        g = _require_graph(session, graph_id, current.id)
        members = session.execute(
            select(UserGraphMember)
            .where(UserGraphMember.graph_id == graph_id)
            .order_by(UserGraphMember.added_at.desc())
        ).scalars().all()

        member_ids = {m.external_id for m in members}
        raw_edges: list[CoordinationEdge] = []
        if len(member_ids) >= 2:
            raw_edges = session.execute(
                select(CoordinationEdge).where(
                    CoordinationEdge.platform == g.platform,
                    CoordinationEdge.account_a.in_(member_ids),
                    CoordinationEdge.account_b.in_(member_ids),
                )
            ).scalars().all()

        edges = [
            GraphEdge(a=e.account_a, b=e.account_b, strength=min(1.0, e.mean_cluster_score))
            for e in raw_edges
        ]

        return UserGraphDetail(
            id=g.id,
            name=g.name,
            platform=g.platform,
            member_count=len(members),
            created_at=g.created_at,
            updated_at=g.updated_at,
            members=[_member_out(m) for m in members],
            edges=edges,
        )


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
