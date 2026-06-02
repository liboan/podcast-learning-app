# Podcast Transcription Pipeline

This component turns local podcast audio into raw, timestamped transcript
files. It owns the audio-to-transcript step: prepare chunks, call the
transcription model, and merge the raw output.

It does not download media, clean transcripts, translate text, or build the
knowledge base. Pass every directory explicitly.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Set `OPENAI_API_KEY` and `OPENAI_ADMIN_KEY` in your shell, or copy this
directory's `.env.example` to `.env` in the main project root. Local `.env`
files are ignored by git.

For this local workspace, store shared secrets in the main project `.env`. The
CLI automatically loads only that main project root `.env`; nested pipeline
`.env` files are ignored. Do not print, copy, grep, or otherwise inspect key
values.

## Usage

Default zero-overlap run:

```bash
podcast-transcriber init-episode EPISODE_DIR \
  --source-dir SOURCE_DIR \
  --chunks-dir CHUNKS_DIR \
  --transcript-dir TRANSCRIPT_DIR

podcast-transcriber chunk EPISODE_DIR \
  --source-dir SOURCE_DIR \
  --source-file SOURCE_AUDIO \
  --chunks-dir CHUNKS_DIR \
  --chunk-seconds 180

podcast-transcriber transcribe EPISODE_DIR \
  --chunks-dir CHUNKS_DIR \
  --transcript-dir TRANSCRIPT_DIR \
  --profile-file transcription_profiles.example.yaml \
  --profile 4o-transcribe \
  --limit 1

podcast-transcriber merge EPISODE_DIR \
  --chunks-dir CHUNKS_DIR \
  --transcript-dir TRANSCRIPT_DIR
```

If you are only preparing reusable chunks, omit `--transcript-dir` from
`init-episode` and run `chunk` without any transcript directory.

Context-padded run with 20 seconds of source audio before and after each
primary chunk where the source boundaries allow it:

```bash
podcast-transcriber init-episode EPISODE_DIR \
  --source-dir SOURCE_DIR \
  --chunks-dir EPISODE_DIR/chunks_180s_ctx20 \
  --transcript-dir EPISODE_DIR/asr_gpt4o_180s_ctx20

podcast-transcriber chunk EPISODE_DIR \
  --source-dir SOURCE_DIR \
  --source-file SOURCE_AUDIO \
  --chunks-dir EPISODE_DIR/chunks_180s_ctx20 \
  --chunk-seconds 180 \
  --overlap-seconds 20

podcast-transcriber transcribe EPISODE_DIR \
  --chunks-dir EPISODE_DIR/chunks_180s_ctx20 \
  --transcript-dir EPISODE_DIR/asr_gpt4o_180s_ctx20 \
  --profile-file transcription_profiles.example.yaml \
  --profile 4o-transcribe

podcast-transcriber merge EPISODE_DIR \
  --chunks-dir EPISODE_DIR/chunks_180s_ctx20 \
  --transcript-dir EPISODE_DIR/asr_gpt4o_180s_ctx20
```

The chunking stage writes `chunking_manifest.jsonl` and
`chunking_metadata.json` in the chunks directory. The transcription stage writes
`transcription_raw_asr.jsonl` and `transcription_metadata.json` in the transcript
directory, and `merge` writes `transcription_raw_asr.md` there. The manifest and raw rows use schema
version 2. `start_ms` and `end_ms` describe the primary source interval assigned
to the chunk. `audio_start_ms` and `audio_end_ms` describe the larger padded
audio interval sent to the model.

Transcription settings come from YAML profiles. The checked-in
`transcription_profiles.example.yaml` includes `4o-transcribe` and
`4o-transcribe-diarize` profiles. The regular transcription profile includes
inline context in its `prompt` string. The diarization profile requests
`diarized_json` and enables `chunking_strategy: auto` only for uploaded chunks
longer than 30 seconds.

Chunks are encoded as mono 16 kHz MP3 at 64k and validated against OpenAI's
25 MB upload limit.

Reuse a chunk directory across multiple transcription output directories. For
example, keep `chunks_180s_ctx20` as the durable chunking output, then run sample
transcribes into disposable directories such as `asr_sample_gpt4o` before
running a full transcription into `asr_gpt4o_180s_ctx20`. `transcribe` creates
the transcript directory when it is missing.

Old generated chunks, manifests, and raw transcript rows are not migrated.
Discard or archive those generated directories and rerun `chunk`, `transcribe`,
and `merge` to produce schema version 2 artifacts.

Use `--force` on `chunk` or `transcribe` to replace generated artifacts for the
selected work. Source audio is never deleted.

## Knowledge Base Vision

The transcripts produced here are the first layer of a podcast language-learning
system. Later steps can use the raw transcript as source material for a content
base that understands an episode, its speakers, its terms, and its domain.

For example, a later process may:

- clean the transcript and turn chunk output into a final episode transcript
- extract bilingual mappings for entities, glossary terms, speakers, aliases,
  and recurring phrases
- use outside context, such as PF2e rules or lore, to recognize game mechanics,
  setting terms, and likely transliterations

The app can then answer context-aware questions about what is happening in an
episode, explain terms in the right setting, and translate with awareness of the
podcast and its subject matter.

## Future Improvements

- Add a later cleaning step that removes duplicate overlap text while preserving
  the raw evidence and timestamps.
- Keep cleaned transcripts side by side with raw ASR output, with enough
  metadata to trace cleaned text back to the source audio.

## Knowledge-Building TODOs

- Track the source of outside material and model-derived facts.
- Define simple data shapes for entities, glossary terms, speakers, aliases,
  translations, and episode references.
- Plan for human correction of speaker names and important terms.
- Split knowledge building into clear stages instead of one large model pass.
