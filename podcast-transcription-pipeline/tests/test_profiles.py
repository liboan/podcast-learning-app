from pathlib import Path

from podcast_transcriber.profiles import load_profile, profile_fingerprint, request_settings_for_profile


def test_example_profiles_resolve_model_settings_and_diarization_options() -> None:
    profile_file = Path("transcription_profiles.example.yaml")

    regular = load_profile(profile_file, "4o-transcribe")
    diarize = load_profile(profile_file, "4o-transcribe-diarize")

    regular_request = request_settings_for_profile(regular, 120)
    assert regular_request["model"] == "gpt-4o-transcribe"
    assert regular_request["language"] == regular.language
    assert regular_request["response_format"] == "json"
    assert "prompt" not in regular_request
    assert regular.prompt_sha256 is None
    assert profile_fingerprint(profile_file, "4o-transcribe") == regular.profile_sha256

    short_request = request_settings_for_profile(diarize, 30)
    long_request = request_settings_for_profile(diarize, 30.1)
    assert short_request["response_format"] == "diarized_json"
    assert "prompt" not in short_request
    assert "chunking_strategy" not in short_request
    assert long_request["chunking_strategy"] == "auto"


def test_profile_loader_passes_through_arbitrary_options(tmp_path: Path) -> None:
    profile_file = tmp_path / "profiles.yaml"
    profile_file.write_text(
        """
version: 1
profiles:
  custom:
    provider: another-provider
    endpoint: some.future.endpoint
    model: future-model
    response_format: verbose_json
    language: zh
    prompt: inline context
    options:
      temperature: 0
      custom_mode: careful
      nested_option:
        enabled: true
      only_for_long_audio:
        value: enabled
        when_audio_seconds_gt: 10
""",
        encoding="utf-8",
    )

    profile = load_profile(profile_file, "custom")
    short_request = request_settings_for_profile(profile, 10)
    long_request = request_settings_for_profile(profile, 11)

    assert profile.provider == "another-provider"
    assert profile.endpoint == "some.future.endpoint"
    assert profile.prompt == "inline context"
    assert profile.prompt_sha256
    assert short_request == {
        "model": "future-model",
        "response_format": "verbose_json",
        "language": "zh",
        "prompt": "inline context",
        "temperature": 0,
        "custom_mode": "careful",
        "nested_option": {"enabled": True},
    }
    assert long_request["only_for_long_audio"] == "enabled"
