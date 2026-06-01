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
    force: bool = False,
) -> list[Chunk]:
    if chunk_seconds <= 0:
        raise RuntimeError("--chunk-seconds must be greater than zero")

    ensure_ffmpeg_available()
    episode_dir = episode_dir.resolve(strict=False)
    source_dir = source_dir.resolve(strict=False)
    source_path = source_path.resolve(strict=True)
    chunks_dir = chunks_dir.resolve(strict=False)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    if force:
        for old_chunk in chunks_dir.glob("chunk_*.mp3"):
            if old_chunk.is_file():
                old_chunk.unlink()

    duration_seconds = probe_duration_seconds(source_path)
    output_pattern = chunks_dir / "chunk_%06d.mp3"
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y" if force else "-n",
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
        "-f",
        "segment",
        "-segment_time",
        str(chunk_seconds),
        "-segment_start_number",
        "1",
        "-reset_timestamps",
        "1",
        str(output_pattern),
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"ffmpeg failed while chunking {source_path}: {detail}")

    chunk_files = sorted(chunks_dir.glob("chunk_*.mp3"))
    if not chunk_files:
        raise RuntimeError(f"ffmpeg did not create any chunks in {chunks_dir}")

    source_stat = source_path.stat()
    source_relative = source_path.relative_to(episode_dir).as_posix()
    chunks: list[Chunk] = []
    total_ms = int(round(duration_seconds * 1000))

    for chunk_index, chunk_file in enumerate(chunk_files, start=1):
        expected_name = f"chunk_{chunk_index:06d}.mp3"
        if chunk_file.name != expected_name:
            expected_path = chunks_dir / expected_name
            if expected_path.exists():
                raise RuntimeError(f"cannot rename {chunk_file.name}; {expected_name} already exists")
            chunk_file.rename(expected_path)
            chunk_file = expected_path

        validate_upload_size(chunk_file)
        start_ms = min((chunk_index - 1) * chunk_seconds * 1000, total_ms)
        end_ms = min(chunk_index * chunk_seconds * 1000, total_ms)
        chunks.append(
            Chunk(
                chunk_id=f"chunk_{chunk_index:06d}",
                chunk_index=chunk_index,
                audio_path=chunk_file.relative_to(episode_dir).as_posix(),
                start_ms=start_ms,
                end_ms=end_ms,
                duration_ms=max(0, end_ms - start_ms),
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

    expected_count = math.ceil(duration_seconds / chunk_seconds)
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
