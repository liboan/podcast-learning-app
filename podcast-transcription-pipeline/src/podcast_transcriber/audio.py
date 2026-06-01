from __future__ import annotations

import math
from pathlib import Path
import shutil
import subprocess

from .manifest import Chunk


MAX_UPLOAD_BYTES = 25_000_000
CHUNK_CODEC = "libmp3lame"
CHUNK_SAMPLE_RATE_HZ = 16000
CHUNK_CHANNELS = 1
CHUNK_BITRATE = "64k"
CHUNK_FORMAT = "mp3"


def ensure_ffmpeg_available() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError(
            "ffmpeg/ffprobe not found. Install ffmpeg and ensure both ffmpeg and ffprobe are available on PATH."
        )


def probe_duration_seconds(source_path: Path) -> float:
    ensure_ffmpeg_available()
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(source_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {source_path}: {result.stderr.strip()}")
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"ffprobe returned an invalid duration for {source_path}") from exc
    if duration <= 0:
        raise RuntimeError(f"audio duration must be positive: {source_path}")
    return duration


def chunk_audio(
    episode_dir: Path,
    source_dir: Path,
    source_path: Path,
    chunks_dir: Path,
    chunk_seconds: int,
    overlap_seconds: int = 0,
    force: bool = False,
) -> list[Chunk]:
    if chunk_seconds <= 0:
        raise RuntimeError("--chunk-seconds must be greater than zero")
    if overlap_seconds < 0:
        raise RuntimeError("--overlap-seconds must be zero or greater")
    if overlap_seconds >= chunk_seconds:
        raise RuntimeError("--overlap-seconds must be less than --chunk-seconds")

    ensure_ffmpeg_available()
    episode_dir = episode_dir.resolve(strict=False)
    source_dir = source_dir.resolve(strict=False)
    source_path = source_path.resolve(strict=True)
    chunks_dir = chunks_dir.resolve(strict=False)
    try:
        source_path.relative_to(source_dir)
    except ValueError as exc:
        raise RuntimeError(f"source audio must be inside source_dir: {source_path}") from exc
    chunks_dir.mkdir(parents=True, exist_ok=True)

    if force:
        for old_chunk in chunks_dir.glob("chunk_*.mp3"):
            if old_chunk.is_file():
                old_chunk.unlink()

    duration_seconds = probe_duration_seconds(source_path)
    source_stat = source_path.stat()
    source_relative = source_path.relative_to(episode_dir).as_posix()
    chunks: list[Chunk] = []
    total_ms = int(round(duration_seconds * 1000))
    chunk_ms = chunk_seconds * 1000
    overlap_ms = overlap_seconds * 1000
    expected_count = math.ceil(total_ms / chunk_ms)

    for chunk_index in range(1, expected_count + 1):
        start_ms = min((chunk_index - 1) * chunk_ms, total_ms)
        end_ms = min(chunk_index * chunk_ms, total_ms)
        audio_start_ms = max(0, start_ms - overlap_ms)
        audio_end_ms = min(total_ms, end_ms + overlap_ms)
        audio_duration_ms = audio_end_ms - audio_start_ms
        chunk_file = chunks_dir / f"chunk_{chunk_index:06d}.mp3"
        if chunk_file.exists() and not force:
            raise RuntimeError(f"{chunk_file} already exists; rerun chunk with --force")

        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y" if force else "-n",
            "-ss",
            f"{audio_start_ms / 1000:.3f}",
            "-t",
            f"{audio_duration_ms / 1000:.3f}",
            "-i",
            str(source_path),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            str(CHUNK_CHANNELS),
            "-ar",
            str(CHUNK_SAMPLE_RATE_HZ),
            "-codec:a",
            CHUNK_CODEC,
            "-b:a",
            CHUNK_BITRATE,
            str(chunk_file),
        ]
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"ffmpeg failed while creating {chunk_file}: {detail}")

        validate_upload_size(chunk_file)
        chunks.append(
            Chunk(
                chunk_id=f"chunk_{chunk_index:06d}",
                chunk_index=chunk_index,
                audio_path=chunk_file.relative_to(episode_dir).as_posix(),
                start_ms=start_ms,
                end_ms=end_ms,
                duration_ms=max(0, end_ms - start_ms),
                audio_start_ms=audio_start_ms,
                audio_end_ms=audio_end_ms,
                audio_duration_ms=audio_duration_ms,
                requested_overlap_ms=overlap_ms,
                leading_context_ms=start_ms - audio_start_ms,
                trailing_context_ms=audio_end_ms - end_ms,
                chunk_mode="fixed_context_padding",
                source_path=source_relative,
                source_name=source_path.name,
                source_size_bytes=source_stat.st_size,
                source_mtime_ns=source_stat.st_mtime_ns,
                chunk_seconds=chunk_seconds,
                chunk_format=CHUNK_FORMAT,
                chunk_codec=CHUNK_CODEC,
                chunk_sample_rate_hz=CHUNK_SAMPLE_RATE_HZ,
                chunk_channels=CHUNK_CHANNELS,
                chunk_bitrate=CHUNK_BITRATE,
                chunk_size_bytes=chunk_file.stat().st_size,
            )
        )

    if len(chunks) != expected_count:
        raise RuntimeError(f"expected {expected_count} chunks, but ffmpeg created {len(chunks)}")
    return chunks


def validate_upload_size(audio_path: Path, max_bytes: int = MAX_UPLOAD_BYTES) -> None:
    size = audio_path.stat().st_size
    if size >= max_bytes:
        raise RuntimeError(
            f"{audio_path} is {size} bytes, which is at or above the {max_bytes} byte upload limit. "
            "Rerun chunk with a smaller --chunk-seconds value."
        )
