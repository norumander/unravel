"""FastAPI routes for the Unravel API."""

import json
import re
import time

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.analysis.context import assemble_context
from app.bundle.chunker import chunk_file
from app.bundle.classifier import classify_files
from app.bundle.parser import BundleTooLargeError, InvalidBundleError, parse_bundle
from app.rag import rag_store
from app.rag.retriever import retrieve_analysis_context, retrieve_for_query
from app.llm.provider import TOOL_USE_SENTINEL, LLMError, get_fallback_provider, get_provider
from app.logging.llm_logger import llm_logger
from app.models.schemas import ChatMessage, DiagnosticReport, FindingSummary, LLMMetaSummary, SessionSummary
from app.evals.evaluator import run_programmatic_evals
from app.sessions.store import SessionNotFoundError, session_store
from app.sessions.persistence import SessionPersistence
from app.sessions.metadata import extract_bundle_metadata
from app.api.session_routes import get_persistence as _get_persistence
from datetime import datetime, UTC

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

SEARCH_BUNDLE_TOOL = {
    "name": "search_bundle",
    "description": (
        "Semantically search the support bundle for content related to a query. "
        "Returns the most relevant chunks with file paths and context. "
        "Use this FIRST to find relevant content, then use get_file_contents "
        "only if you need the complete file."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language description of what you're looking for.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of chunks to return (default 10).",
            },
        },
        "required": ["query"],
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

    # RAG: chunk and embed files for semantic search
    if rag_store.is_available():
        chunks = []
        for bf in manifest.files:
            file_content = extracted_files.get(bf.path)
            if file_content is None:
                continue
            text = file_content.decode("utf-8", errors="replace")
            chunks.extend(chunk_file(bf.path, text, bf.signal_type))

        collection_name = rag_store.create_collection(session.session_id, chunks)
        session.chroma_collection_name = collection_name

    signal_summary = {
        signal_type.value: len(files)
        for signal_type, files in classified.items()
    }

    response_content: dict = {
        "session_id": session.session_id,
        "manifest": manifest.model_dump(),
        "signal_summary": signal_summary,
    }
    if session.chroma_collection_name:
        response_content["chunks_indexed"] = len(chunks) if rag_store.is_available() else 0
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

            if rag_store.is_available() and session.chroma_collection_name:
                context = retrieve_analysis_context(
                    rag_store, session.chroma_collection_name,
                    bundle_manifest=session.bundle_manifest,
                )
            else:
                context = assemble_context(
                    session.classified_signals, session.extracted_files
                )

            collected = ""
            primary_error = None
            used_fallback = False
            llm_meta: dict = {}
            analysis_start = time.monotonic()

            try:
                with llm_logger.track(
                    session_id, "analyze", provider.provider_name, provider.model_name
                ) as tracker:
                    async for chunk in provider.analyze(context):
                        collected += chunk
                        yield {"data": json.dumps({"type": "chunk", "content": chunk})}

                    tracker.input_tokens = provider.last_input_tokens
                    tracker.output_tokens = provider.last_output_tokens

                llm_meta = {
                    "provider": provider.provider_name,
                    "model": provider.model_name,
                    "input_tokens": provider.last_input_tokens,
                    "output_tokens": provider.last_output_tokens,
                }

            except LLMError as e:
                primary_error = e

            # If primary provider failed, try fallback
            if primary_error is not None:
                fallback = get_fallback_provider()
                if fallback is None:
                    yield {"data": json.dumps({"type": "error", "message": str(primary_error)})}
                    return

                yield {"data": json.dumps({
                    "type": "warning",
                    "message": f"{provider.provider_name.title()} failed: {primary_error}. Falling back to {fallback.provider_name.title()}...",
                })}

                used_fallback = True
                collected = ""
                try:
                    with llm_logger.track(
                        session_id, "analyze", fallback.provider_name, fallback.model_name
                    ) as tracker:
                        async for chunk in fallback.analyze(context):
                            collected += chunk
                            yield {"data": json.dumps({"type": "chunk", "content": chunk})}

                        tracker.input_tokens = fallback.last_input_tokens
                        tracker.output_tokens = fallback.last_output_tokens

                    llm_meta = {
                        "provider": fallback.provider_name,
                        "model": fallback.model_name,
                        "input_tokens": fallback.last_input_tokens,
                        "output_tokens": fallback.last_output_tokens,
                    }

                except LLMError as e:
                    yield {"data": json.dumps({
                        "type": "error",
                        "message": f"Both providers failed. {provider.provider_name.title()}: {primary_error}. {fallback.provider_name.title()}: {e}",
                    })}
                    return

            # Emit LLM call metadata to the client
            if llm_meta:
                llm_meta["latency_ms"] = round(
                    (time.monotonic() - analysis_start) * 1000
                )
                llm_meta["used_fallback"] = used_fallback
                yield {"data": json.dumps({"type": "llm_meta", **llm_meta})}

            # Strip markdown fences that LLMs commonly wrap JSON in
            cleaned = _strip_markdown_fences(collected)

            # Sanitize LLM output — map unknown signal types to "other"
            cleaned = _sanitize_signal_types(cleaned)

            # Parse the complete response into a DiagnosticReport
            try:
                report = DiagnosticReport.model_validate_json(cleaned)
                session.report = report
                yield {
                    "data": json.dumps({"type": "report", "report": report.model_dump()})
                }

                # Run programmatic quality evals
                bundle_signal_types = {
                    st for st, files in session.classified_signals.items() if files
                }
                eval_report = run_programmatic_evals(
                    report, bundle_signal_types, session.extracted_files
                )

                # Stream eval scores to frontend
                yield {"data": json.dumps({
                    "type": "eval_scores",
                    **eval_report.to_dict(),
                })}

                # Attach eval scores to report
                report.eval_scores = {
                    r.dimension: r.score for r in eval_report.results
                }
                report.eval_scores["composite"] = eval_report.composite_score
                session.report = report

            except Exception as exc:
                import logging
                logger = logging.getLogger(__name__)
                logger.error("Report parse failed: %s", exc)
                logger.error("Raw LLM response (first 2000 chars): %s", cleaned[:2000])
                yield {
                    "data": json.dumps({
                        "type": "error",
                        "message": "Failed to parse LLM response into structured report.",
                    })
                }

            # Persist completed session to disk
            try:
                persistence = _get_persistence()
                bundle_metadata = extract_bundle_metadata(session.extracted_files)
                findings = [
                    FindingSummary(severity=f.severity.value, title=f.title)
                    for f in report.findings
                ] if report else []

                llm_meta_summary = None
                if llm_meta:
                    llm_meta_summary = LLMMetaSummary(
                        provider=llm_meta.get("provider", "unknown"),
                        model=llm_meta.get("model", "unknown"),
                        input_tokens=llm_meta.get("input_tokens", 0),
                        output_tokens=llm_meta.get("output_tokens", 0),
                        latency_ms=llm_meta.get("latency_ms", 0),
                    )

                summary = SessionSummary(
                    id=session_id,
                    bundle_name=session.bundle_manifest.files[0].path.split("/")[0] + ".tar.gz"
                    if session.bundle_manifest.files
                    else "unknown.tar.gz",
                    file_size=session.bundle_manifest.total_size_bytes,
                    timestamp=datetime.now(UTC).isoformat(),
                    status="completed",
                    bundle_metadata=bundle_metadata,
                    findings_summary=findings,
                    llm_meta=llm_meta_summary,
                    eval_score=eval_report.composite_score if eval_report else None,
                )

                report_dict = report.model_dump() if report else {}
                persistence.save_session(summary, report=report_dict)
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "Failed to persist session %s", session_id
                )

            # Send done event to flush the proxy buffer — without this,
            # the report event can be lost when the connection closes
            yield {"data": json.dumps({"type": "done"})}
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

    # Persist user message to disk
    try:
        _get_persistence().append_chat(
            session_id,
            {"role": "user", "content": body.message, "timestamp": datetime.now(UTC).isoformat()},
        )
    except Exception:
        pass  # Chat persistence is best-effort

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
            if name == "search_bundle":
                if not rag_store.is_available() or not session.chroma_collection_name:
                    return "Semantic search is not available. Use get_file_contents instead."
                query = arguments.get("query", "")
                max_results = arguments.get("max_results", 10)
                results = retrieve_for_query(
                    rag_store, session.chroma_collection_name, query, max_results=max_results
                )
                if not results:
                    return f"No results found for query: {query}"
                parts = []
                for r in results:
                    parts.append(
                        f"--- {r.file_path} ({r.signal_type.value}, relevance: {r.score:.2f}) ---\n{r.text}"
                    )
                return "\n\n".join(parts)
            return f"Unknown tool: {name}"

        tools = [GET_FILE_CONTENTS_TOOL]
        if rag_store.is_available() and session.chroma_collection_name:
            tools = [SEARCH_BUNDLE_TOOL, GET_FILE_CONTENTS_TOOL]

        async def _run_chat(p):
            nonlocal collected
            with llm_logger.track(
                session_id, "chat", p.provider_name, p.model_name
            ) as tracker:
                async for chunk in p.chat(
                    messages, tools, tool_handler
                ):
                    if chunk.startswith(TOOL_USE_SENTINEL):
                        tool_data = json.loads(chunk[len(TOOL_USE_SENTINEL):])
                        yield {"data": json.dumps(tool_data)}
                        continue

                    collected += chunk
                    yield {"data": json.dumps({"type": "chunk", "content": chunk})}

                tracker.input_tokens = p.last_input_tokens
                tracker.output_tokens = p.last_output_tokens

        collected = ""
        primary_error = None
        used_fallback = False
        active_provider = provider
        chat_start = time.monotonic()

        try:
            async for event in _run_chat(provider):
                yield event
        except LLMError as e:
            primary_error = e

        if primary_error is not None:
            fallback = get_fallback_provider()
            if fallback is None:
                yield {"data": json.dumps({"type": "error", "message": str(primary_error)})}
                yield {"data": json.dumps({"type": "done"})}
                return

            yield {"data": json.dumps({
                "type": "warning",
                "message": f"{provider.provider_name.title()} failed: {primary_error}. Falling back to {fallback.provider_name.title()}...",
            })}

            used_fallback = True
            active_provider = fallback
            collected = ""
            try:
                async for event in _run_chat(fallback):
                    yield event
            except LLMError as e:
                yield {"data": json.dumps({
                    "type": "error",
                    "message": f"Both providers failed. {provider.provider_name.title()}: {primary_error}. {fallback.provider_name.title()}: {e}",
                })}
                yield {"data": json.dumps({"type": "done"})}
                return

        # Save assistant response to chat history
        if collected.strip():
            session.chat_history.append(
                ChatMessage(role="assistant", content=collected)
            )

            # Persist assistant message to disk
            try:
                _get_persistence().append_chat(
                    session_id,
                    {"role": "assistant", "content": collected, "timestamp": datetime.now(UTC).isoformat()},
                )
            except Exception:
                pass  # Chat persistence is best-effort

        # Emit LLM call metadata to the client
        yield {"data": json.dumps({
            "type": "llm_meta",
            "provider": active_provider.provider_name,
            "model": active_provider.model_name,
            "input_tokens": active_provider.last_input_tokens,
            "output_tokens": active_provider.last_output_tokens,
            "latency_ms": round((time.monotonic() - chat_start) * 1000),
            "used_fallback": used_fallback,
        })}

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


_VALID_SIGNAL_TYPES = {"pod_logs", "cluster_info", "resource_definitions", "events", "node_status", "other"}


def _sanitize_signal_types(text: str) -> str:
    """Replace unknown signal type strings with 'other' in the JSON response.

    LLMs occasionally invent signal types like 'node_conditions' or 'pod_status'
    that don't match the SignalType enum, causing the entire report to fail
    validation. This normalizes them before parsing.
    """
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text

    for finding in data.get("findings", []):
        if "source_signals" in finding:
            finding["source_signals"] = [
                s if s in _VALID_SIGNAL_TYPES else "other"
                for s in finding["source_signals"]
            ]

    if "signal_types_analyzed" in data:
        data["signal_types_analyzed"] = [
            s if s in _VALID_SIGNAL_TYPES else "other"
            for s in data["signal_types_analyzed"]
        ]

    return json.dumps(data)


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
