from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import warnings

from .manifest import Chunk, read_manifest


def merge_raw_asr_to_markdown(episode_dir: Path, transcript_dir: Path) -> str:
    episode_dir = episode_dir.resolve(strict=False)
    transcript_dir = transcript_dir.resolve(strict=False)
    manifest_path = transcript_dir / "chunks_manifest.jsonl"
    raw_asr_path = transcript_dir / "raw_asr.jsonl"
    markdown_path = transcript_dir / "raw_asr.md"

    chunks = read_manifest(manifest_path)
    rows = _read_jsonl(raw_asr_path)
    manifest_by_id = {chunk.chunk_id: chunk for chunk in chunks}

    latest_by_chunk: dict[str, dict[str, Any]] = {}
    for row in rows:
        chunk = manifest_by_id.get(str(row.get("chunk_id")))
        if chunk is None or not _row_matches_chunk(row, chunk):
            continue
        latest_by_chunk[chunk.chunk_id] = row

    missing = [chunk.chunk_id for chunk in chunks if chunk.chunk_id not in latest_by_chunk]
    if missing:
        warnings.warn(f"missing transcript rows for {len(missing)} manifest chunks: {', '.join(missing[:5])}", stacklevel=2)

    ordered_rows = [latest_by_chunk[chunk.chunk_id] for chunk in chunks if chunk.chunk_id in latest_by_chunk]
    markdown = _render_markdown(chunks, ordered_rows)
    markdown_path.write_text(markdown, encoding="utf-8")
    return markdown


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"raw ASR file not found: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid raw ASR row {line_number}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"invalid raw ASR row {line_number}: expected an object")
            rows.append(payload)
    return rows


def _row_matches_chunk(row: dict[str, Any], chunk: Chunk) -> bool:
    fields = [
        "chunk_id",
        "audio_path",
        "source_path",
        "source_name",
        "source_size_bytes",
        "source_mtime_ns",
        "chunk_seconds",
        "chunk_format",
        "chunk_size_bytes",
    ]
    return all(row.get(field) == getattr(chunk, field) for field in fields)


def _render_markdown(chunks: list[Chunk], rows: list[dict[str, Any]]) -> str:
    source = _single_value(rows, "source_name") or (chunks[0].source_name if chunks else "unknown")
    model = _single_value(rows, "model") or "unknown"
    language = _single_value(rows, "language") or "not set"

    lines = [
        "# Raw ASR Transcript",
        "",
        f"Source: {source}",
        f"Model: {model}",
        f"Language: {language}",
        "",
    ]

    for row in rows:
        lines.extend(
            [
                f"## {_format_timestamp(int(row['start_ms']))}-{_format_timestamp(int(row['end_ms']))}",
                "",
            ]
        )
        segments = row.get("segments")
        if isinstance(segments, list) and segments:
            for segment in segments:
                segment_text = _segment_text(segment).strip()
                speaker = segment.get("speaker") if isinstance(segment, dict) else None
                if speaker:
                    lines.append(f"**{speaker}:** {segment_text}")
                elif segment_text:
                    lines.append(segment_text)
                lines.append("")
        else:
            text = str(row.get("text", "")).strip()
            lines.append(text)
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _single_value(rows: list[dict[str, Any]], key: str) -> str | None:
    values = {row.get(key) for row in rows if row.get(key)}
    if len(values) == 1:
        return str(next(iter(values)))
    if len(values) > 1:
        return "multiple"
    return None


def _format_timestamp(ms: int) -> str:
    total_seconds = max(0, ms // 1000)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _segment_text(segment: Any) -> str:
    if not isinstance(segment, dict):
        return str(segment)
    for key in ("text", "transcript", "content", "value"):
        value = segment.get(key)
        if isinstance(value, str):
            return value
    return ""
