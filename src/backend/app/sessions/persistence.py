"""File-based session persistence — JSON index + per-session directories."""

import json
import logging
import os
import shutil
import tempfile

from app.models.schemas import SessionSummary

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = "/app/data/sessions"


class SessionPersistence:
    """Persists completed session data to JSON files.

    Separate from the in-memory SessionStore — this writes durable records
    of finished analyses, not active session runtime state.

    Storage layout:
        {data_dir}/sessions.json         — index of all sessions
        {data_dir}/{session_id}/report.json  — full analysis report
        {data_dir}/{session_id}/chat.json    — chat transcript
    """

    def __init__(self, data_dir: str | None = None) -> None:
        self._data_dir = data_dir or os.environ.get(
            "SESSION_DATA_DIR", DEFAULT_DATA_DIR
        )
        os.makedirs(self._data_dir, exist_ok=True)
        self._index_path = os.path.join(self._data_dir, "sessions.json")

    def _read_index(self) -> list[dict]:
        if not os.path.exists(self._index_path):
            return []
        with open(self._index_path) as f:
            return json.load(f)

    def _write_index(self, entries: list[dict]) -> None:
        # Atomic write: write to temp file, then rename
        fd, tmp_path = tempfile.mkstemp(
            dir=self._data_dir, suffix=".json.tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(entries, f, indent=2)
            os.replace(tmp_path, self._index_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def save_session(
        self,
        summary: SessionSummary,
        report: dict | None = None,
        chat: list[dict] | None = None,
    ) -> None:
        """Save a session summary to the index and write report/chat files."""
        entries = self._read_index()
        entries.append(summary.model_dump())
        self._write_index(entries)

        session_dir = os.path.join(self._data_dir, summary.id)
        os.makedirs(session_dir, exist_ok=True)

        if report is not None:
            report_path = os.path.join(session_dir, "report.json")
            with open(report_path, "w") as f:
                json.dump(report, f, indent=2)

        chat_path = os.path.join(session_dir, "chat.json")
        with open(chat_path, "w") as f:
            json.dump(chat or [], f)

    def list_sessions(self) -> list[SessionSummary]:
        """Return all sessions, most recent first."""
        entries = self._read_index()
        sessions = [SessionSummary(**e) for e in entries]
        sessions.sort(key=lambda s: s.timestamp, reverse=True)
        return sessions

    def get_session(self, session_id: str) -> dict:
        """Load full session data: summary + report + chat."""
        entries = self._read_index()
        match = next((e for e in entries if e["id"] == session_id), None)
        if match is None:
            raise KeyError(f"Session {session_id} not found")

        session_dir = os.path.join(self._data_dir, session_id)
        report = {}
        report_path = os.path.join(session_dir, "report.json")
        if os.path.exists(report_path):
            with open(report_path) as f:
                report = json.load(f)

        chat = []
        chat_path = os.path.join(session_dir, "chat.json")
        if os.path.exists(chat_path):
            with open(chat_path) as f:
                chat = json.load(f)

        return {
            "summary": SessionSummary(**match),
            "report": report,
            "chat": chat,
        }

    def update_session(
        self,
        session_id: str,
        notes: str | None = None,
        tags: list[str] | None = None,
    ) -> SessionSummary:
        """Update mutable fields (notes, tags) on a session."""
        entries = self._read_index()
        match = next((e for e in entries if e["id"] == session_id), None)
        if match is None:
            raise KeyError(f"Session {session_id} not found")

        if notes is not None:
            match["notes"] = notes
        if tags is not None:
            match["tags"] = tags

        self._write_index(entries)
        return SessionSummary(**match)

    def delete_session(self, session_id: str) -> None:
        """Remove a session from the index and delete its data directory."""
        entries = self._read_index()
        original_len = len(entries)
        entries = [e for e in entries if e["id"] != session_id]
        if len(entries) == original_len:
            raise KeyError(f"Session {session_id} not found")

        self._write_index(entries)

        session_dir = os.path.join(self._data_dir, session_id)
        if os.path.isdir(session_dir):
            shutil.rmtree(session_dir)

    def append_chat(self, session_id: str, message: dict) -> None:
        """Append a single chat message to the session's chat transcript."""
        session_dir = os.path.join(self._data_dir, session_id)
        chat_path = os.path.join(session_dir, "chat.json")
        if not os.path.exists(chat_path):
            raise KeyError(f"Session {session_id} not found")

        with open(chat_path) as f:
            chat = json.load(f)
        chat.append(message)
        with open(chat_path, "w") as f:
            json.dump(chat, f)
