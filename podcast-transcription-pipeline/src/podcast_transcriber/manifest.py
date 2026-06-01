from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    chunk_index: int
    audio_path: str
    start_ms: int
    end_ms: int
    duration_ms: int
    source_path: str
    source_name: str
    source_size_bytes: int
    source_mtime_ns: int
    chunk_seconds: int
    chunk_format: str
    chunk_codec: str
    chunk_sample_rate_hz: int
    chunk_channels: int
    chunk_bitrate: str
    chunk_size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Chunk":
        known_fields = {field.name for field in fields(cls)}
        missing = sorted(known_fields - data.keys())
        if missing:
            raise ValueError(f"manifest row missing required fields: {', '.join(missing)}")
        return cls(**{key: data[key] for key in known_fields})


def write_manifest(chunks: list[Chunk], manifest_path: Path) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk.to_dict(), ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    tmp_path.replace(manifest_path)


def read_manifest(manifest_path: Path) -> list[Chunk]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")

    chunks: list[Chunk] = []
    with manifest_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
                chunks.append(Chunk.from_dict(payload))
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid manifest row {line_number}: {exc}") from exc
    return chunks
