"""Content-type-aware chunker — splits bundle files into retrieval-friendly chunks."""

import json
import os
import re
from dataclasses import dataclass

from app.models.schemas import SignalType

CHARS_PER_TOKEN = 4
DEFAULT_CHUNK_SIZE = int(os.environ.get("RAG_CHUNK_SIZE", "512"))  # tokens
DEFAULT_CHUNK_OVERLAP = int(os.environ.get("RAG_CHUNK_OVERLAP", "50"))  # tokens

_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")
_LOG_GROUP_SIZE = 30


@dataclass
class Chunk:
    text: str
    file_path: str
    signal_type: SignalType
    chunk_index: int
    char_start: int = 0
    char_end: int = 0


def chunk_file(
    file_path: str,
    content: str,
    signal_type: SignalType,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    """Split a bundle file into retrieval-friendly chunks based on its signal type.

    Args:
        file_path: Path of the file within the bundle (used as metadata).
        content: Raw text content of the file.
        signal_type: Classified signal type driving the chunking strategy.
        chunk_size: Target chunk size in tokens (applies to fixed-size fallback).
        chunk_overlap: Overlap between consecutive chunks in tokens.

    Returns:
        List of Chunk objects. Empty list if content is blank.
    """
    if not content.strip():
        return []

    if signal_type == SignalType.events:
        chunks = _chunk_json_events(content, file_path, signal_type)
        if chunks is not None:
            return chunks

    if signal_type == SignalType.resource_definitions:
        chunks = _chunk_yaml_documents(content, file_path, signal_type)
        if chunks is not None:
            return chunks

    if signal_type == SignalType.pod_logs:
        chunks = _chunk_log_lines(content, file_path, signal_type)
        if chunks is not None:
            return chunks

    return _chunk_fixed_size(content, file_path, signal_type, chunk_size, chunk_overlap)


def _chunk_json_events(content: str, file_path: str, signal_type: SignalType) -> list[Chunk] | None:
    """Parse JSON arrays or {items:[...]} objects into one chunk per element.

    Returns None if content is not valid JSON or not a supported shape,
    signalling the caller to fall back to fixed-size chunking.
    """
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return None

    items: list = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
        items = data["items"]
    else:
        return None

    if not items:
        return None

    return [
        Chunk(
            text=json.dumps(item, indent=2),
            file_path=file_path,
            signal_type=signal_type,
            chunk_index=i,
        )
        for i, item in enumerate(items)
    ]


def _chunk_yaml_documents(content: str, file_path: str, signal_type: SignalType) -> list[Chunk] | None:
    """Split a multi-document YAML file on `---` separators.

    Empty documents (blank content between separators) are skipped.
    Returns None only if no non-empty documents are found.
    """
    docs = re.split(r"^---\s*$", content, flags=re.MULTILINE)
    docs = [d.strip() for d in docs if d.strip()]
    if not docs:
        return None
    return [
        Chunk(text=doc, file_path=file_path, signal_type=signal_type, chunk_index=i)
        for i, doc in enumerate(docs)
    ]


def _chunk_log_lines(content: str, file_path: str, signal_type: SignalType) -> list[Chunk] | None:
    """Group log lines into fixed-line-count chunks.

    Timestamped logs use a smaller group size (30 lines) to keep temporal
    context tight. Non-timestamped logs use a larger group (60 lines).
    """
    lines = content.split("\n")
    sample = lines[:20]
    timestamped_count = sum(1 for line in sample if _TIMESTAMP_RE.match(line))
    group_size = _LOG_GROUP_SIZE if timestamped_count > len(sample) * 0.3 else _LOG_GROUP_SIZE * 2

    if len(lines) <= group_size:
        return [Chunk(text=content, file_path=file_path, signal_type=signal_type, chunk_index=0)]

    chunks = []
    for i in range(0, len(lines), group_size):
        group = "\n".join(lines[i : i + group_size])
        if group.strip():
            chunks.append(
                Chunk(text=group, file_path=file_path, signal_type=signal_type, chunk_index=len(chunks))
            )
    return chunks if chunks else None


def _chunk_fixed_size(
    content: str,
    file_path: str,
    signal_type: SignalType,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Chunk]:
    """Split content into overlapping fixed-size character windows.

    Overlap is applied so consecutive chunks share context at their boundaries,
    improving retrieval recall for content that spans chunk edges.
    """
    max_chars = chunk_size * CHARS_PER_TOKEN
    overlap_chars = chunk_overlap * CHARS_PER_TOKEN

    if len(content) <= max_chars:
        return [
            Chunk(
                text=content,
                file_path=file_path,
                signal_type=signal_type,
                chunk_index=0,
                char_start=0,
                char_end=len(content),
            )
        ]

    chunks = []
    start = 0
    idx = 0
    while start < len(content):
        end = min(start + max_chars, len(content))
        chunks.append(
            Chunk(
                text=content[start:end],
                file_path=file_path,
                signal_type=signal_type,
                chunk_index=idx,
                char_start=start,
                char_end=end,
            )
        )
        idx += 1
        next_start = end - overlap_chars
        if next_start >= len(content) or len(content) - next_start <= overlap_chars:
            break
        start = next_start
    return chunks
