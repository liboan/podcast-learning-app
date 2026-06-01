from __future__ import annotations

from podcast_transcriber.manifest import Chunk


def sample_chunk(**overrides: object) -> Chunk:
    values = {
        "chunk_id": "chunk_000001",
        "chunk_index": 1,
        "audio_path": "chunks/chunk_000001.mp3",
        "start_ms": 0,
        "end_ms": 1000,
        "duration_ms": 1000,
        "audio_start_ms": 0,
        "audio_end_ms": 1500,
        "audio_duration_ms": 1500,
        "requested_overlap_ms": 500,
        "leading_context_ms": 0,
        "trailing_context_ms": 500,
        "chunk_mode": "fixed_context_padding",
        "source_path": "audio/sample.wav",
        "source_name": "sample.wav",
        "source_size_bytes": 123,
        "source_mtime_ns": 456,
        "chunk_seconds": 1,
        "chunk_format": "mp3",
        "chunk_codec": "libmp3lame",
        "chunk_sample_rate_hz": 16000,
        "chunk_channels": 1,
        "chunk_bitrate": "64k",
        "chunk_size_bytes": 789,
    }
    values.update(overrides)
    return Chunk(**values)
