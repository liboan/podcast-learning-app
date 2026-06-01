from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def transcribe_audio_file(audio_path: Path, request: dict[str, Any]) -> dict[str, Any]:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set. Export it in your shell or load it from a local .env file.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The OpenAI Python SDK is not installed. Run `python -m pip install -e .`.") from exc

    client = OpenAI()
    with audio_path.open("rb") as audio_file:
        response = client.audio.transcriptions.create(file=audio_file, **dict(request))

    raw_response = _response_to_dict(response)
    return {
        "text": _extract_text(response, raw_response),
        "segments": _extract_segments(response, raw_response),
        "raw_response": raw_response,
        "response_format": request.get("response_format"),
        "chunking_strategy": request.get("chunking_strategy"),
    }


def _response_to_dict(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    if hasattr(response, "model_dump"):
        return response.model_dump()
    if hasattr(response, "to_dict"):
        return response.to_dict()
    text = getattr(response, "text", None)
    if text is not None:
        return {"text": text}
    return {"value": str(response)}


def _extract_text(response: Any, raw_response: dict[str, Any]) -> str:
    text = raw_response.get("text")
    if isinstance(text, str):
        return text
    response_text = getattr(response, "text", "")
    return response_text if isinstance(response_text, str) else str(response_text)


def _extract_segments(response: Any, raw_response: dict[str, Any]) -> list[dict[str, Any]] | None:
    segments = raw_response.get("segments")
    if segments is None:
        segments = getattr(response, "segments", None)
    if segments is None:
        return None
    normalized: list[dict[str, Any]] = []
    for segment in segments:
        if isinstance(segment, dict):
            normalized.append(segment)
        elif hasattr(segment, "model_dump"):
            normalized.append(segment.model_dump())
        elif hasattr(segment, "to_dict"):
            normalized.append(segment.to_dict())
        else:
            normalized.append({"value": str(segment)})
    return normalized
