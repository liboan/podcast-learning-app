import json
from pathlib import Path

from tests.helpers import sample_chunk

from podcast_transcriber.manifest import write_manifest
from podcast_transcriber.merge import merge_raw_asr_to_markdown


def test_merge_renders_context_timing_and_segments(tmp_path: Path) -> None:
    episode_dir = tmp_path
    transcript_dir = episode_dir / "transcripts"
    transcript_dir.mkdir()
    chunk = sample_chunk(
        start_ms=5000,
        end_ms=7000,
        duration_ms=2000,
        audio_start_ms=3000,
        audio_end_ms=9000,
        audio_duration_ms=6000,
        requested_overlap_ms=2000,
        leading_context_ms=2000,
        trailing_context_ms=2000,
        chunk_seconds=2,
    )
    write_manifest([chunk], transcript_dir / "chunks_manifest.jsonl")
    row = {
        **chunk.to_dict(),
        "model": "gpt-4o-transcribe",
        "language": None,
        "prompt_sha256": None,
        "response_format": "json",
        "chunking_strategy": None,
        "text": "leading primary trailing",
        "segments": [
            {
                "speaker": "S1",
                "text": "leading",
                "absolute_start_ms": 4000,
                "absolute_end_ms": 5000,
                "overlap_role": "leading_context",
            },
            {
                "speaker": "S1",
                "text": "primary",
                "absolute_start_ms": 5200,
                "absolute_end_ms": 6500,
                "overlap_role": "primary",
            },
            {
                "speaker": "S2",
                "text": "trailing",
                "absolute_start_ms": 7100,
                "absolute_end_ms": 8200,
                "overlap_role": "trailing_context",
            },
        ],
        "raw_response": {"text": "hello world"},
    }
    (transcript_dir / "raw_asr.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    markdown = merge_raw_asr_to_markdown(episode_dir, transcript_dir)

    assert "## 00:00:05-00:00:07" in markdown
    assert "Audio: 00:00:03-00:00:09; context: leading 00:00:02, trailing 00:00:02" in markdown
    assert "[00:00:04-00:00:05] [leading_context] **S1:** leading" in markdown
    assert "[00:00:05-00:00:06] **S1:** primary" in markdown
    assert "[00:00:07-00:00:08] [trailing_context] **S2:** trailing" in markdown
    assert (transcript_dir / "raw_asr.md").exists()
