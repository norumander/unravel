"""FastAPI routes for the Unravel API."""

import json
import re

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.analysis.context import assemble_context
from app.bundle.classifier import classify_files
from app.bundle.parser import BundleTooLargeError, InvalidBundleError, parse_bundle
from app.llm.provider import TOOL_USE_SENTINEL, LLMError, get_provider
from app.logging.llm_logger import llm_logger
from app.models.schemas import ChatMessage, DiagnosticReport
from app.sessions.store import SessionNotFoundError, session_store

MAX_CHAT_HISTORY = 40  # ~20 turns of user+assistant

router = APIRouter(prefix="/api")

GET_FILE_CONTENTS_TOOL = {
    "name": "get_file_contents",
    "description": "Retrieve the contents of a specific file from the uploaded support bundle.",
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": (
                    "The path of the file within the bundle, as listed in the bundle manifest."
                ),
            }
        },
        "required": ["file_path"],
    },
}

# Cached provider — created once, reset via reset_provider() for testing
_provider_instance = None


def _get_or_create_provider():
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = get_provider()
    return _provider_instance


def reset_provider():
    """Reset the cached provider. Used by tests to inject mocks."""
    global _provider_instance
    _provider_instance = None


MAX_MESSAGE_LENGTH = 50_000  # ~12.5k tokens — generous but bounded


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)


@router.post("/upload")
async def upload_bundle(file: UploadFile) -> JSONResponse:
    """Upload and extract a support bundle."""
    # Stream-read with size limit to avoid buffering unbounded uploads
    chunks = []
    total = 0
    max_size = 500 * 1024 * 1024  # 500MB
    while True:
        chunk = await file.read(1024 * 1024)  # 1MB at a time
        if not chunk:
            break
        total += len(chunk)
        if total > max_size:
            return JSONResponse(
                status_code=413,
                content={"error": "File exceeds maximum upload size of 500MB."},
            )
        chunks.append(chunk)
    file_data = b"".join(chunks)

    try:
        manifest, extracted_files, parse_warnings = parse_bundle(file_data)
    except BundleTooLargeError as e:
        return JSONResponse(status_code=413, content={"error": str(e)})
    except InvalidBundleError:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid file format. Expected a .tar.gz archive."},
        )

    classified = classify_files(manifest)
    session = session_store.create(manifest, extracted_files, classified)

    signal_summary = {
        signal_type.value: len(files)
        for signal_type, files in classified.items()
    }

    response_content: dict = {
        "session_id": session.session_id,
        "manifest": manifest.model_dump(),
        "signal_summary": signal_summary,
    }
    if parse_warnings:
        response_content["warnings"] = parse_warnings

    return JSONResponse(status_code=200, content=response_content)


@router.get("/analyze/{session_id}")
async def analyze_bundle(session_id: str):
    """Stream LLM analysis of the uploaded bundle."""
    try:
        session = session_store.get(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    if session.report is not None:
        # Analysis already completed — return cached report
        async def cached_generator():
            yield {"data": json.dumps({"type": "report", "report": session.report.model_dump()})}

        return EventSourceResponse(cached_generator())

    if session.analyzing:
        raise HTTPException(status_code=409, detail="Analysis already in progress.")

    session.analyzing = True

    async def event_generator():
        try:
            try:
                provider = _get_or_create_provider()
            except ValueError as e:
                yield {"data": json.dumps({"type": "error", "message": str(e)})}
                return

            context = assemble_context(
                session.classified_signals, session.extracted_files
            )

            collected = ""
            try:
                with llm_logger.track(
                    session_id, "analyze", provider.provider_name, provider.model_name
                ) as tracker:
                    async for chunk in provider.analyze(context):
                        collected += chunk
                        yield {"data": json.dumps({"type": "chunk", "content": chunk})}

                    tracker.input_tokens = provider.last_input_tokens
                    tracker.output_tokens = provider.last_output_tokens

            except LLMError as e:
                yield {"data": json.dumps({"type": "error", "message": str(e)})}
                return

            # Strip markdown fences that LLMs commonly wrap JSON in
            cleaned = _strip_markdown_fences(collected)

            # Parse the complete response into a DiagnosticReport
            try:
                report = DiagnosticReport.model_validate_json(cleaned)
                session.report = report
                yield {
                    "data": json.dumps({"type": "report", "report": report.model_dump()})
                }
            except Exception:
                yield {
                    "data": json.dumps({
                        "type": "error",
                        "message": "Failed to parse LLM response into structured report.",
                    })
                }
        finally:
            session.analyzing = False

    return EventSourceResponse(event_generator())


@router.post("/chat/{session_id}")
async def chat(session_id: str, body: ChatRequest):
    """Stream a chat response with tool-use support."""
    try:
        session = session_store.get(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    # Add user message to chat history
    session.chat_history.append(ChatMessage(role="user", content=body.message))

    # Cap chat history to prevent unbounded context growth
    if len(session.chat_history) > MAX_CHAT_HISTORY:
        session.chat_history = session.chat_history[-MAX_CHAT_HISTORY:]

    async def event_generator():
        try:
            provider = _get_or_create_provider()
        except ValueError as e:
            yield {"data": json.dumps({"type": "error", "message": str(e)})}
            yield {"data": json.dumps({"type": "done"})}
            return

        # Build context messages: include report and manifest as system context
        context_parts = []
        if session.report:
            context_parts.append(
                f"Diagnostic Report:\n{session.report.model_dump_json()}"
            )
        context_parts.append(
            f"Bundle Manifest ({session.bundle_manifest.total_files} files):\n"
            + "\n".join(
                f"  {f.path} ({f.size_bytes} bytes, {f.signal_type.value})"
                for f in session.bundle_manifest.files[:100]
            )
        )

        messages = [
            ChatMessage(role="user", content="\n\n".join(context_parts)),
            ChatMessage(role="assistant", content="I have the diagnostic report and bundle manifest. How can I help you investigate?"),
            *session.chat_history,
        ]

        def tool_handler(name: str, arguments: dict) -> str:
            if name == "get_file_contents":
                file_path = arguments.get("file_path", "")
                content = session.extracted_files.get(file_path)
                if content is None:
                    return f"File not found in bundle: {file_path}"
                return content.decode("utf-8", errors="replace")
            return f"Unknown tool: {name}"

        collected = ""
        try:
            with llm_logger.track(
                session_id, "chat", provider.provider_name, provider.model_name
            ) as tracker:
                async for chunk in provider.chat(
                    messages, [GET_FILE_CONTENTS_TOOL], tool_handler
                ):
                    # Check if this is a tool-use indicator via sentinel prefix
                    if chunk.startswith(TOOL_USE_SENTINEL):
                        tool_data = json.loads(chunk[len(TOOL_USE_SENTINEL):])
                        yield {"data": json.dumps(tool_data)}
                        continue

                    collected += chunk
                    yield {"data": json.dumps({"type": "chunk", "content": chunk})}

                tracker.input_tokens = provider.last_input_tokens
                tracker.output_tokens = provider.last_output_tokens

        except LLMError as e:
            yield {"data": json.dumps({"type": "error", "message": str(e)})}
            yield {"data": json.dumps({"type": "done"})}
            return

        # Save assistant response to chat history
        if collected.strip():
            session.chat_history.append(
                ChatMessage(role="assistant", content=collected)
            )

        yield {"data": json.dumps({"type": "done"})}

    return EventSourceResponse(event_generator())


def _strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences that LLMs commonly wrap JSON responses in."""
    stripped = text.strip()
    # Match ```json ... ``` or ``` ... ```
    match = re.match(r"^```(?:json)?\s*\n(.*)\n\s*```$", stripped, re.DOTALL)
    if match:
        return match.group(1).strip()
    return stripped


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> JSONResponse:
    """Delete a session and all associated data."""
    try:
        session_store.delete(session_id)
        return JSONResponse(status_code=200, content={"deleted": True})
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")


@router.get("/files/{session_id}/{file_path:path}")
async def get_file(session_id: str, file_path: str) -> PlainTextResponse:
    """Retrieve the content of a specific file from the session's extracted files."""
    try:
        session = session_store.get(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    content = session.extracted_files.get(file_path)
    if content is None:
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    return PlainTextResponse(content=content.decode("utf-8", errors="replace"))
