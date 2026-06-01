from pathlib import Path

from podcast_transcriber.manifest import Chunk, read_manifest, write_manifest


def test_manifest_round_trip(tmp_path: Path) -> None:
    chunk = Chunk(
        chunk_id="chunk_000001",
        chunk_index=1,
        audio_path="chunks/chunk_000001.mp3",
        start_ms=0,
        end_ms=1000,
        duration_ms=1000,
        source_path="audio/sample.wav",
        source_name="sample.wav",
        source_size_bytes=123,
        source_mtime_ns=456,
        chunk_seconds=1,
        chunk_format="mp3",
        chunk_codec="libmp3lame",
        chunk_sample_rate_hz=16000,
        chunk_channels=1,
        chunk_bitrate="64k",
        chunk_size_bytes=789,
    )

    manifest_path = tmp_path / "chunks_manifest.jsonl"
    write_manifest([chunk], manifest_path)

    assert read_manifest(manifest_path) == [chunk]
