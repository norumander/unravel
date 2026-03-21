"""API routes for session history — browse, update, delete past analyses."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.sessions.persistence import SessionPersistence

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/history", tags=["session-history"])

# Singleton — overridable via FastAPI dependency injection for testing
_persistence: SessionPersistence | None = None


def get_persistence() -> SessionPersistence:
    """Return the global SessionPersistence instance."""
    global _persistence
    if _persistence is None:
        _persistence = SessionPersistence()
    return _persistence


class SessionUpdateRequest(BaseModel):
    """Request body for PATCH /api/sessions/{id}."""

    notes: str | None = None
    tags: list[str] | None = None


@router.get("")
def list_sessions(store: SessionPersistence = Depends(get_persistence)):
    """List all persisted sessions, most recent first."""
    sessions = store.list_sessions()
    return [s.model_dump() for s in sessions]


@router.get("/{session_id}")
def get_session(
    session_id: str, store: SessionPersistence = Depends(get_persistence)
):
    """Get full session detail: summary + report + chat transcript."""
    try:
        data = store.get_session(session_id)
        return {
            "summary": data["summary"].model_dump(),
            "report": data["report"],
            "chat": data["chat"],
        }
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")


@router.patch("/{session_id}")
def update_session(
    session_id: str,
    body: SessionUpdateRequest,
    store: SessionPersistence = Depends(get_persistence),
):
    """Update notes or tags on a persisted session."""
    try:
        updated = store.update_session(
            session_id, notes=body.notes, tags=body.tags
        )
        return updated.model_dump()
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")


@router.delete("/{session_id}", status_code=204)
def delete_session(
    session_id: str, store: SessionPersistence = Depends(get_persistence)
):
    """Delete a persisted session and its data."""
    try:
        store.delete_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
