"""Reasoning endpoints — Phase 7.

Only one for now: generate (or fetch cached) commentary on an
investigation. Always authenticated; commentary lives on the user's
investigation row.

Public report routes (under /r/...) do NOT generate commentary; they
only display it if the owner has already generated one. This prevents
share recipients from running up the owner's token bill.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import CurrentUser, require_user
from app.reasoning import synthesize_commentary
from app.schemas import CommentaryResponse
from app.storage.db import get_session
from app.storage.repository import AccountRepository


router = APIRouter(prefix="/v1/investigations", tags=["reasoning"])


@router.post("/{slug}/commentary", response_model=CommentaryResponse)
def generate_commentary(
    slug: str,
    refresh: bool = Query(False, description="Force regeneration even if cached."),
    current: CurrentUser = Depends(require_user),
) -> CommentaryResponse:
    """Generate (or return cached) analyst-style commentary on an
    investigation. Idempotent unless ``refresh=true``."""
    with get_session() as session:
        repo = AccountRepository(session)
        inv = repo.get_investigation(
            slug=slug, user_id=current.id if current.id != 0 else None,
        )
        if inv is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Investigation not found.",
            )

        # Cache hit
        if inv.commentary_text and not refresh:
            return CommentaryResponse(
                slug=inv.slug,
                text=inv.commentary_text,
                provider=inv.commentary_provider or "unknown",
                tokens_used=inv.commentary_tokens_used or 0,
                generated_at=inv.commentary_generated_at or datetime.now(timezone.utc),
                cached=True,
            )

        # Generate
        result = synthesize_commentary(
            investigation={
                "label": inv.label,
                "input_url": inv.input_url,
                "kind": inv.kind,
                "slug": inv.slug,
                "created_at": inv.created_at,
            },
            payload=inv.payload_json or {},
        )
        now = datetime.now(timezone.utc)
        inv.commentary_text = result.text
        inv.commentary_provider = result.provider
        inv.commentary_tokens_used = result.tokens_used
        inv.commentary_generated_at = now

        return CommentaryResponse(
            slug=inv.slug,
            text=result.text,
            provider=result.provider,
            tokens_used=result.tokens_used,
            generated_at=now,
            cached=False,
        )
