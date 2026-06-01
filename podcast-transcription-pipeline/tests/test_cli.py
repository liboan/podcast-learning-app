import json
from pathlib import Path
from typing import Any

from tests.helpers import sample_chunk

from podcast_transcriber import cli
from podcast_transcriber.manifest import write_manifest


def test_chunk_rerun_tracks_overlap_in_manifest_and_chunking_metadata(tmp_path: Path) -> None:
    episode_dir = tmp_path
    source_dir = episode_dir / "source"
    chunks_dir = episode_dir / "chunks_ctx5"
    source_dir.mkdir()
    chunks_dir.mkdir()
    source_file = source_dir / "episode.wav"
    source_file.write_bytes(b"source audio")
    chunk_file = chunks_dir / "chunk_000001.mp3"
    chunk_file.write_bytes(b"fake")
    source_stat = source_file.stat()
    chunk = sample_chunk(
        audio_path="chunks_ctx5/chunk_000001.mp3",
        source_path="source/episode.wav",
        source_name="episode.wav",
        source_size_bytes=source_stat.st_size,
        source_mtime_ns=source_stat.st_mtime_ns,
        chunk_seconds=30,
        requested_overlap_ms=5000,
        leading_context_ms=0,
        trailing_context_ms=5000,
        chunk_size_bytes=chunk_file.stat().st_size,
    )
    write_manifest([chunk], chunks_dir / "chunking_manifest.jsonl")

    ok = cli.main(
        [
            "chunk",
            str(episode_dir),
            "--source-dir",
            str(source_dir),
            "--source-file",
            str(source_file),
            "--chunks-dir",
            str(chunks_dir),
            "--chunk-seconds",
            "30",
            "--overlap-seconds",
            "5",
        ]
    )
    stale = cli.main(
        [
            "chunk",
            str(episode_dir),
            "--source-dir",
            str(source_dir),
            "--source-file",
            str(source_file),
            "--chunks-dir",
            str(chunks_dir),
            "--chunk-seconds",
            "30",
            "--overlap-seconds",
            "10",
        ]
    )

    metadata = json.loads((chunks_dir / "chunking_metadata.json").read_text(encoding="utf-8"))
    assert ok == 0
    assert stale == 1
    assert metadata["schema_version"] == 2
    assert metadata["source"]["path"] == "source/episode.wav"
    assert metadata["chunk"]["chunks_dir"] == "chunks_ctx5"
    assert metadata["chunk"]["chunk_seconds"] == 30
    assert metadata["chunk"]["overlap_seconds"] == 5
    assert metadata["artifacts"]["chunking_manifest_path"] == "chunks_ctx5/chunking_manifest.jsonl"
    assert metadata["artifacts"]["chunking_metadata_path"] == "chunks_ctx5/chunking_metadata.json"


def test_transcribe_writes_transcription_metadata_and_absolute_segment_times(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    episode_dir = tmp_path
    chunks_dir = episode_dir / "chunks_ctx2"
    transcript_dir = episode_dir / "asr_ctx2"
    chunks_dir.mkdir()
    chunk_file = chunks_dir / "chunk_000001.mp3"
    chunk_file.write_bytes(b"fake mp3")
    chunk = sample_chunk(
        audio_path="chunks_ctx2/chunk_000001.mp3",
        start_ms=5000,
        end_ms=8000,
        duration_ms=3000,
        audio_start_ms=3000,
        audio_end_ms=10000,
        audio_duration_ms=7000,
        requested_overlap_ms=2000,
        leading_context_ms=2000,
        trailing_context_ms=2000,
        chunk_seconds=3,
        chunk_size_bytes=chunk_file.stat().st_size,
    )
    write_manifest([chunk], chunks_dir / "chunking_manifest.jsonl")
    profile_file = episode_dir / "profiles.yaml"
    profile_file.write_text(
        """
version: 1
profiles:
  4o-transcribe:
    provider: openai
    endpoint: audio.transcriptions
    model: gpt-4o-transcribe
    response_format: json
    language: ja
    options: {}
""",
        encoding="utf-8",
    )

    def fake_transcribe_audio_file(**kwargs: object) -> dict[str, object]:
        request = kwargs["request"]
        assert isinstance(request, dict)
        assert "prompt" not in request
        return {
            "response_format": "json",
            "chunking_strategy": None,
            "text": "hello",
            "segments": [{"speaker": "S1", "start": 1.5, "end": 4.5, "text": "hello"}],
            "raw_response": {"text": "hello"},
        }

    monkeypatch.setattr(cli, "transcribe_audio_file", fake_transcribe_audio_file)
    exit_code = cli.main(
        [
            "transcribe",
            str(episode_dir),
            "--chunks-dir",
            str(chunks_dir),
            "--transcript-dir",
            str(transcript_dir),
            "--profile-file",
            str(profile_file),
            "--profile",
            "4o-transcribe",
        ]
    )

    row = json.loads((transcript_dir / "transcription_raw_asr.jsonl").read_text(encoding="utf-8").strip())
    transcription = json.loads((transcript_dir / "transcription_metadata.json").read_text(encoding="utf-8"))
    segment = row["segments"][0]
    assert exit_code == 0
    assert transcript_dir.exists()
    assert segment["relative_start_ms"] == 1500
    assert segment["absolute_start_ms"] == 4500
    assert segment["absolute_end_ms"] == 7500
    assert segment["overlap_role"] == "crosses_primary_boundary"
    assert transcription == {
        "schema_version": 2,
        "profile_name": "4o-transcribe",
        "profile_sha256": transcription["profile_sha256"],
        "profile_file": transcription["profile_file"],
        "model": "gpt-4o-transcribe",
        "language": "ja",
        "prompt_sha256": None,
        "response_format": "json",
        "chunking_strategy": None,
        "artifacts": {
            "transcript_dir": "asr_ctx2",
            "chunks_dir": "chunks_ctx2",
            "chunking_manifest_path": "chunks_ctx2/chunking_manifest.jsonl",
            "transcription_metadata_path": "asr_ctx2/transcription_metadata.json",
            "transcription_raw_asr_path": "asr_ctx2/transcription_raw_asr.jsonl",
            "transcription_markdown_path": "asr_ctx2/transcription_raw_asr.md",
        },
    }
    assert row["profile_name"] == "4o-transcribe"
    assert row["profile_sha256"] == transcription["profile_sha256"]
    assert row["profile_file"] == transcription["profile_file"]


def test_transcribe_profile_fingerprint_controls_resume(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    episode_dir = tmp_path
    chunks_dir = episode_dir / "chunks_ctx2"
    transcript_dir = episode_dir / "asr_ctx2"
    chunks_dir.mkdir()
    chunk_file = chunks_dir / "chunk_000001.mp3"
    chunk_file.write_bytes(b"fake mp3")
    chunk = sample_chunk(audio_path="chunks_ctx2/chunk_000001.mp3", chunk_size_bytes=chunk_file.stat().st_size)
    write_manifest([chunk], chunks_dir / "chunking_manifest.jsonl")
    profile_file = episode_dir / "profiles.yaml"
    profile_text = """
version: 1
profiles:
  basic:
    provider: openai
    endpoint: audio.transcriptions
    model: gpt-4o-transcribe
    response_format: json
    language: ja
    options: {}
"""
    profile_file.write_text(profile_text, encoding="utf-8")
    calls: list[dict[str, object]] = []

    def fake_transcribe_audio_file(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "response_format": "json",
            "chunking_strategy": None,
            "text": "hello",
            "segments": None,
            "raw_response": {"text": "hello"},
        }

    monkeypatch.setattr(cli, "transcribe_audio_file", fake_transcribe_audio_file)
    argv = [
        "transcribe",
        str(episode_dir),
        "--chunks-dir",
        str(chunks_dir),
        "--transcript-dir",
        str(transcript_dir),
        "--profile-file",
        str(profile_file),
        "--profile",
        "basic",
    ]

    assert cli.main(argv) == 0
    assert cli.main(argv) == 0
    profile_file.write_text(profile_text + "\n", encoding="utf-8")
    assert cli.main(argv) == 1
    assert cli.main([*argv, "--force"]) == 0
    rows = [
        json.loads(line)
        for line in (transcript_dir / "transcription_raw_asr.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(calls) == 2
    assert len(rows) == 1
