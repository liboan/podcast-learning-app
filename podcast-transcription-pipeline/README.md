# Podcast Transcription Pipeline

Local CLI for converting a podcast or long-form audio file into a raw,
timestamped transcript. The tool does not download media or infer folder names;
pass every directory explicitly.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Set `OPENAI_API_KEY` in your shell, or create a local `.env` file from
`.env.example`. Local `.env` files are ignored by git.

## Usage

```bash
podcast-transcriber init-episode EPISODE_DIR \
  --source-dir SOURCE_DIR \
  --chunks-dir CHUNKS_DIR \
  --transcript-dir TRANSCRIPT_DIR

podcast-transcriber chunk EPISODE_DIR \
  --source-dir SOURCE_DIR \
  --source-file SOURCE_AUDIO \
  --chunks-dir CHUNKS_DIR \
  --transcript-dir TRANSCRIPT_DIR \
  --chunk-seconds 180

podcast-transcriber transcribe EPISODE_DIR \
  --transcript-dir TRANSCRIPT_DIR \
  --model gpt-4o-transcribe \
  --language ja \
  --limit 1

podcast-transcriber merge EPISODE_DIR \
  --transcript-dir TRANSCRIPT_DIR
```

The pipeline writes `chunks_manifest.jsonl`, `raw_asr.jsonl`, and `raw_asr.md`
in the transcript directory. Chunks are encoded as mono 16 kHz MP3 at 64k and
validated against OpenAI's 25 MB upload limit.

Use `--force` on `chunk` or `transcribe` to replace generated artifacts for the
selected work. Source audio is never deleted.
