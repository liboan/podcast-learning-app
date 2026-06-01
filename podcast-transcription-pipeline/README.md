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

- Add overlapping chunks and a reconciliation step that removes duplicate text
  while preserving timestamps.
- Keep raw ASR and cleaned transcripts side by side, with enough metadata to
  trace cleaned text back to the source audio.

## Knowledge-Building TODOs

- Track the source of outside material and model-derived facts.
- Define simple data shapes for entities, glossary terms, speakers, aliases,
  translations, and episode references.
- Plan for human correction of speaker names and important terms.
- Split knowledge building into clear stages instead of one large model pass.
