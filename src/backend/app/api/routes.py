"""FastAPI routes for the Unravel API."""

import json

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.analysis.context import assemble_context
from app.bundle.classifier import classify_files
from app.bundle.parser import BundleTooLargeError, InvalidBundleError, parse_bundle
from app.llm.provider import LLMError, get_provider
from app.logging.llm_logger import llm_logger
from app.models.schemas import ChatMessage, DiagnosticReport
from app.sessions.store import SessionNotFoundError, session_store

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


class ChatRequest(BaseModel):
    message: str


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
        manifest, extracted_files = parse_bundle(file_data)
    except BundleTooLargeError as e:
        return JSONResponse(status_code=413, content={"error": str(e)})
    except InvalidBundleError:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid file format. Expected a .tar.gz archive."},
        )

    classified = classify_files(manifest)
    session = session_store.create(manifest, extracted_files, classified)

    return JSONResponse(
        status_code=200,
        content={
            "session_id": session.session_id,
            "manifest": manifest.model_dump(),
        },
    )


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

    async def event_generator():
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

        # Parse the complete response into a DiagnosticReport
        try:
            report = DiagnosticReport.model_validate_json(collected)
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
                    # Check if this is a tool-use indicator
                    stripped = chunk.strip()
                    if stripped.startswith('{"type":"tool_use"'):
                        try:
                            tool_data = json.loads(stripped)
                            yield {"data": json.dumps(tool_data)}
                            continue
                        except json.JSONDecodeError:
                            pass

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


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> JSONResponse:
    """Delete a session and all associated data."""
    try:
        session_store.delete(session_id)
        return JSONResponse(status_code=200, content={"deleted": True})
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")
