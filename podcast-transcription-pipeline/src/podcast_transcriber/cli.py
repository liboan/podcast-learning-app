from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

from .audio import chunk_audio, validate_upload_size
from .manifest import Chunk, read_manifest, write_manifest
from .merge import merge_raw_asr_to_markdown
from .openai_client import DIARIZE_MODEL, request_settings_for_model, transcribe_audio_file


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
    _add_episode_dirs(init_parser)
    init_parser.set_defaults(func=_cmd_init_episode)

    chunk_parser = subparsers.add_parser("chunk", help="Create fixed-length MP3 chunks and a manifest.")
    _add_episode_dirs(chunk_parser)
    chunk_parser.add_argument("--source-file", required=True, type=Path)
    chunk_parser.add_argument("--chunk-seconds", type=int, default=180)
    chunk_parser.add_argument("--force", action="store_true")
    chunk_parser.set_defaults(func=_cmd_chunk)

    transcribe_parser = subparsers.add_parser("transcribe", help="Transcribe manifest chunks with OpenAI.")
    transcribe_parser.add_argument("episode_dir", type=Path)
    transcribe_parser.add_argument("--transcript-dir", required=True, type=Path)
    transcribe_parser.add_argument("--model", default="gpt-4o-transcribe")
    transcribe_parser.add_argument("--prompt-file", type=Path)
    transcribe_parser.add_argument("--language")
    transcribe_parser.add_argument("--chunk-id")
    transcribe_parser.add_argument("--start-index", type=int)
    transcribe_parser.add_argument("--end-index", type=int)
    transcribe_parser.add_argument("--limit", type=int)
    transcribe_parser.add_argument("--force", action="store_true")
    transcribe_parser.set_defaults(func=_cmd_transcribe)

    merge_parser = subparsers.add_parser("merge", help="Merge raw ASR JSONL into timestamped Markdown.")
    merge_parser.add_argument("episode_dir", type=Path)
    merge_parser.add_argument("--transcript-dir", required=True, type=Path)
    merge_parser.set_defaults(func=_cmd_merge)

    return parser


def _add_episode_dirs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("episode_dir", type=Path)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--chunks-dir", required=True, type=Path)
    parser.add_argument("--transcript-dir", required=True, type=Path)


def _cmd_init_episode(args: argparse.Namespace) -> int:
    episode_dir = _resolve(args.episode_dir)
    source_dir = _resolve(args.source_dir)
    chunks_dir = _resolve(args.chunks_dir)
    transcript_dir = _resolve(args.transcript_dir)

    episode_dir.mkdir(parents=True, exist_ok=True)
    _require_inside(episode_dir, source_dir, "SOURCE_DIR")
    _require_inside(episode_dir, chunks_dir, "CHUNKS_DIR")
    _require_inside(episode_dir, transcript_dir, "TRANSCRIPT_DIR")

    source_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    transcript_dir.mkdir(parents=True, exist_ok=True)
    print(f"initialized episode directory: {episode_dir}")
    return 0


def _cmd_chunk(args: argparse.Namespace) -> int:
    episode_dir, source_dir, chunks_dir, transcript_dir = _validate_episode_dirs(args)
    source_file = _resolve(args.source_file)
    if not source_file.exists():
        raise FileNotFoundError(f"source audio not found: {source_file}")
    if not source_file.is_file():
        raise RuntimeError(f"source audio is not a file: {source_file}")
    _require_inside(source_dir, source_file, "SOURCE_AUDIO")

    transcript_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = transcript_dir / "chunks_manifest.jsonl"

    if manifest_path.exists() and not args.force:
        chunks = read_manifest(manifest_path)
        if _manifest_matches_source(chunks, episode_dir, source_file, args.chunk_seconds):
            _validate_manifest_chunk_files(episode_dir, chunks)
            print(f"manifest already up to date: {manifest_path}")
            return 0
        raise RuntimeError("existing manifest does not match the source file or chunk settings; rerun chunk with --force")

    existing_chunks = sorted(chunks_dir.glob("chunk_*.mp3"))
    if existing_chunks and not args.force:
        raise RuntimeError(f"{chunks_dir} already contains generated chunks; rerun chunk with --force")

    chunks = chunk_audio(
        episode_dir=episode_dir,
        source_dir=source_dir,
        source_path=source_file,
        chunks_dir=chunks_dir,
        chunk_seconds=args.chunk_seconds,
        force=args.force,
    )
    write_manifest(chunks, manifest_path)
    print(f"wrote {len(chunks)} chunks and manifest: {manifest_path}")
    return 0


def _cmd_transcribe(args: argparse.Namespace) -> int:
    episode_dir = _resolve(args.episode_dir)
    transcript_dir = _resolve(args.transcript_dir)
    _require_inside(episode_dir, transcript_dir, "TRANSCRIPT_DIR")
    chunks = read_manifest(transcript_dir / "chunks_manifest.jsonl")
    selected_chunks = _select_chunks(chunks, args)
    if not selected_chunks:
        raise RuntimeError("no chunks matched the requested selection")

    prompt, prompt_sha256 = _read_prompt(args.prompt_file)
    effective_prompt = None if args.model == DIARIZE_MODEL else prompt
    effective_prompt_sha256 = None if args.model == DIARIZE_MODEL else prompt_sha256
    raw_asr_path = transcript_dir / "raw_asr.jsonl"
    existing_rows = _read_jsonl_if_exists(raw_asr_path)

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

        duration_seconds = chunk.duration_ms / 1000 if chunk.duration_ms else None
        response_format, chunking_strategy = request_settings_for_model(args.model, duration_seconds)
        if _has_matching_row(
            existing_rows,
            chunk,
            model=args.model,
            language=args.language,
            prompt_sha256=effective_prompt_sha256,
            response_format=response_format,
            chunking_strategy=chunking_strategy,
        ):
            skipped += 1
            print(f"skipped existing transcript: {chunk.chunk_id}")
            continue

        result = transcribe_audio_file(
            audio_path=audio_path,
            model=args.model,
            prompt=effective_prompt,
            language=args.language,
            duration_seconds=duration_seconds,
        )
        row = {
            **chunk.to_dict(),
            "model": args.model,
            "language": args.language,
            "prompt_sha256": effective_prompt_sha256,
            "response_format": result["response_format"],
            "chunking_strategy": result["chunking_strategy"],
            "text": result["text"],
            "segments": result["segments"],
            "raw_response": result["raw_response"],
        }
        _append_jsonl(raw_asr_path, row)
        existing_rows.append(row)
        completed += 1
        print(f"transcribed: {chunk.chunk_id}")

    print(f"transcription complete: {completed} written, {skipped} skipped")
    return 0


def _cmd_merge(args: argparse.Namespace) -> int:
    episode_dir = _resolve(args.episode_dir)
    transcript_dir = _resolve(args.transcript_dir)
    _require_inside(episode_dir, transcript_dir, "TRANSCRIPT_DIR")
    merge_raw_asr_to_markdown(episode_dir, transcript_dir)
    print(f"wrote merged Markdown: {transcript_dir / 'raw_asr.md'}")
    return 0


def _validate_episode_dirs(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    episode_dir = _resolve(args.episode_dir)
    source_dir = _resolve(args.source_dir)
    chunks_dir = _resolve(args.chunks_dir)
    transcript_dir = _resolve(args.transcript_dir)
    if not episode_dir.exists():
        raise FileNotFoundError(f"episode directory not found: {episode_dir}")
    _require_inside(episode_dir, source_dir, "SOURCE_DIR")
    _require_inside(episode_dir, chunks_dir, "CHUNKS_DIR")
    _require_inside(episode_dir, transcript_dir, "TRANSCRIPT_DIR")
    return episode_dir, source_dir, chunks_dir, transcript_dir


def _resolve(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _require_inside(parent: Path, child: Path, label: str) -> None:
    parent = parent.resolve(strict=False)
    child = child.resolve(strict=False)
    try:
        child.relative_to(parent)
    except ValueError as exc:
        raise RuntimeError(f"{label} must be inside {parent}: {child}") from exc


def _manifest_matches_source(chunks: list[Chunk], episode_dir: Path, source_file: Path, chunk_seconds: int) -> bool:
    if not chunks:
        return False
    source_stat = source_file.stat()
    source_relative = source_file.relative_to(episode_dir).as_posix()
    for chunk in chunks:
        if chunk.source_path != source_relative:
            return False
        if chunk.source_size_bytes != source_stat.st_size or chunk.source_mtime_ns != source_stat.st_mtime_ns:
            return False
        if chunk.chunk_seconds != chunk_seconds:
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


def _read_prompt(prompt_file: Path | None) -> tuple[str | None, str | None]:
    if prompt_file is None:
        return None, None
    prompt_path = _resolve(prompt_file)
    prompt_bytes = prompt_path.read_bytes()
    try:
        prompt = prompt_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"prompt file must be UTF-8: {prompt_path}") from exc
    return prompt, hashlib.sha256(prompt_bytes).hexdigest()


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
    model: str,
    language: str | None,
    prompt_sha256: str | None,
    response_format: str,
    chunking_strategy: str | None,
) -> bool:
    for row in rows:
        if row.get("chunk_id") != chunk.chunk_id:
            continue
        if row.get("source_path") != chunk.source_path:
            continue
        if row.get("source_size_bytes") != chunk.source_size_bytes:
            continue
        if row.get("source_mtime_ns") != chunk.source_mtime_ns:
            continue
        if row.get("chunk_seconds") != chunk.chunk_seconds:
            continue
        if row.get("chunk_format") != chunk.chunk_format:
            continue
        if row.get("chunk_size_bytes") != chunk.chunk_size_bytes:
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


def _load_local_env() -> None:
    candidates = [Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"]
    for candidate in candidates:
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
