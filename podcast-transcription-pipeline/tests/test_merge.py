import json
from pathlib import Path

from podcast_transcriber.manifest import Chunk, write_manifest
from podcast_transcriber.merge import merge_raw_asr_to_markdown


def test_merge_writes_timestamped_markdown(tmp_path: Path) -> None:
    episode_dir = tmp_path
    transcript_dir = episode_dir / "transcripts"
    transcript_dir.mkdir()
    chunk = Chunk(
        chunk_id="chunk_000001",
        chunk_index=1,
        audio_path="chunks/chunk_000001.mp3",
        start_ms=0,
        end_ms=2000,
        duration_ms=2000,
        source_path="audio/sample.wav",
        source_name="sample.wav",
        source_size_bytes=123,
        source_mtime_ns=456,
        chunk_seconds=2,
        chunk_format="mp3",
        chunk_codec="libmp3lame",
        chunk_sample_rate_hz=16000,
        chunk_channels=1,
        chunk_bitrate="64k",
        chunk_size_bytes=789,
    )
    write_manifest([chunk], transcript_dir / "chunks_manifest.jsonl")
    row = {
        **chunk.to_dict(),
        "model": "gpt-4o-transcribe",
        "language": None,
        "prompt_sha256": None,
        "response_format": "json",
        "chunking_strategy": None,
        "text": "hello world",
        "segments": None,
        "raw_response": {"text": "hello world"},
    }
    (transcript_dir / "raw_asr.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    markdown = merge_raw_asr_to_markdown(episode_dir, transcript_dir)

    assert "## 00:00:00-00:00:02" in markdown
    assert "hello world" in markdown
    assert (transcript_dir / "raw_asr.md").exists()
