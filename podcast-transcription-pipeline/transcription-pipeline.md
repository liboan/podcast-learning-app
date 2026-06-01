# Build a Local Podcast Transcription Pipeline

This ExecPlan is a living document. Keep `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` current as work proceeds.

If `.agent/PLANS.md` exists, follow it. This plan is otherwise self-contained.

## Purpose / Big Picture

Build a small local CLI that turns any local podcast or long-form audio file
into a timestamped raw transcript.

The user explicitly chooses an episode directory, source audio file, and all
working/output directories:

    podcast-transcriber init-episode EPISODE_DIR --source-dir SOURCE_DIR --chunks-dir CHUNKS_DIR --transcript-dir TRANSCRIPT_DIR
    podcast-transcriber chunk EPISODE_DIR --source-dir SOURCE_DIR --source-file SOURCE_AUDIO --chunks-dir CHUNKS_DIR --transcript-dir TRANSCRIPT_DIR
    podcast-transcriber transcribe EPISODE_DIR --transcript-dir TRANSCRIPT_DIR
    podcast-transcriber merge EPISODE_DIR --transcript-dir TRANSCRIPT_DIR

The pipeline writes:

    TRANSCRIPT_DIR/chunks_manifest.jsonl
    TRANSCRIPT_DIR/raw_asr.jsonl
    TRANSCRIPT_DIR/raw_asr.md

`EPISODE_DIR` can be any writable directory. `SOURCE_AUDIO` must be a local
audio file under `SOURCE_DIR`. Do not depend on a specific episode name,
repository name, parent directory, source filename, or fixed folder layout. Do
not infer `SOURCE_DIR`, `CHUNKS_DIR`, or `TRANSCRIPT_DIR`; the user must pass
them.

The pipeline does not download episodes, build a web app, use a database,
translate text, or repair transcripts. It prepares audio, chunks it, calls the
OpenAI transcription API, and merges raw output.

## Progress

- [x] Create a project-level `.venv` and document setup.
- [x] Create an installable Python CLI package.
- [x] Implement episode directory initialization and validation.
- [x] Implement fixed-length MP3 audio chunking with `ffmpeg`.
- [x] Write a JSONL chunk manifest with source metadata and timestamps.
- [x] Implement OpenAI transcription calls.
- [x] Make transcription resumable without accepting stale rows.
- [x] Implement Markdown merge output.
- [x] Add `.env.example`, `.gitignore`, README usage, and smoke tests.
- [x] Validate chunking with synthetic audio.
- [x] Validate transcription with a short real speech sample when an API key is available.
- [x] Update this ExecPlan with discoveries, decisions, and outcomes.

## Surprises & Discoveries

- Observation: The repository already had an `OPENAI_API_KEY` in the process
  environment, but the user requested a new project key.
  Evidence: A new key named `podcast-learning-app Codex` was created through
  the OpenAI Platform connector and written to `podcast-transcription-pipeline/.env`.

- Observation: The real sample under `test_transcribe/` is a long file, not a
  short fixture.
  Evidence: `ffprobe` reported duration `12884.706168` seconds and size
  `269359217` bytes.

- Observation: One-minute chunking on the real sample produced 215 upload-sized
  MP3 chunks.
  Evidence: `podcast-transcriber chunk ... --chunk-seconds 60` wrote 215 rows
  to `test_transcribe/transcripts/chunks_manifest.jsonl`.

## Decision Log

- Decision: Downloading media is out of scope.
  Rationale: The first version should accept local files and avoid site-specific
  downloader maintenance.
  Date/Author: 2026-05-31 / initial plan.

- Decision: Use local files instead of a database.
  Rationale: JSONL, Markdown, and MP3 chunks are easy to inspect, edit,
  diff, rerun, and archive.
  Date/Author: 2026-05-31 / initial plan.

- Decision: Start with fixed-length chunks.
  Rationale: This is deterministic and simple. Add silence-aware chunking later
  only if cut-off speech becomes a real problem.
  Date/Author: 2026-05-31 / initial plan.

- Decision: Default to `gpt-4o-transcribe`, but keep the model configurable.
  Rationale: The user may want to compare supported transcription models.
  Date/Author: 2026-05-31 / initial plan.

- Decision: Use a `src/` package layout.
  Rationale: This is an installable CLI, not a loose script folder.
  Date/Author: 2026-06-01 / review.

- Decision: Require the source audio file explicitly.
  Rationale: The CLI should work for any episode directory and any local audio
  file. There should be no hidden search path or preferred source filename.
  Date/Author: 2026-06-01 / review.

- Decision: Require working and output directories explicitly.
  Rationale: Folder names should be caller choices, not tool conventions.
  Date/Author: 2026-06-01 / review.

- Decision: Generate size-checked MP3 chunks.
  Rationale: OpenAI file uploads are limited to 25 MB. MP3 is supported by the
  transcription API and avoids oversized uncompressed chunks.
  Date/Author: 2026-06-01 / review.

- Decision: Drop context-file creation from version one.
  Rationale: The first pipeline only needs source audio, chunks, and transcript
  artifacts. Prompt files remain explicit inputs through `--prompt-file`.
  Date/Author: 2026-06-01 / review.

- Decision: Load a local `.env` from the current working directory or installed
  project root before OpenAI calls.
  Rationale: This keeps CLI usage simple while still making `OPENAI_API_KEY`
  the runtime contract.
  Date/Author: 2026-06-01 / implementation.

- Decision: For the real sample smoke test, transcribe only the first
  60-second chunk.
  Rationale: The source file is over 3.5 hours long; a single-chunk API call
  validates the integration without incurring a full-episode transcription.
  Date/Author: 2026-06-01 / implementation.

## Review and Critique

The core design is sound: a local, file-oriented CLI is easy to inspect and easy
to rerun. The original plan was too specific to one path, one episode name, and
one source filename; this revision replaces those with explicit parameters and
required directory arguments.

Main design risks:

- Resuming by `chunk_id` alone can reuse stale transcripts after the source file
  or request settings change. Store source metadata, chunk settings, prompt
  hash, response format, and diarization settings in raw ASR rows, and only skip
  rows that still match.
- Fixed chunks can split speech. Accept this for version one; consider silence
  detection or overlap later.
- OpenAI response shapes differ by model. Keep all SDK details inside
  `openai_client.py` and normalize responses before the CLI or merge code sees
  them.
- Partial writes can corrupt output. Append a row only after a chunk succeeds;
  use a temp file plus atomic replace when rewriting with `--force`.
- Oversized chunks fail at upload time. Validate each generated chunk is under
  the OpenAI upload limit before transcription.
- Use a project-level `.venv`; do not depend on globally installed packages.

## OpenAI Docs Check

Checked with the OpenAI docs skill:

- `https://developers.openai.com/api/docs/guides/speech-to-text#transcriptions`
- `https://developers.openai.com/api/docs/guides/speech-to-text#speaker-diarization`
- `/audio/transcriptions` OpenAPI spec

Plan rules from current docs:

- File uploads are limited to 25 MB. Generated chunks must stay below that
  limit before upload.
- Use MP3 chunks for version one because MP3 is listed as a supported input
  format in both the guide and API reference.
- Use JSON output for `gpt-4o-transcribe` and `gpt-4o-mini-transcribe`.
- Request `diarized_json` for `gpt-4o-transcribe-diarize` if speaker labels are
  needed.
- Do not send prompts to `gpt-4o-transcribe-diarize`; warn and omit the prompt.
- Use `chunking_strategy="auto"` with `gpt-4o-transcribe-diarize` when the input
  chunk is longer than 30 seconds.
- Add optional `--language LANGUAGE`. Prefer ISO-639-1 where available; omit it
  when unknown. GPT-4o transcription models support some ISO 639-1 and 639-3
  codes.

## Outcomes & Retrospective

Completed on 2026-06-01.

Implemented an installable Python 3.11 CLI package under `src/podcast_transcriber`
with commands for `init-episode`, `chunk`, `transcribe`, and `merge`. The package
uses `ffmpeg`/`ffprobe` for fixed-length MP3 chunking and the official OpenAI
Python SDK for transcription.

Created:

    pyproject.toml
    README.md
    .env.example
    src/podcast_transcriber/
    tests/

Verification completed:

    PYTHONPATH=src python3 -m pytest tests
    PYTHONPATH=src python3 -m podcast_transcriber.cli --help
    python3 -m venv .venv
    .venv/bin/python -m pip install -e .
    .venv/bin/podcast-transcriber --help

Synthetic chunking smoke test passed with a five-second generated sine-wave file
and wrote three chunks plus `chunks_manifest.jsonl`.

Real sample smoke test used:

    EPISODE_DIR=test_transcribe
    SOURCE_DIR=test_transcribe
    CHUNKS_DIR=test_transcribe/chunks
    TRANSCRIPT_DIR=test_transcribe/transcripts

The real sample was chunked with `--chunk-seconds 60`, producing 215 manifest
rows. `transcribe --limit 1 --force` called OpenAI successfully for
`chunk_000001`, wrote one `raw_asr.jsonl` row, and `merge` wrote `raw_asr.md`.
The merge command warned about 214 missing chunks, which is expected because
only one chunk was transcribed for the smoke test.

Timestamp preservation is manifest-driven: each raw ASR row carries `start_ms`
and `end_ms` from its chunk, and Markdown sections render those values as
`HH:MM:SS-HH:MM:SS`.

Next improvements should be silence-aware chunking or small overlaps, richer
integration tests with a committed short speech fixture, and optional full-file
transcription orchestration once cost and runtime expectations are explicit.

## Directory Inputs

An episode is any writable directory. The tool does not assume conventional
child folders. The caller must pass these paths:

    EPISODE_DIR
    SOURCE_DIR
    CHUNKS_DIR
    TRANSCRIPT_DIR
    SOURCE_AUDIO

`init-episode` creates the specified directories if missing. `SOURCE_AUDIO` must
be under `SOURCE_DIR`. For the first version, require `SOURCE_DIR`,
`CHUNKS_DIR`, and `TRANSCRIPT_DIR` to be inside `EPISODE_DIR` so artifacts stay
relocatable. Do not persist absolute paths in manifest or transcript output.

Project files:

    PROJECT_ROOT/
      .venv/
      pyproject.toml
      README.md
      .env.example
      src/podcast_transcriber/
        __init__.py
        cli.py
        audio.py
        manifest.py
        openai_client.py
        merge.py

## Implementation Plan

Create a package under `src/podcast_transcriber` with an `argparse` CLI named
`podcast-transcriber`. Use Python 3.11 or newer.

Create `pyproject.toml` with:

    [project.scripts]
    podcast-transcriber = "podcast_transcriber.cli:main"

Declare the OpenAI Python SDK as a project dependency.

Set up development from the repository root:

    python -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install -e .

Update `.gitignore` for `.venv/`, `.env`, generated chunks, and raw transcript
outputs unless the project intentionally commits sample artifacts.

### CLI

Implement:

    podcast-transcriber init-episode EPISODE_DIR --source-dir SOURCE_DIR --chunks-dir CHUNKS_DIR --transcript-dir TRANSCRIPT_DIR
    podcast-transcriber chunk EPISODE_DIR --source-dir SOURCE_DIR --source-file SOURCE_AUDIO --chunks-dir CHUNKS_DIR --transcript-dir TRANSCRIPT_DIR [--chunk-seconds N] [--force]
    podcast-transcriber transcribe EPISODE_DIR --transcript-dir TRANSCRIPT_DIR [--model MODEL] [--prompt-file PATH] [--language LANGUAGE] [--chunk-id CHUNK_ID] [--start-index N] [--end-index N] [--limit N] [--force]
    podcast-transcriber merge EPISODE_DIR --transcript-dir TRANSCRIPT_DIR

Directory arguments are required. `--source-file` is required and must point
inside `SOURCE_DIR`. The `chunk` command must validate that relationship. Do not
search for source files, chunks, or transcripts in conventional folder names.

`init-episode` creates missing folders but never overwrites existing files.

`chunk` writes MP3 files to the configured chunks directory and writes
`chunks_manifest.jsonl` to the configured transcript directory.

Generated chunks must use a stable ffmpeg target:

    -ac 1 -ar 16000 -codec:a libmp3lame -b:a 64k

Validate every chunk is below 25 MB before transcription. If any chunk is too
large, fail with a clear message asking the user to rerun `chunk` with a smaller
`--chunk-seconds` value.

`chunk`, `transcribe`, and `merge` are separate components joined by files, not
one all-at-once component. `chunk` can run once, then `transcribe` can be run
later against the manifest.

Each manifest line includes:

    {
      "chunk_id": "chunk_000001",
      "chunk_index": 1,
      "audio_path": "CHUNKS_DIR_RELATIVE_TO_EPISODE/chunk_000001.mp3",
      "start_ms": 0,
      "end_ms": 180000,
      "duration_ms": 180000,
      "source_path": "SOURCE_DIR_RELATIVE_TO_EPISODE/SOURCE_AUDIO_NAME",
      "source_name": "SOURCE_AUDIO_NAME",
      "source_size_bytes": 123456,
      "source_mtime_ns": 1234567890,
      "chunk_seconds": 180,
      "chunk_format": "mp3",
      "chunk_codec": "libmp3lame",
      "chunk_sample_rate_hz": 16000,
      "chunk_channels": 1,
      "chunk_bitrate": "64k",
      "chunk_size_bytes": 1440000
    }

Store paths relative to `EPISODE_DIR`.

`transcribe` reads the manifest, selects chunks, calls the OpenAI wrapper for
each selected chunk, and appends one JSON object per completed chunk to
`raw_asr.jsonl` in the configured transcript directory. It must support
single-chunk and subset runs for testing:

    podcast-transcriber transcribe EPISODE_DIR --transcript-dir TRANSCRIPT_DIR --chunk-id chunk_000001
    podcast-transcriber transcribe EPISODE_DIR --transcript-dir TRANSCRIPT_DIR --start-index 10 --end-index 20
    podcast-transcriber transcribe EPISODE_DIR --transcript-dir TRANSCRIPT_DIR --limit 1

Before each API call, `transcribe` must verify that the chunk file exists and is
below 25 MB.

Each raw ASR line includes:

    {
      "chunk_id": "chunk_000001",
      "chunk_index": 1,
      "start_ms": 0,
      "end_ms": 180000,
      "audio_path": "CHUNKS_DIR_RELATIVE_TO_EPISODE/chunk_000001.mp3",
      "source_path": "SOURCE_DIR_RELATIVE_TO_EPISODE/SOURCE_AUDIO_NAME",
      "source_name": "SOURCE_AUDIO_NAME",
      "source_size_bytes": 123456,
      "source_mtime_ns": 1234567890,
      "chunk_seconds": 180,
      "chunk_format": "mp3",
      "chunk_size_bytes": 1440000,
      "model": "gpt-4o-transcribe",
      "language": null,
      "prompt_sha256": null,
      "response_format": "json",
      "chunking_strategy": null,
      "text": "...",
      "segments": null,
      "raw_response": {}
    }

Skip existing rows only when `chunk_id`, source metadata, chunk settings, model,
language, `prompt_sha256`, `response_format`, and `chunking_strategy` match.
Hash prompt file contents, not the prompt file path. With `--force`, rewrite the
whole file through a temp file and atomic replace.

`merge` sorts raw ASR rows by `chunk_index`, warns about missing manifest chunks,
and writes timestamped Markdown:

    # Raw ASR Transcript

    Source: SOURCE_AUDIO_NAME
    Model: gpt-4o-transcribe
    Language: not set

    ## 00:00:00-00:03:00

    Transcript text...

If diarized segments are present, emit the returned speaker label verbatim:

    **SPEAKER_LABEL_FROM_RESPONSE:** Transcript text...

## Core Interfaces

`manifest.py`:

    @dataclass
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

    def write_manifest(chunks: list[Chunk], manifest_path: Path) -> None: ...
    def read_manifest(manifest_path: Path) -> list[Chunk]: ...

`audio.py`:

    def ensure_ffmpeg_available() -> None: ...
    def probe_duration_seconds(source_path: Path) -> float: ...
    def chunk_audio(
        episode_dir: Path,
        source_dir: Path,
        source_path: Path,
        chunks_dir: Path,
        chunk_seconds: int,
        force: bool = False,
    ) -> list[Chunk]: ...

    def validate_upload_size(audio_path: Path, max_bytes: int = 25_000_000) -> None: ...

`openai_client.py`:

    def transcribe_audio_file(
        audio_path: Path,
        model: str,
        prompt: str | None = None,
        language: str | None = None,
        duration_seconds: float | None = None,
    ) -> dict: ...

Rules for the wrapper:

- Read `OPENAI_API_KEY` from the environment.
- Use the official OpenAI Python SDK.
- Return a stable dict with `text`, `segments`, and `raw_response`.
- For `gpt-4o-transcribe` and `gpt-4o-mini-transcribe`, request JSON output and
  pass prompt and language when provided.
- For `gpt-4o-transcribe-diarize`, request `diarized_json`, preserve speaker
  segments, omit unsupported prompts with a warning, pass language when
  provided, and set `chunking_strategy="auto"` when needed. Preserve each
  returned segment's `speaker` value verbatim.

`merge.py`:

    def merge_raw_asr_to_markdown(episode_dir: Path, transcript_dir: Path) -> str: ...

## Validation

Check the CLI:

    podcast-transcriber --help

Expected result: it lists `init-episode`, `chunk`, `transcribe`, and `merge`.

Run a chunking smoke test:

    EPISODE_DIR="$(mktemp -d)"
    SOURCE_DIR="$EPISODE_DIR/input-audio"
    CHUNKS_DIR="$EPISODE_DIR/chunk-output"
    TRANSCRIPT_DIR="$EPISODE_DIR/asr-output"
    podcast-transcriber init-episode "$EPISODE_DIR" --source-dir "$SOURCE_DIR" --chunks-dir "$CHUNKS_DIR" --transcript-dir "$TRANSCRIPT_DIR"
    ffmpeg -f lavfi -i sine=frequency=1000:duration=5 -ar 16000 -ac 1 "$SOURCE_DIR/synthetic.wav"
    podcast-transcriber chunk "$EPISODE_DIR" --source-dir "$SOURCE_DIR" --source-file "$SOURCE_DIR/synthetic.wav" --chunks-dir "$CHUNKS_DIR" --transcript-dir "$TRANSCRIPT_DIR" --chunk-seconds 2
    test -s "$TRANSCRIPT_DIR/chunks_manifest.jsonl"

Expected result: all commands exit 0 and the manifest exists.

Run the API smoke test only when a short real speech sample and API key are
available:

    EPISODE_DIR=<episode-directory>
    SOURCE_DIR=<source-directory>
    SOURCE_AUDIO=<source-directory>/<short-speech-sample>
    CHUNKS_DIR=<chunks-directory>
    TRANSCRIPT_DIR=<transcript-directory>
    podcast-transcriber init-episode "$EPISODE_DIR" --source-dir "$SOURCE_DIR" --chunks-dir "$CHUNKS_DIR" --transcript-dir "$TRANSCRIPT_DIR"
    podcast-transcriber chunk "$EPISODE_DIR" --source-dir "$SOURCE_DIR" --source-file "$SOURCE_AUDIO" --chunks-dir "$CHUNKS_DIR" --transcript-dir "$TRANSCRIPT_DIR" --chunk-seconds 60
    podcast-transcriber transcribe "$EPISODE_DIR" --transcript-dir "$TRANSCRIPT_DIR" --model gpt-4o-transcribe --language LANGUAGE --limit 1
    podcast-transcriber transcribe "$EPISODE_DIR" --transcript-dir "$TRANSCRIPT_DIR" --model gpt-4o-transcribe --language LANGUAGE
    podcast-transcriber merge "$EPISODE_DIR" --transcript-dir "$TRANSCRIPT_DIR"
    test -s "$TRANSCRIPT_DIR/raw_asr.jsonl"
    test -s "$TRANSCRIPT_DIR/raw_asr.md"

Replace `LANGUAGE` with a supported language code, preferring ISO-639-1 where
available, or omit `--language` when unknown.

Acceptance criteria:

- Manifest has one line per chunk.
- Manifest paths are relative when they point inside `EPISODE_DIR`.
- Each generated chunk is MP3 and below 25 MB.
- Raw ASR has one line per transcribed chunk.
- A single selected chunk can be transcribed for testing without transcribing the
  full manifest.
- Raw ASR includes timestamp metadata, source metadata, model, language, text,
  prompt hash, response format, chunking strategy, and optional segments.
- Markdown is readable and timestamped.
- No command infers source, chunk, or transcript directories from conventional
  names.
- No command deletes source audio.

## Idempotence and Errors

`init-episode` is safe to rerun and does not overwrite user-edited files.

`chunk` is safe to rerun with the same source metadata and options. If generated
chunks already exist, skip them unless `--force` is passed. If source metadata
or chunk settings differ, fail clearly unless `--force` is passed.

`transcribe` resumes from the first missing matching chunk. If a network or API
error stops the run, rerunning the same command continues safely.

`merge` is safe to rerun and regenerates `raw_asr.md`.

If `ffmpeg` or `ffprobe` is missing:

    ffmpeg/ffprobe not found. Install ffmpeg and ensure both ffmpeg and ffprobe are available on PATH.

If the API key is missing:

    OPENAI_API_KEY is not set. Export it in your shell or load it from a local .env file.

## Future Work

Future transcript repair should be a separate plan. Possible later commands:

    podcast-transcriber repair EPISODE_DIR
    podcast-transcriber translate EPISODE_DIR
    podcast-transcriber extract-entities EPISODE_DIR

Keep this first implementation boring, local, and file-oriented.
