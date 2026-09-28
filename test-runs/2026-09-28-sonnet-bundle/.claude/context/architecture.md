# Architecture (v0.2 — Beat Reporter Model)

```
                    ┌─────────────────────┐
                    │   EDITOR (main)     │
                    │  assembles show     │
                    └─────────┬───────────┘
                              │
           ┌──────────┬───────┴────────┬──────────┐
           ▼          ▼                ▼          ▼
    ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
    │ AI/Tech    │ │ Agents &   │ │ NBA/Sports │ │ Entertain. │
    │ Beat Agent │ │ Building★  │ │ Beat Agent │ │ Beat Agent │
    └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
          │              │              │              │
    RSS + YouTube   Claude Code +  Podcast RSS    RSS + pods
    + blog fetches  builder pods   + RSS + trades  + Twitch
                    + newsletters
    (★ featured beat — prediction markets demoted to a quick-hit)
```

**Pre-step reporter (2026-06-11):** the **Claude Lab Build-Pitch Reporter** runs
after ingest and before the script passes. It scans Claude-technique YouTube
transcripts, verifies findings against other sources, and writes a verified
upgrade pitch to `build-pitches/YYYY-MM-DD.md` (+ `.tmp/build-pitches.md`) that
the front half folds in as the "Build-Pitch of the Day."

## Two implementations of the same pipeline
- **Interactive / cold-start playbook:** `.claude/commands/` — one command per
  pipeline step (generate-brief → run-beat-reporters → assemble-episode →
  qc-episode → publish-episode). Use these when running the pipeline by hand or
  picking it up cold. The beat-reporter fan-out lives here.
- **Automated daily run:** `generate-episode.sh` (launchd). For throughput it
  uses a **2-pass** script-writing implementation (front half: AI/Tech + Agents
  & Building + Build-Pitch; back half: Sports + Entertainment + Economics +
  optional prediction-markets quick-hit + outro) rather than 4 separate beat
  agents — a single `claude -p` call caps at ~9K words, so two passes hit the
  14-18K target. Its QC step delegates to `.claude/commands/qc-episode.md` (the
  adversarial 3-skeptic QC), so QC logic is shared between both paths.

## Dependencies
- Python 3.13 (venv at `./venv/`)
- `mlx-audio` — Kokoro TTS (local MLX, Apple Silicon, primary)
- `edge-tts` — Microsoft Edge TTS (free, async, fallback)
- `mlx-whisper` — Apple Silicon Whisper transcription
- `yt-dlp` — YouTube transcripts + Twitch VOD downloads
- `ffmpeg` — truncation, concat, normalization (`/opt/homebrew/bin/ffmpeg`)

## Future (v0.3+)
- Per-episode generated artwork via local image model
- Google Trends integration for general awareness
- SSML markup for more natural voice flow
- Intro/outro music stingers
- NotebookLM pipeline (PDF → upload → video)
- HiveLive X Spaces full transcript capture
- Browser-based Kalshi position scraping for Locksy/Foster
