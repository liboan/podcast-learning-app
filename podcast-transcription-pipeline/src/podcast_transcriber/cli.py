from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

from .audio import chunk_audio, validate_upload_size
from .manifest import SCHEMA_VERSION, Chunk, read_manifest, write_manifest
from .merge import (
    CHUNKING_MANIFEST_FILENAME,
    TRANSCRIPTION_MARKDOWN_FILENAME,
    TRANSCRIPTION_RAW_ASR_FILENAME,
    merge_raw_asr_to_markdown,
)
from .openai_client import transcribe_audio_file
from .profiles import load_profile, request_settings_for_profile

CHUNKING_METADATA_FILENAME = "chunking_metadata.json"
TRANSCRIPTION_METADATA_FILENAME = "transcription_metadata.json"


def main(argv: list[str] | None = None) -> int:
    _load_local_env()
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="podcast-transcriber")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-episode", help="Create episode working directories.")
    init_parser.add_argument("episode_dir", type=Path)
    init_parser.add_argument("--source-dir", required=True, type=Path)
    init_parser.add_argument("--chunks-dir", required=True, type=Path)
    init_parser.add_argument("--transcript-dir", type=Path)
    init_parser.set_defaults(func=_cmd_init_episode)

    chunk_parser = subparsers.add_parser("chunk", help="Create fixed-length MP3 chunks and a manifest.")
    chunk_parser.add_argument("episode_dir", type=Path)
    chunk_parser.add_argument("--source-dir", required=True, type=Path)
    chunk_parser.add_argument("--chunks-dir", required=True, type=Path)
    chunk_parser.add_argument("--source-file", required=True, type=Path)
    chunk_parser.add_argument("--chunk-seconds", type=int, default=180)
    chunk_parser.add_argument("--overlap-seconds", type=int, default=0)
    chunk_parser.add_argument("--force", action="store_true")
    chunk_parser.set_defaults(func=_cmd_chunk)

    transcribe_parser = subparsers.add_parser("transcribe", help="Transcribe manifest chunks with OpenAI.")
    transcribe_parser.add_argument("episode_dir", type=Path)
    transcribe_parser.add_argument("--chunks-dir", required=True, type=Path)
    transcribe_parser.add_argument("--transcript-dir", required=True, type=Path)
    transcribe_parser.add_argument("--profile-file", required=True, type=Path)
    transcribe_parser.add_argument("--profile", required=True)
    transcribe_parser.add_argument("--chunk-id")
    transcribe_parser.add_argument("--start-index", type=int)
    transcribe_parser.add_argument("--end-index", type=int)
    transcribe_parser.add_argument("--limit", type=int)
    transcribe_parser.add_argument("--force", action="store_true")
    transcribe_parser.set_defaults(func=_cmd_transcribe)

    merge_parser = subparsers.add_parser("merge", help="Merge raw ASR JSONL into timestamped Markdown.")
    merge_parser.add_argument("episode_dir", type=Path)
    merge_parser.add_argument("--chunks-dir", required=True, type=Path)
    merge_parser.add_argument("--transcript-dir", required=True, type=Path)
    merge_parser.set_defaults(func=_cmd_merge)

    return parser


def _cmd_init_episode(args: argparse.Namespace) -> int:
    episode_dir = _resolve(args.episode_dir)
    source_dir = _resolve(args.source_dir)
    chunks_dir = _resolve(args.chunks_dir)
    transcript_dir = _resolve(args.transcript_dir) if args.transcript_dir else None

    episode_dir.mkdir(parents=True, exist_ok=True)
    _require_inside(episode_dir, source_dir, "SOURCE_DIR")
    _require_inside(episode_dir, chunks_dir, "CHUNKS_DIR")
    if transcript_dir:
        _require_inside(episode_dir, transcript_dir, "TRANSCRIPT_DIR")

    source_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    if transcript_dir:
        transcript_dir.mkdir(parents=True, exist_ok=True)
    print(f"initialized episode directory: {episode_dir}")
    return 0


def _cmd_chunk(args: argparse.Namespace) -> int:
    episode_dir, source_dir, chunks_dir = _validate_chunk_dirs(args)
    if args.chunk_seconds <= 0:
        raise RuntimeError("--chunk-seconds must be greater than zero")
    if args.overlap_seconds < 0:
        raise RuntimeError("--overlap-seconds must be zero or greater")
    if args.overlap_seconds >= args.chunk_seconds:
        raise RuntimeError("--overlap-seconds must be less than --chunk-seconds")

    source_file = _resolve(args.source_file)
    if not source_file.exists():
        raise FileNotFoundError(f"source audio not found: {source_file}")
    if not source_file.is_file():
        raise RuntimeError(f"source audio is not a file: {source_file}")
    _require_inside(source_dir, source_file, "SOURCE_AUDIO")

    chunks_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = chunks_dir / CHUNKING_MANIFEST_FILENAME
    chunking_metadata_path = chunks_dir / CHUNKING_METADATA_FILENAME
    existing_metadata = _read_json_file_if_exists(chunking_metadata_path)

    if manifest_path.exists():
        chunks = read_manifest(manifest_path)
        if _manifest_matches_source(chunks, episode_dir, source_file, args.chunk_seconds, args.overlap_seconds) and not args.force:
            if existing_metadata and not _chunking_metadata_matches_chunks(existing_metadata, episode_dir, chunks_dir, chunks):
                raise RuntimeError("existing chunking_metadata.json does not match the manifest; rerun chunk with --force")
            _validate_manifest_chunk_files(episode_dir, chunks)
            _write_json_file_atomic(chunking_metadata_path, _chunking_metadata_for_chunks(episode_dir, chunks_dir, chunks))
            print(f"manifest already up to date: {manifest_path}")
            return 0
        if not args.force:
            raise RuntimeError("existing manifest does not match the source file or chunk settings; rerun chunk with --force")
    elif existing_metadata and not args.force:
        raise RuntimeError("existing chunking_metadata.json found without a manifest; rerun chunk with --force")

    existing_chunks = sorted(chunks_dir.glob("chunk_*.mp3"))
    if existing_chunks and not args.force:
        raise RuntimeError(f"{chunks_dir} already contains generated chunks; rerun chunk with --force")

    chunks = chunk_audio(
        episode_dir=episode_dir,
        source_dir=source_dir,
        source_path=source_file,
        chunks_dir=chunks_dir,
        chunk_seconds=args.chunk_seconds,
        overlap_seconds=args.overlap_seconds,
        force=args.force,
    )
    write_manifest(chunks, manifest_path)
    _write_json_file_atomic(chunking_metadata_path, _chunking_metadata_for_chunks(episode_dir, chunks_dir, chunks))
    print(f"wrote {len(chunks)} chunks and manifest: {manifest_path}")
    return 0


def _cmd_transcribe(args: argparse.Namespace) -> int:
    episode_dir = _resolve(args.episode_dir)
    chunks_dir = _resolve(args.chunks_dir)
    transcript_dir = _resolve(args.transcript_dir)
    _require_inside(episode_dir, chunks_dir, "CHUNKS_DIR")
    _require_inside(episode_dir, transcript_dir, "TRANSCRIPT_DIR")
    transcript_dir.mkdir(parents=True, exist_ok=True)
    chunks = read_manifest(chunks_dir / CHUNKING_MANIFEST_FILENAME)
    selected_chunks = _select_chunks(chunks, args)
    if not selected_chunks:
        raise RuntimeError("no chunks matched the requested selection")

    profile_path = _resolve(args.profile_file)
    profile = load_profile(profile_path, args.profile)
    cwd = Path.cwd().resolve(strict=False)
    try:
        profile_file = Path(profile.profile_file).relative_to(cwd).as_posix()
    except ValueError:
        profile_file = profile.profile_file
    raw_asr_path = transcript_dir / TRANSCRIPTION_RAW_ASR_FILENAME
    transcription_metadata_path = transcript_dir / TRANSCRIPTION_METADATA_FILENAME
    existing_rows = _read_jsonl_if_exists(raw_asr_path)
    run_request = request_settings_for_profile(profile, max(chunk.audio_duration_ms for chunk in selected_chunks) / 1000)
    transcription_metadata = {
        "schema_version": SCHEMA_VERSION,
        "profile_name": profile.name,
        "profile_sha256": profile.profile_sha256,
        "profile_file": profile_file,
        "model": run_request["model"],
        "language": run_request.get("language"),
        "prompt_sha256": profile.prompt_sha256,
        "response_format": run_request["response_format"],
        "chunking_strategy": run_request.get("chunking_strategy"),
        "artifacts": {
            "chunks_dir": chunks_dir.relative_to(episode_dir).as_posix(),
            "chunking_manifest_path": (chunks_dir / CHUNKING_MANIFEST_FILENAME).relative_to(episode_dir).as_posix(),
            "transcript_dir": transcript_dir.relative_to(episode_dir).as_posix(),
            "transcription_metadata_path": transcription_metadata_path.relative_to(episode_dir).as_posix(),
            "transcription_raw_asr_path": raw_asr_path.relative_to(episode_dir).as_posix(),
            "transcription_markdown_path": (transcript_dir / TRANSCRIPTION_MARKDOWN_FILENAME).relative_to(
                episode_dir
            ).as_posix(),
        },
    }
    existing_metadata = _read_json_file_if_exists(transcription_metadata_path)
    if existing_metadata and existing_metadata != transcription_metadata and not args.force:
        raise RuntimeError("existing transcription_metadata.json has different transcription settings; rerun transcribe with --force")

    if args.force:
        selected_ids = {chunk.chunk_id for chunk in selected_chunks}
        existing_rows = [row for row in existing_rows if row.get("chunk_id") not in selected_ids]
        _write_jsonl_atomic(raw_asr_path, existing_rows)

    completed = 0
    skipped = 0
    for chunk in selected_chunks:
        audio_path = episode_dir / chunk.audio_path
        if not audio_path.exists():
            raise FileNotFoundError(f"chunk audio not found: {audio_path}")
        validate_upload_size(audio_path)

        duration_seconds = chunk.audio_duration_ms / 1000 if chunk.audio_duration_ms else None
        request = request_settings_for_profile(profile, duration_seconds)
        if _has_matching_row(
            existing_rows,
            chunk,
            profile_name=profile.name,
            profile_sha256=profile.profile_sha256,
            profile_file=profile_file,
            model=request["model"],
            language=request.get("language"),
            prompt_sha256=profile.prompt_sha256,
            response_format=request["response_format"],
            chunking_strategy=request.get("chunking_strategy"),
        ):
            skipped += 1
            print(f"skipped existing transcript: {chunk.chunk_id}")
            continue

        result = transcribe_audio_file(
            audio_path=audio_path,
            request=request,
        )
        row = {
            **chunk.to_dict(),
            "profile_name": profile.name,
            "profile_sha256": profile.profile_sha256,
            "profile_file": profile_file,
            "model": request["model"],
            "language": request.get("language"),
            "prompt_sha256": profile.prompt_sha256,
            "response_format": result["response_format"],
            "chunking_strategy": result["chunking_strategy"],
            "text": result["text"],
            "segments": enrich_segments_with_absolute_times(result["segments"], chunk),
            "raw_response": result["raw_response"],
        }
        _append_jsonl(raw_asr_path, row)
        existing_rows.append(row)
        completed += 1
        print(f"transcribed: {chunk.chunk_id}")

    print(f"transcription complete: {completed} written, {skipped} skipped")
    _write_json_file_atomic(transcription_metadata_path, transcription_metadata)
    return 0


def _cmd_merge(args: argparse.Namespace) -> int:
    episode_dir = _resolve(args.episode_dir)
    chunks_dir = _resolve(args.chunks_dir)
    transcript_dir = _resolve(args.transcript_dir)
    _require_inside(episode_dir, chunks_dir, "CHUNKS_DIR")
    _require_inside(episode_dir, transcript_dir, "TRANSCRIPT_DIR")
    merge_raw_asr_to_markdown(episode_dir, chunks_dir, transcript_dir)
    print(f"wrote merged Markdown: {transcript_dir / TRANSCRIPTION_MARKDOWN_FILENAME}")
    return 0


def _validate_chunk_dirs(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    episode_dir = _resolve(args.episode_dir)
    source_dir = _resolve(args.source_dir)
    chunks_dir = _resolve(args.chunks_dir)
    if not episode_dir.exists():
        raise FileNotFoundError(f"episode directory not found: {episode_dir}")
    _require_inside(episode_dir, source_dir, "SOURCE_DIR")
    _require_inside(episode_dir, chunks_dir, "CHUNKS_DIR")
    return episode_dir, source_dir, chunks_dir


def _resolve(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _require_inside(parent: Path, child: Path, label: str) -> None:
    parent = parent.resolve(strict=False)
    child = child.resolve(strict=False)
    try:
        child.relative_to(parent)
    except ValueError as exc:
        raise RuntimeError(f"{label} must be inside {parent}: {child}") from exc


def _manifest_matches_source(
    chunks: list[Chunk],
    episode_dir: Path,
    source_file: Path,
    chunk_seconds: int,
    overlap_seconds: int,
) -> bool:
    if not chunks:
        return False
    source_stat = source_file.stat()
    source_relative = source_file.relative_to(episode_dir).as_posix()
    requested_overlap_ms = overlap_seconds * 1000
    for chunk in chunks:
        if chunk.source_path != source_relative:
            return False
        if chunk.source_size_bytes != source_stat.st_size or chunk.source_mtime_ns != source_stat.st_mtime_ns:
            return False
        if chunk.chunk_seconds != chunk_seconds:
            return False
        if chunk.requested_overlap_ms != requested_overlap_ms:
            return False
    return True


def _validate_manifest_chunk_files(episode_dir: Path, chunks: list[Chunk]) -> None:
    for chunk in chunks:
        chunk_path = episode_dir / chunk.audio_path
        if not chunk_path.exists():
            raise RuntimeError(f"manifest references missing chunk: {chunk_path}")
        if chunk_path.stat().st_size != chunk.chunk_size_bytes:
            raise RuntimeError(f"manifest references stale chunk size: {chunk_path}")
        validate_upload_size(chunk_path)


def _chunking_metadata_for_chunks(episode_dir: Path, chunks_dir: Path, chunks: list[Chunk]) -> dict[str, Any]:
    if not chunks:
        raise RuntimeError("cannot write chunking_metadata.json without manifest chunks")
    first = chunks[0]
    chunk_dir = Path(first.audio_path).parent.as_posix()
    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "path": first.source_path,
            "name": first.source_name,
            "size_bytes": first.source_size_bytes,
            "mtime_ns": first.source_mtime_ns,
        },
        "chunk": {
            "chunks_dir": chunk_dir,
            "chunk_count": len(chunks),
            "chunk_seconds": first.chunk_seconds,
            "overlap_seconds": first.requested_overlap_ms // 1000,
            "requested_overlap_ms": first.requested_overlap_ms,
            "chunk_mode": first.chunk_mode,
            "format": first.chunk_format,
            "codec": first.chunk_codec,
            "sample_rate_hz": first.chunk_sample_rate_hz,
            "channels": first.chunk_channels,
            "bitrate": first.chunk_bitrate,
        },
        "artifacts": {
            "chunks_dir": chunks_dir.relative_to(episode_dir).as_posix(),
            "chunking_manifest_path": (chunks_dir / CHUNKING_MANIFEST_FILENAME).relative_to(episode_dir).as_posix(),
            "chunking_metadata_path": (chunks_dir / CHUNKING_METADATA_FILENAME).relative_to(episode_dir).as_posix(),
        },
    }


def _chunking_metadata_matches_chunks(
    metadata: dict[str, Any],
    episode_dir: Path,
    chunks_dir: Path,
    chunks: list[Chunk],
) -> bool:
    expected = _chunking_metadata_for_chunks(episode_dir, chunks_dir, chunks)
    return (
        metadata.get("schema_version") == SCHEMA_VERSION
        and metadata.get("source") == expected["source"]
        and metadata.get("chunk") == expected["chunk"]
        and metadata.get("artifacts") == expected["artifacts"]
    )


def _select_chunks(chunks: list[Chunk], args: argparse.Namespace) -> list[Chunk]:
    selected = chunks
    if args.chunk_id:
        selected = [chunk for chunk in selected if chunk.chunk_id == args.chunk_id]
    if args.start_index is not None:
        selected = [chunk for chunk in selected if chunk.chunk_index >= args.start_index]
    if args.end_index is not None:
        selected = [chunk for chunk in selected if chunk.chunk_index <= args.end_index]
    if args.limit is not None:
        if args.limit <= 0:
            raise RuntimeError("--limit must be greater than zero")
        selected = selected[: args.limit]
    return selected


def _read_jsonl_if_exists(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL row {line_number} in {path}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"invalid JSONL row {line_number} in {path}: expected an object")
            rows.append(payload)
    return rows


def _read_json_file_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON in {path}: expected an object")
    return payload


def _write_json_file_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    tmp_path.replace(path)


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def _has_matching_row(
    rows: list[dict[str, Any]],
    chunk: Chunk,
    *,
    profile_name: str,
    profile_sha256: str,
    profile_file: str,
    model: str,
    language: str | None,
    prompt_sha256: str | None,
    response_format: str,
    chunking_strategy: str | None,
) -> bool:
    for row in rows:
        if any(row.get(field) != value for field, value in chunk.to_dict().items()):
            continue
        if row.get("profile_name") != profile_name:
            continue
        if row.get("profile_sha256") != profile_sha256:
            continue
        if row.get("profile_file") != profile_file:
            continue
        if row.get("model") != model:
            continue
        if row.get("language") != language:
            continue
        if row.get("prompt_sha256") != prompt_sha256:
            continue
        if row.get("response_format") != response_format:
            continue
        if row.get("chunking_strategy") != chunking_strategy:
            continue
        return True
    return False


def enrich_segments_with_absolute_times(segments: list[dict[str, Any]] | None, chunk: Chunk) -> list[dict[str, Any]] | None:
    if segments is None:
        return None
    enriched: list[dict[str, Any]] = []
    for segment in segments:
        if not isinstance(segment, dict):
            enriched.append({"value": str(segment)})
            continue

        enriched_segment = dict(segment)
        start = segment.get("start")
        end = segment.get("end")
        if (
            isinstance(start, (int, float))
            and not isinstance(start, bool)
            and isinstance(end, (int, float))
            and not isinstance(end, bool)
            and end >= start
        ):
            relative_start_ms = int(round(start * 1000))
            relative_end_ms = int(round(end * 1000))
            absolute_start_ms = chunk.audio_start_ms + relative_start_ms
            absolute_end_ms = chunk.audio_start_ms + relative_end_ms
            if absolute_end_ms <= chunk.start_ms:
                overlap_role = "leading_context"
            elif absolute_start_ms >= chunk.end_ms:
                overlap_role = "trailing_context"
            elif absolute_start_ms < chunk.start_ms or absolute_end_ms > chunk.end_ms:
                overlap_role = "crosses_primary_boundary"
            else:
                overlap_role = "primary"
            enriched_segment.update(
                {
                    "relative_start_ms": relative_start_ms,
                    "relative_end_ms": relative_end_ms,
                    "absolute_start_ms": absolute_start_ms,
                    "absolute_end_ms": absolute_end_ms,
                    "overlap_role": overlap_role,
                }
            )
        enriched.append(enriched_segment)
    return enriched


def _load_local_env() -> None:
    pipeline_root = Path(__file__).resolve().parents[2]
    candidate = pipeline_root.parent / ".env"
    if candidate.exists():
        _load_env_file(candidate)


def _load_env_file(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip().strip("'").strip('"')
        os.environ[key] = value


if __name__ == "__main__":
    raise SystemExit(main())
