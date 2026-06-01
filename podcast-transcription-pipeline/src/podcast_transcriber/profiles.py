from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class TranscriptionProfile:
    name: str
    profile_file: str
    profile_sha256: str
    provider: str
    endpoint: str
    model: str
    response_format: str
    language: str | None
    prompt: str | None
    prompt_sha256: str | None
    options: dict[str, Any]


def load_profile(profile_file: Path, profile_name: str) -> TranscriptionProfile:
    profile_path = profile_file.expanduser().resolve(strict=True)
    payload = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    profiles = payload.get("profiles") if isinstance(payload, dict) else {}
    raw_profile = profiles.get(profile_name) if isinstance(profiles, dict) else None
    if not isinstance(raw_profile, dict):
        raise ValueError(f"profile not found in {profile_path}: {profile_name}")

    prompt = raw_profile.get("prompt")
    prompt = prompt if isinstance(prompt, str) and prompt else None
    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest() if prompt else None
    options = raw_profile.get("options", {})
    if not isinstance(options, dict):
        options = {}

    return TranscriptionProfile(
        name=profile_name,
        profile_file=profile_path.as_posix(),
        profile_sha256=profile_fingerprint(profile_path, profile_name),
        provider=str(raw_profile.get("provider", "openai")),
        endpoint=str(raw_profile.get("endpoint", "audio.transcriptions")),
        model=str(raw_profile.get("model", profile_name)),
        response_format=str(raw_profile.get("response_format", "json")),
        language=raw_profile.get("language"),
        prompt=prompt,
        prompt_sha256=prompt_sha256,
        options=dict(options),
    )


def request_settings_for_profile(profile: TranscriptionProfile, duration_seconds: float | None) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model": profile.model,
        "response_format": profile.response_format,
    }
    if profile.language:
        request["language"] = profile.language
    if profile.prompt:
        request["prompt"] = profile.prompt
    for key, value in profile.options.items():
        if isinstance(value, dict) and "value" in value:
            threshold = value.get("when_audio_seconds_gt")
            passes_threshold = (
                threshold is None
                or isinstance(threshold, (int, float))
                and duration_seconds is not None
                and duration_seconds > threshold
            )
            if passes_threshold:
                request[key] = value["value"]
        else:
            request[key] = value
    return request


def profile_fingerprint(profile_file: Path, profile_name: str) -> str:
    profile_bytes = profile_file.expanduser().resolve(strict=True).read_bytes()
    digest = hashlib.sha256()
    digest.update(profile_bytes)
    digest.update(b"\0")
    digest.update(profile_name.encode("utf-8"))
    return digest.hexdigest()
