# Add Context-Padded Raw Transcription Outputs and YAML Model Profiles

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Maintain this plan according to `.agent/PLANS.md`.

## Purpose / Big Picture

The transcription pipeline should produce richer raw evidence for later knowledge-base building. After this change, a caller can run the same episode through multiple explicit chunk/transcript directories, add context padding around chunk boundaries, and hand one or more self-describing transcript directories to a later cleaner or knowledge builder.

Context padding means each chunk still has one non-overlapped primary time range, but the audio sent to transcription also includes extra source audio before and after that primary range. This is sound because it gives ASR more boundary context while preserving timing metadata for a later model to identify duplicate overlap text. The cost is more uploaded audio, more ASR cost, and duplicate raw text near boundaries.

The transcription step should also move model-specific request details out of Python conditionals and into a YAML profile file. A profile names the model, response format, language, prompt behavior, and any model-specific options such as diarization chunking. This lets the user compare `gpt-4o-transcribe`, `gpt-4o-transcribe-diarize`, and later transcription models by adding or editing YAML profiles instead of editing `openai_client.py`.

This plan intentionally does not support old generated chunk manifests, old raw ASR rows, or previously transcribed chunks. Existing generated transcript/chunk outputs should be archived or discarded and regenerated.

## Progress

- [x] (2026-06-01 07:37Z) Inspected `podcast-transcription-pipeline/README.md`, current CLI code, tests, existing `transcription-pipeline.md`, `.agent/PLANS.md`, and current OpenAI speech-to-text docs.
- [x] (2026-06-01 07:37Z) Locked product choices: separate output dirs, context padding, chunk plus segment timestamps, caller-passed transcript dirs, and raw evidence only.
- [x] (2026-06-01 07:37Z) Revised the plan to drop backwards compatibility for existing generated transcript/chunk artifacts.
- [x] (2026-06-01 07:47Z) Wrote this standalone ExecPlan to disk without implementing code.
- [x] (2026-06-01 08:11Z) Replaced the manifest/raw ASR schema with v2 context-aware rows and clear regenerate-artifacts errors for old rows.
- [x] (2026-06-01 08:11Z) Added `--overlap-seconds` and deterministic per-chunk ffmpeg extraction with primary and padded audio intervals.
- [x] (2026-06-01 08:11Z) Added `transcription_run.json` metadata for chunk and transcription settings.
- [x] (2026-06-01 08:11Z) Preserved absolute segment timestamps in raw ASR rows when model output includes segment timing.
- [x] (2026-06-01 08:11Z) Updated Markdown merge output to expose context timing without trimming or de-duplicating raw text.
- [x] (2026-06-01 08:11Z) Updated README examples and tests for v2 manifests, context chunking, stale overlap detection, segment timing, merge output, and run metadata.
- [x] (2026-06-01 08:11Z) Ran unit tests with `PYTHONPATH=src python3 -m pytest tests`; all 6 tests passed.
- [x] (2026-06-01 08:11Z) Ran the synthetic ffmpeg smoke test with 3-second chunks and 1-second overlap; manifest intervals were `0-3000 audio 0-4000`, `3000-6000 audio 2000-7000`, and `6000-7000 audio 5000-7000`.
- [x] (2026-06-01 08:11Z) Initialized the real episode directory `test_transcribe/【PF2跑团replay】颂神之人-第1回 [BV1RrFczVEDF].f30280.normal/` and chunked the full source into 30s/5s and 600s/30s outputs without transcription.
- [x] (2026-06-01 08:34Z) Added a follow-on milestone to move model-specific transcription settings into YAML profiles.
- [x] (2026-06-01 08:28Z) Added YAML profile loading with `PyYAML>=6.0`, `yaml.safe_load`, profile lookup, prompt loading, and profile fingerprinting.
- [x] (2026-06-01 08:28Z) Replaced hard-coded diarization model branching with resolved profile request options.
- [x] (2026-06-01 08:28Z) Added `transcription_profiles.example.yaml` with `gpt-4o-transcribe` and `gpt-4o-transcribe-diarize` profiles.
- [x] (2026-06-01 08:28Z) Updated `transcribe` CLI, README examples, run metadata, raw ASR rows, and tests to use required YAML profiles.
- [x] (2026-06-01 08:28Z) Removed legacy direct `transcribe --model`, `--language`, and `--prompt-file` flags instead of maintaining compatibility paths.
- [x] (2026-06-01 08:28Z) Ran `PYTHONPATH=src python3 -m pytest tests`; all 9 tests passed.
- [x] (2026-06-01 08:32Z) Simplified `profiles.py` again after user review so it just loads a named YAML profile, resolves optional prompt text, fingerprints the file/name, and passes arbitrary options through.
- [x] (2026-06-01 08:36Z) Renamed checked-in example profiles to `4o-transcribe` and `4o-transcribe-diarize`, removed the Japanese PF2e prompt file, and omitted prompts from example profiles.
- [x] (2026-06-01 08:44Z) Changed prompt support to inline plaintext YAML strings and removed prompt-path loading.

## Surprises & Discoveries

- Observation: The current pipeline already accepts explicit `CHUNKS_DIR` and `TRANSCRIPT_DIR`, so multiple raw outputs can be supported without a run registry.
  Evidence: `podcast-transcriber chunk` and `transcribe` already route artifacts through caller-provided directories.

- Observation: Current chunk filenames and chunk IDs are local to one chosen chunk directory and transcript directory.
  Evidence: `audio.py` writes `chunk_000001.mp3`, and `merge.py` reads one `chunks_manifest.jsonl` plus one `raw_asr.jsonl`.

- Observation: Current OpenAI docs say `gpt-4o-transcribe-diarize` returns speaker segments with `speaker`, `start`, and `end` in `diarized_json`, requires `chunking_strategy` for inputs longer than 30 seconds, and does not support prompts.
  Evidence: Official docs at `https://developers.openai.com/api/docs/guides/speech-to-text#speaker-diarization`.

- Observation: The local shell exposes Python as `python3`, not `python`.
  Evidence: `PYTHONPATH=src python -m pytest tests` failed with `zsh:1: command not found: python`; `PYTHONPATH=src python3 -m pytest tests` passed.

- Observation: Deterministic per-chunk extraction produced the expected context-padded boundaries on synthetic and real audio.
  Evidence: The synthetic 7-second smoke test produced three rows with primary/audio intervals `(0, 3000, 0, 4000)`, `(3000, 6000, 2000, 7000)`, and `(6000, 7000, 5000, 7000)`. The real 30s/5s run produced 430 rows and the real 600s/30s run produced 22 rows.

- Observation: The current transcription request builder has model-specific branches in Python.
  Evidence: `openai_client.py` special-cases `gpt-4o-transcribe-diarize` to choose `diarized_json`, suppress prompts, and set `chunking_strategy="auto"` for longer chunks.

- Observation: Carrying old direct transcription flags would preserve an unused path and encourage future model-specific Python branches.
  Evidence: User review requested removing backwards compatibility for `--model`, `--language`, and `--prompt-file` rather than keeping deprecated fallback behavior.

- Observation: Profile loading should not try to validate model/provider semantics.
  Evidence: User review pointed out that future arbitrary models may need different request options, so `profiles.py` now just loads YAML fields, passes arbitrary `options` keys through, and only treats `{value: ..., when_audio_seconds_gt: ...}` as a generic conditional wrapper.

## Decision Log

- Decision: Use separate caller-provided chunk and transcript directories for multiple raw outputs.
  Rationale: This preserves the pipeline's explicit-directory design and avoids introducing a global episode registry. A later knowledge builder should accept one or more transcript directories explicitly.
  Date/Author: 2026-06-01 / planning.

- Decision: One transcript directory represents one coherent raw ASR output.
  Rationale: Mixing different chunk strategies or models in the same `raw_asr.jsonl` makes comparison and downstream cleaning harder. If model, prompt, language, or chunk settings differ, the caller should use a different transcript directory or pass `--force`.
  Date/Author: 2026-06-01 / planning.

- Decision: Add symmetrical context padding with `--overlap-seconds N`, defaulting to zero.
  Rationale: Existing default behavior remains conceptually the same for new runs, while `--overlap-seconds 20` includes up to 20 seconds before and after each primary chunk.
  Date/Author: 2026-06-01 / planning.

- Decision: Keep `start_ms`, `end_ms`, and `duration_ms` as the primary, non-overlapped source interval.
  Rationale: These fields should tell the later cleaner what source range this chunk is responsible for. New fields describe the larger audio interval sent to ASR.
  Date/Author: 2026-06-01 / planning.

- Decision: Do not reconcile or trim overlap text in this plan.
  Rationale: The raw pipeline's job is to preserve evidence. Cleaning, de-duplication, translation, and knowledge extraction belong in later stages.
  Date/Author: 2026-06-01 / planning.

- Decision: Do not provide backwards compatibility for old generated manifests, chunks, or raw transcripts.
  Rationale: The existing artifacts are disposable raw pipeline outputs. Supporting both schemas would add complexity in the exact layer we want to keep simple. Regenerating is clearer and produces uniform evidence for the knowledge builder.
  Date/Author: 2026-06-01 / user revision.

- Decision: Store this as a standalone plan in `podcast-transcription-pipeline/context-padded-raw-transcription-outputs.md`.
  Rationale: `.agent/PLANS.md` is the repository's ExecPlan instruction file, not the feature plan. Keeping this plan next to the transcription pipeline makes it easy for a future implementer to find without overwriting repository guidance.
  Date/Author: 2026-06-01 / planning.

- Decision: Store `transcription_run.json` as a compact source, chunk, artifact, and transcription settings record derived from the manifest.
  Rationale: The manifest remains the detailed row-level source of truth, while the run metadata makes each transcript directory self-describing without duplicating every chunk row.
  Date/Author: 2026-06-01 / implementation.

- Decision: For the live episode run, use the episode directory itself as `--source-dir`.
  Rationale: The source `.m4a` already lived directly inside the episode directory, and using the episode directory as the source directory avoided moving or copying the original audio while still satisfying the CLI's inside-episode safety checks.
  Date/Author: 2026-06-01 / implementation.

- Decision: Move model-specific transcription behavior into YAML profiles.
  Rationale: The pipeline should be able to compare transcription models without editing Python for every model-specific response format, prompt capability, language, or option. YAML is easier to edit by hand than JSON and can carry comments in local user copies.
  Date/Author: 2026-06-01 / user revision.

- Decision: Ship prefilled OpenAI profiles for `gpt-4o-transcribe` and `gpt-4o-transcribe-diarize`.
  Rationale: These are the two immediate comparison targets. The example profile names should be short labels, while the OpenAI model names remain in each profile's `model` field.
  Date/Author: 2026-06-01 / planning.

- Decision: Keep this as an OpenAI Audio Transcriptions profile system, not a full provider abstraction.
  Rationale: The current code only calls OpenAI's audio transcriptions endpoint. General provider abstraction would add unnecessary interfaces before there is a second provider to integrate.
  Date/Author: 2026-06-01 / planning.

- Decision: Remove direct `transcribe --model`, `--language`, and `--prompt-file` flags.
  Rationale: The project can regenerate raw artifacts from scratch, and keeping a second transcription configuration path adds maintenance cost without current value. Profiles are now the only transcription configuration interface.
  Date/Author: 2026-06-01 / implementation after user review.

- Decision: Treat profile `options` as generic OpenAI request options.
  Rationale: The profile system should support future transcription models without editing Python for each model's special keys. A mapping shaped as `{value: X, when_audio_seconds_gt: N}` remains useful for conditional request options such as chunking strategy, but the resolver does not validate model-specific semantics.
  Date/Author: 2026-06-01 / implementation after user review.

- Decision: Keep `profiles.py` intentionally thin.
  Rationale: The YAML file is the source of truth. The code should load the named profile, read an optional inline prompt string, fingerprint the profile file and name, and pass through arbitrary fields/options rather than trying to police every possible future model shape.
  Date/Author: 2026-06-01 / implementation after user review.

- Decision: Omit prompts from checked-in example profiles.
  Rationale: Prompt text is not settled yet. The model profiles should only establish model, language, response format, and options until a prompt is intentionally authored later.
  Date/Author: 2026-06-01 / implementation after user review.

- Decision: Store prompts inline in YAML profiles.
  Rationale: A separate prompt file loader made profile handling more complex than needed. If a profile needs a prompt later, it should use a plain `prompt: "..."` string in the YAML file.
  Date/Author: 2026-06-01 / implementation after user review.

## Outcomes & Retrospective

The context-padding milestone is implemented. The CLI now accepts `podcast-transcriber chunk ... --overlap-seconds N`, writes schema version 2 manifests with primary and padded audio intervals, writes `transcription_run.json`, enriches timed ASR segments with relative and absolute millisecond timestamps, and renders Markdown with primary interval headers plus audio interval and context metadata. Old generated manifest/raw rows are rejected with clear regeneration guidance instead of being migrated.

Validation passed with `PYTHONPATH=src python3 -m pytest tests` showing 6 passing tests. The synthetic ffmpeg smoke test also passed. The requested live episode was initialized and chunked into `chunks_30s_ctx5` / `asr_30s_ctx5` and `chunks_600s_ctx30` / `asr_600s_ctx30` without model transcription. The 30s/5s run produced 430 chunks, and the 600s/30s run produced 22 chunks. No `raw_asr.jsonl` file exists in either transcript directory, confirming that audio was not sent to a transcription model.

The YAML model-profile milestone is implemented. `transcribe` now requires `--profile-file` and `--profile`; direct `--model`, `--language`, and `--prompt-file` flags were removed. Profiles are loaded from YAML with `yaml.safe_load`, named profile lookup, optional inline prompt text, generic option pass-through, and profile-file fingerprinting. The OpenAI wrapper now receives an already resolved request dictionary and no longer imports or compares against a diarization model constant.

Validation passed with `PYTHONPATH=src python3 -m pytest tests` showing 9 passing tests. The tests cover example profile loading with omitted prompts, generic conditional options for diarization chunking, arbitrary option pass-through, profile metadata in `transcription_run.json` and `raw_asr.jsonl`, and profile fingerprint mismatch behavior on resume. No live model/API calls were made.

## Context and Orientation

The project lives under `podcast-transcription-pipeline`. The CLI entrypoint is `src/podcast_transcriber/cli.py`. Audio chunking is in `src/podcast_transcriber/audio.py`. Chunk JSONL serialization is in `src/podcast_transcriber/manifest.py`. OpenAI API calls are isolated in `src/podcast_transcriber/openai_client.py`. Markdown rendering is in `src/podcast_transcriber/merge.py`.

Raw ASR means raw automatic speech recognition output from the transcription API. Primary interval means the non-overlapped source time a chunk is responsible for covering. Audio interval means the actual source time included in the MP3 sent to the transcription API, including context padding. Segment means a timed span returned by a model response, usually with text and optionally speaker labels.

## Plan of Work

Replace the `Chunk` dataclass in `manifest.py` with a schema-versioned, context-aware shape. Do not make `Chunk.from_dict` fill defaults for old rows. If required fields are missing, raise a clear error telling the user to discard or regenerate generated artifacts.

The new chunk manifest rows must include:

    schema_version: 2
    chunk_id: "chunk_000001"
    chunk_index: 1
    audio_path: "CHUNKS_DIR_RELATIVE_TO_EPISODE/chunk_000001.mp3"
    start_ms: 0
    end_ms: 180000
    duration_ms: 180000
    audio_start_ms: 0
    audio_end_ms: 200000
    audio_duration_ms: 200000
    requested_overlap_ms: 20000
    leading_context_ms: 0
    trailing_context_ms: 20000
    chunk_mode: "fixed_context_padding"
    source_path: "SOURCE_DIR_RELATIVE_TO_EPISODE/SOURCE_AUDIO_NAME"
    source_name: "SOURCE_AUDIO_NAME"
    source_size_bytes: 123456
    source_mtime_ns: 1234567890
    chunk_seconds: 180
    chunk_format: "mp3"
    chunk_codec: "libmp3lame"
    chunk_sample_rate_hz: 16000
    chunk_channels: 1
    chunk_bitrate: "64k"
    chunk_size_bytes: 1440000

Update `chunk` CLI parsing in `cli.py` to accept `--overlap-seconds`, default `0`. Validate `chunk_seconds > 0`, `overlap_seconds >= 0`, and `overlap_seconds < chunk_seconds`. Include overlap fields in manifest matching, stale row checks, and raw ASR matching.

Replace the ffmpeg segment muxer approach in `audio.py` with deterministic per-chunk extraction. Compute primary intervals as fixed ranges of `chunk_seconds` over the source duration. For each primary interval, compute:

    audio_start_ms = max(0, start_ms - overlap_ms)
    audio_end_ms = min(source_duration_ms, end_ms + overlap_ms)
    leading_context_ms = start_ms - audio_start_ms
    trailing_context_ms = audio_end_ms - end_ms

Run ffmpeg once per chunk with `-ss`, `-t`, mono 16 kHz MP3, `libmp3lame`, and `64k`. Continue to validate every generated MP3 against the 25 MB upload limit. With zero overlap, new runs should have primary intervals equivalent to the old fixed chunking behavior, but the manifest schema is still v2 only.

Add `transcription_run.json` in every transcript directory. `chunk` creates or updates it with source metadata, chunk settings, relative artifact paths, and schema version. `transcribe` updates it with model, language, prompt hash, response format, and chunking strategy. If an existing run metadata file describes incompatible settings, fail clearly unless `--force` is used.

In `cli.py`, normalize model-returned segments before writing each raw ASR row. Preserve the original segment fields. When a segment has numeric `start` and `end` values, treat them as seconds relative to the uploaded chunk audio and add:

    relative_start_ms
    relative_end_ms
    absolute_start_ms
    absolute_end_ms
    overlap_role

Compute absolute times by adding `audio_start_ms`. Set `overlap_role` to `leading_context`, `primary`, `trailing_context`, or `crosses_primary_boundary`. If segment times are missing or invalid, leave the segment text intact and omit these added timing fields.

Update raw ASR rows to include all new chunk fields. The row-level `start_ms` and `end_ms` remain primary interval times. The row-level `audio_start_ms` and `audio_end_ms` show the actual source audio sent to the model.

Update `merge.py` to require v2 raw ASR rows and preserve all raw text. The Markdown section header should continue to use the primary interval. Add a short metadata line under each section showing the audio interval and context lengths. For timed segments, prefix rendered segment lines with absolute timestamps and mark non-primary context segments. Do not delete, trim, or de-duplicate overlap text.

Update `README.md` with two examples: one zero-overlap default run and one overlapping run. Document that multiple raw outputs are created by choosing separate chunk and transcript directories, for example one `gpt-4o-transcribe` directory with 180-second chunks and one `gpt-4o-transcribe-diarize` directory with 60-second chunks. State explicitly that old generated transcripts/chunks should be discarded and regenerated.

## Follow-on Milestone: YAML Transcription Profiles

Add profile-driven transcription configuration. A profile is a named YAML entry that resolves to one OpenAI audio transcription request shape. Model-specific details must live in YAML, not in `if model == ...` branches.

Create `podcast-transcription-pipeline/transcription_profiles.example.yaml` with this initial content. The file is an example for users to copy and edit, and tests may load it directly:

    version: 1
    profiles:
      4o-transcribe:
        provider: openai
        endpoint: audio.transcriptions
        model: gpt-4o-transcribe
        response_format: json
        language: ja
        options: {}

      4o-transcribe-diarize:
        provider: openai
        endpoint: audio.transcriptions
        model: gpt-4o-transcribe-diarize
        response_format: diarized_json
        language: ja
        options:
          chunking_strategy:
            value: auto
            when_audio_seconds_gt: 30

Omit prompts from the checked-in example profiles for now. If a profile needs a prompt later, put the prompt plaintext directly in the YAML string.

Add `PyYAML>=6.0` to `pyproject.toml`. Use `yaml.safe_load` only. Keep profile loading thin: find the named profile under `profiles`, read optional inline prompt text, fingerprint the profile file plus profile name, and otherwise pass profile fields through.

Add a new module, `src/podcast_transcriber/profiles.py`, with a dataclass or small typed structure that represents the resolved profile. It should expose:

    def load_profile(profile_file: Path, profile_name: str) -> TranscriptionProfile: ...

    def request_settings_for_profile(profile: TranscriptionProfile, duration_seconds: float | None) -> dict[str, Any]: ...

    def profile_fingerprint(profile_file: Path, profile_name: str) -> str: ...

`profile_fingerprint` should hash the profile file bytes plus the profile name, so reruns can detect profile changes even when the profile name stays the same.

Update `transcribe` CLI to prefer profiles:

    podcast-transcriber transcribe EPISODE_DIR --transcript-dir TRANSCRIPT_DIR --profile-file transcription_profiles.example.yaml --profile 4o-transcribe

    podcast-transcriber transcribe EPISODE_DIR --transcript-dir TRANSCRIPT_DIR --profile-file transcription_profiles.example.yaml --profile 4o-transcribe-diarize

The profile is the source of truth for `model`, `language`, `response_format`, prompt behavior, and model-specific `options`. Do not keep special cases in `openai_client.py` for diarization. `openai_client.py` should receive the resolved request settings and submit them to the OpenAI SDK.

For this milestone, remove existing direct flags such as `--model`, `--language`, and `--prompt-file`. Profiles are the only supported transcription configuration path. Do not add model-specific branches to replace those flags. New examples and new tests should use `--profile-file` and `--profile`.

When a profile has a non-empty `prompt` string, send that string to the transcription request and hash that exact UTF-8 text into `prompt_sha256`. Missing or empty prompt strings mean no prompt is sent and `prompt_sha256` is null.

When a profile option is written as a mapping with `value` and `when_audio_seconds_gt`, send that option only for uploaded chunk audio longer than the threshold. This reproduces the current diarization behavior without hard-coding the diarization model in Python while still allowing arbitrary future OpenAI request options to pass through.

Update `transcription_run.json` and each raw ASR row to include `profile_name`, `profile_sha256`, `profile_file`, `model`, `language`, `prompt_sha256`, `response_format`, and resolved model options such as `chunking_strategy`. Use relative paths where possible. Resuming should skip existing rows only when the chunk metadata and resolved profile metadata still match.

## Concrete Steps

Work from:

    cd podcast-transcription-pipeline

Update files in this order:

    src/podcast_transcriber/manifest.py
    src/podcast_transcriber/audio.py
    src/podcast_transcriber/cli.py
    src/podcast_transcriber/merge.py
    tests/test_manifest.py
    tests/test_merge.py
    new tests as needed under tests/
    README.md

Remove tests that assert old manifest compatibility. Add a test that an old-style manifest row fails with a clear regenerate-artifacts error.

For the YAML profile milestone, update files in this order:

    pyproject.toml
    transcription_profiles.example.yaml
    src/podcast_transcriber/profiles.py
    src/podcast_transcriber/openai_client.py
    src/podcast_transcriber/cli.py
    tests/test_profiles.py
    tests/test_cli.py
    README.md

The YAML profile milestone is complete when `openai_client.py` no longer imports or compares against a `DIARIZE_MODEL` constant. The OpenAI wrapper should only receive a resolved request dict, open the audio file, call `client.audio.transcriptions.create(file=audio_file, **request)`, and normalize the response.

Example intended usage for one output:

    EPISODE_DIR=test_episode
    SOURCE_DIR=test_episode/source
    CHUNKS_DIR=test_episode/chunks_180s_ctx20
    TRANSCRIPT_DIR=test_episode/asr_gpt4o_180s_ctx20

    podcast-transcriber init-episode "$EPISODE_DIR" --source-dir "$SOURCE_DIR" --chunks-dir "$CHUNKS_DIR" --transcript-dir "$TRANSCRIPT_DIR"
    podcast-transcriber chunk "$EPISODE_DIR" --source-dir "$SOURCE_DIR" --source-file "$SOURCE_DIR/episode.mp3" --chunks-dir "$CHUNKS_DIR" --transcript-dir "$TRANSCRIPT_DIR" --chunk-seconds 180 --overlap-seconds 20
    podcast-transcriber transcribe "$EPISODE_DIR" --transcript-dir "$TRANSCRIPT_DIR" --profile-file transcription_profiles.example.yaml --profile 4o-transcribe
    podcast-transcriber merge "$EPISODE_DIR" --transcript-dir "$TRANSCRIPT_DIR"

Example intended usage for a second raw output:

    CHUNKS_DIR=test_episode/chunks_60s_ctx20_diarize
    TRANSCRIPT_DIR=test_episode/asr_diarize_60s_ctx20

    podcast-transcriber chunk "$EPISODE_DIR" --source-dir "$SOURCE_DIR" --source-file "$SOURCE_DIR/episode.mp3" --chunks-dir "$CHUNKS_DIR" --transcript-dir "$TRANSCRIPT_DIR" --chunk-seconds 60 --overlap-seconds 20
    podcast-transcriber transcribe "$EPISODE_DIR" --transcript-dir "$TRANSCRIPT_DIR" --profile-file transcription_profiles.example.yaml --profile 4o-transcribe-diarize
    podcast-transcriber merge "$EPISODE_DIR" --transcript-dir "$TRANSCRIPT_DIR"

The future knowledge builder should be invoked with both transcript directories explicitly. Do not add directory scanning or an episode index in this plan.

## Validation and Acceptance

Run unit tests:

    PYTHONPATH=src python -m pytest tests

Add tests that prove:

- An old v1 manifest row fails with a clear error instructing regeneration.
- A v2 manifest row round-trips with `audio_start_ms`, `audio_end_ms`, and context fields.
- For a 125-second source, `--chunk-seconds 60 --overlap-seconds 20` produces primary intervals `0-60000`, `60000-120000`, `120000-125000` and audio intervals `0-80000`, `40000-125000`, `100000-125000`.
- Changing `--overlap-seconds` makes an existing manifest stale unless `--force` is used.
- Raw ASR segment normalization converts relative segment times to absolute source times using `audio_start_ms`.
- Markdown merge renders primary interval, audio interval, context lengths, and timed segment lines without dropping context text.
- `transcription_run.json` is created and records source, chunk, model, language, prompt hash, and artifact paths.
- YAML profiles load from `transcription_profiles.example.yaml`.
- The `4o-transcribe` profile resolves `model`, `language`, and `response_format`, with no prompt.
- The `4o-transcribe-diarize` profile resolves `response_format: diarized_json`, does not send prompts, and resolves `chunking_strategy: auto` only when uploaded audio duration is greater than 30 seconds.
- YAML profiles load from the named entry and pass arbitrary provider, endpoint, and option keys through without model-specific validation.
- `transcribe` writes `profile_name`, `profile_sha256`, `profile_file`, resolved model settings, and `prompt_sha256` into `transcription_run.json` and `raw_asr.jsonl`.
- Existing rows are skipped only when profile metadata still matches; changing the YAML profile file forces retranscription unless `--force` rewrites selected rows.

Run a synthetic smoke test if ffmpeg is available:

    EPISODE_DIR="$(mktemp -d)"
    SOURCE_DIR="$EPISODE_DIR/source"
    CHUNKS_DIR="$EPISODE_DIR/chunks_ctx2"
    TRANSCRIPT_DIR="$EPISODE_DIR/asr_ctx2"
    podcast-transcriber init-episode "$EPISODE_DIR" --source-dir "$SOURCE_DIR" --chunks-dir "$CHUNKS_DIR" --transcript-dir "$TRANSCRIPT_DIR"
    ffmpeg -hide_banner -loglevel error -f lavfi -i sine=frequency=1000:duration=7 -ar 16000 -ac 1 "$SOURCE_DIR/synthetic.wav"
    podcast-transcriber chunk "$EPISODE_DIR" --source-dir "$SOURCE_DIR" --source-file "$SOURCE_DIR/synthetic.wav" --chunks-dir "$CHUNKS_DIR" --transcript-dir "$TRANSCRIPT_DIR" --chunk-seconds 3 --overlap-seconds 1

Expected result: command exits 0, chunks are created, `chunks_manifest.jsonl` exists, and rows show audio intervals larger than primary intervals except where capped by source boundaries.

Acceptance is complete when overlap runs produce self-describing timestamp-aware raw artifacts, multiple raw outputs can coexist by using separate directories, old generated artifacts are rejected rather than migrated, and all tests pass.

## Idempotence and Recovery

`init-episode` remains safe to rerun. `chunk` remains safe to rerun with matching source and chunk settings. If source metadata, `chunk_seconds`, or `overlap_seconds` differ, fail unless `--force` is passed. `transcribe` resumes by matching source, chunk, overlap, profile name, profile hash, model, language, prompt hash, response format, and resolved options such as chunking strategy. `merge` remains safe to rerun and rewrites only `raw_asr.md`.

If old generated artifacts are present, do not migrate them. Archive or delete the old chunk/transcript directories, then rerun `chunk`, `transcribe`, and `merge`.

If per-chunk ffmpeg extraction fails halfway, rerun with `--force` to regenerate the transcript directory's chunks and manifest. Source audio must never be deleted.

## Interfaces and Dependencies

The context-padding milestone did not require a new third-party dependency. The YAML profile milestone must add `PyYAML>=6.0`. Continue using Python 3.11, ffmpeg/ffprobe, and the official OpenAI Python SDK.

Public CLI additions:

    podcast-transcriber chunk ... [--overlap-seconds N]

    podcast-transcriber transcribe EPISODE_DIR --transcript-dir TRANSCRIPT_DIR --profile-file PROFILE_YAML --profile PROFILE_NAME

Updated function signature:

    def chunk_audio(
        episode_dir: Path,
        source_dir: Path,
        source_path: Path,
        chunks_dir: Path,
        chunk_seconds: int,
        overlap_seconds: int = 0,
        force: bool = False,
    ) -> list[Chunk]: ...

Add a small helper, either in `cli.py` or a new internal module, with behavior equivalent to:

    def enrich_segments_with_absolute_times(segments: list[dict] | None, chunk: Chunk) -> list[dict] | None: ...

The helper must preserve original segment text and speaker labels.

Add profile interfaces in `profiles.py`:

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

    def load_profile(profile_file: Path, profile_name: str) -> TranscriptionProfile: ...

    def request_settings_for_profile(profile: TranscriptionProfile, duration_seconds: float | None) -> dict[str, Any]: ...

## Artifacts and Notes

Current official OpenAI documentation checked during planning:

    https://developers.openai.com/api/docs/guides/speech-to-text#transcriptions
    https://developers.openai.com/api/docs/guides/speech-to-text#speaker-diarization

Relevant constraints to preserve through YAML profile defaults:

- `gpt-4o-transcribe-diarize` should request `diarized_json` to receive speaker segments.
- `gpt-4o-transcribe-diarize` requires `chunking_strategy` for inputs longer than 30 seconds and `"auto"` is appropriate.
- Prompts are omitted from the checked-in example profiles for now.
- Segment timestamps from diarized output are relative to the uploaded chunk audio, so absolute source timestamps must add `audio_start_ms`.

## Revision Notes

2026-06-01: Created this standalone ExecPlan from the planning discussion. The user explicitly redirected from implementation to writing the plan to disk, so no pipeline code was changed as part of this revision.

2026-06-01: Implemented and validated the plan. This revision records the v2 schema, overlap chunking, self-describing transcript directories, tests, synthetic smoke output, and the requested real episode chunk outputs.

2026-06-01: Added the YAML transcription-profile milestone at the user's request. The goal is to replace model-specific Python branching with editable YAML profiles, prefilled for `gpt-4o-transcribe` and `gpt-4o-transcribe-diarize`, including declarative diarization options.

2026-06-01: Implemented the YAML transcription-profile milestone. During review, direct legacy transcribe flags were removed instead of retained, and profile options were simplified to generic request-option pass-through with an optional duration threshold wrapper.

2026-06-01: Simplified profile loading again after user review. `profiles.py` now avoids provider/endpoint/schema policing and behaves as a thin YAML loader plus optional prompt resolver and request-option builder.

2026-06-01: Removed the checked-in Japanese PF2e prompt and changed the example profile names to `4o-transcribe` and `4o-transcribe-diarize`. The example profiles now omit prompts.

2026-06-01: Removed prompt-path loading. Profiles now use a plain inline `prompt` YAML string, with empty strings treated as no prompt.
