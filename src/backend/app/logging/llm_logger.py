"""Structured JSON logger for LLM API calls."""

import json
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Generator


class LLMCallLogger:
    """Logs LLM API calls as structured JSON to stdout.

    Each call emits exactly one JSON line with: timestamp, session_id,
    call_type, provider, model, input_tokens, output_tokens, latency_ms, status.

    No bundle content is ever included in log output (GR-6 compliance).
    """

    @contextmanager
    def track(
        self,
        session_id: str,
        call_type: str,
        provider: str,
        model: str,
    ) -> Generator["LLMCallTracker", None, None]:
        """Context manager that tracks an LLM call and logs it on exit."""
        tracker = LLMCallTracker(session_id, call_type, provider, model)
        try:
            yield tracker
        except Exception:
            tracker.status = "error"
            raise
        finally:
            tracker.emit()


class LLMCallTracker:
    """Tracks metrics for a single LLM API call."""

    def __init__(self, session_id: str, call_type: str, provider: str, model: str) -> None:
        self.session_id = session_id
        self.call_type = call_type
        self.provider = provider
        self.model = model
        self.input_tokens = 0
        self.output_tokens = 0
        self.status = "success"
        self._start_time = time.monotonic()

    def emit(self) -> None:
        """Emit the log entry as a JSON line to stdout."""
        latency_ms = round((time.monotonic() - self._start_time) * 1000)
        entry = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "session_id": self.session_id,
            "call_type": self.call_type,
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms": latency_ms,
            "status": self.status,
        }
        print(json.dumps(entry), file=sys.stdout, flush=True)


# Global singleton
llm_logger = LLMCallLogger()
