"""In-memory session store — manages session lifecycle with no disk I/O."""

import uuid
from datetime import UTC, datetime

from app.models.schemas import BundleFile, BundleManifest, Session, SignalType

MAX_SESSIONS = 20
SESSION_TTL_SECONDS = 3600  # 1 hour


class SessionNotFoundError(Exception):
    """Raised when a requested session does not exist."""


class SessionStore:
    """In-memory session store. Not thread-safe — designed for single-process asyncio.

    All data lives in a Python dict. No persistence, no disk I/O.
    Sessions expire after SESSION_TTL_SECONDS and are evicted on access.
    Maximum of MAX_SESSIONS concurrent sessions; oldest evicted when full.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create(
        self,
        manifest: BundleManifest,
        extracted_files: dict[str, bytes],
        classified_signals: dict[SignalType, list[BundleFile]],
    ) -> Session:
        """Create a new session with the given bundle data."""
        self._evict_expired()

        # Evict oldest session if at capacity
        while len(self._sessions) >= MAX_SESSIONS:
            oldest_id = min(
                self._sessions, key=lambda k: self._sessions[k].created_at
            )
            del self._sessions[oldest_id]

        session_id = str(uuid.uuid4())
        session = Session(
            session_id=session_id,
            bundle_manifest=manifest,
            extracted_files=extracted_files,
            classified_signals=classified_signals,
        )
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Session:
        """Get a session by ID.

        Raises:
            SessionNotFoundError: If the session does not exist or has expired.
        """
        self._evict_expired()
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        return session

    def delete(self, session_id: str) -> bool:
        """Delete a session and all associated data.

        Raises:
            SessionNotFoundError: If the session does not exist.
        """
        if session_id not in self._sessions:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        del self._sessions[session_id]
        return True

    def _evict_expired(self) -> None:
        """Remove sessions older than SESSION_TTL_SECONDS."""
        now = datetime.now(tz=UTC)
        expired = [
            sid
            for sid, session in self._sessions.items()
            if (now - session.created_at).total_seconds() > SESSION_TTL_SECONDS
        ]
        for sid in expired:
            del self._sessions[sid]


# Global singleton instance
session_store = SessionStore()
