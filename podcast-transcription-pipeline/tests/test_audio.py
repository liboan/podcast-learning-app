from pathlib import Path
import shutil
import subprocess

import pytest

from podcast_transcriber.audio import chunk_audio


def test_context_padded_chunk_intervals_with_real_ffmpeg(tmp_path: Path) -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required for live chunk extraction")

    episode_dir = tmp_path
    source_dir = episode_dir / "source"
    chunks_dir = episode_dir / "chunks_ctx20"
    source_dir.mkdir()
    source_file = source_dir / "synthetic.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=125",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(source_file),
        ],
        check=True,
    )

    chunks = chunk_audio(
        episode_dir=episode_dir,
        source_dir=source_dir,
        source_path=source_file,
        chunks_dir=chunks_dir,
        chunk_seconds=60,
        overlap_seconds=20,
    )

    assert [(chunk.start_ms, chunk.end_ms) for chunk in chunks] == [
        (0, 60000),
        (60000, 120000),
        (120000, 125000),
    ]
    assert [(chunk.audio_start_ms, chunk.audio_end_ms) for chunk in chunks] == [
        (0, 80000),
        (40000, 125000),
        (100000, 125000),
    ]
    assert [chunk.requested_overlap_ms for chunk in chunks] == [20000, 20000, 20000]
    assert all((episode_dir / chunk.audio_path).exists() for chunk in chunks)
