"""In-memory session store — manages session lifecycle with no disk I/O."""

import uuid

from app.models.schemas import BundleFile, BundleManifest, Session, SignalType


class SessionNotFoundError(Exception):
    """Raised when a requested session does not exist."""


class SessionStore:
    """Thread-safe in-memory session store.

    All data lives in a Python dict. No persistence, no disk I/O.
    Data is cleared on server restart or explicit delete.
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
            SessionNotFoundError: If the session does not exist.
        """
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


# Global singleton instance
session_store = SessionStore()
