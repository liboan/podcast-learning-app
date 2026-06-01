from pathlib import Path

import pytest

from podcast_transcriber.manifest import read_manifest, write_manifest

from tests.helpers import sample_chunk


def test_manifest_round_trip(tmp_path: Path) -> None:
    chunk = sample_chunk()

    manifest_path = tmp_path / "chunking_manifest.jsonl"
    write_manifest([chunk], manifest_path)

    assert read_manifest(manifest_path) == [chunk]
    row = read_manifest(manifest_path)[0].to_dict()
    assert row["schema_version"] == 2
    assert row["audio_start_ms"] == 0
    assert row["audio_end_ms"] == 1500
    assert row["trailing_context_ms"] == 500


def test_old_manifest_row_explains_regeneration(tmp_path: Path) -> None:
    manifest_path = tmp_path / "chunking_manifest.jsonl"
    manifest_path.write_text('{"chunk_id": "chunk_000001"}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="regenerate"):
        read_manifest(manifest_path)
