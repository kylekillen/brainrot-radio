# Killen Time

Personalized news show — two AI hosts discuss the top stories from a
profile-driven feed list. Multiple episodes per day. Companion to Kyle's Killen
Time Substack. **Cost per episode: $0.00** (script written in a Claude Code
session; TTS and mixing are free).

This file holds only the true globals — the things that apply to *every* session.
Task-specific detail lives in the AI layer below and is loaded on demand, so no
session carries context it doesn't need.

## The AI layer (load on demand — don't inline these here)

**Pipeline commands** (`.claude/commands/`) — one per step, the cold-start
playbook. Run them in order or invoke individually:
1. `/generate-brief` — ingest the ranked topic brief + research the top stories
2. `/run-beat-reporters` — parallel beat agents, one per beat
3. `/assemble-episode [date]` — editor orders segments, writes intro/outro
4. `/qc-episode [script]` — **MANDATORY** adversarial 3-skeptic + synthesizer QC
5. `/publish-episode [script]` — render → mix → publish

**Context docs** (`.claude/context/`) — read only what the task needs:
- `architecture.md` — the Beat Reporter Model + how the automated run differs
- `editorial-voice.md` — voice, length target, sourcing, connection discipline
- `beats/*.md` — per-beat editorial guidelines (one file per beat)
- `scoring.md` — the ingest scoring algorithm
- `dedup.md` — multi-episode dedup rules + how to save covered stories
- `publishing.md` — render/mix/publish + distribution + launchd schedule

## Critical operating rules (these apply every time)
- **Follow the pipeline order:** ingest → research → beats → assemble → QC →
  render/mix/publish. Skipping research is the most common quality regression.
- **Don't write from RSS summaries.** Pull the actual source article/transcript.
- **QC is mandatory.** Always run `/qc-episode` after writing and BEFORE
  rendering. Do NOT render until it returns `QC VERDICT: PASS`.
- **Dedup is the most critical quality issue.** Read the last 48h of scripts and
  all `scripts/.covered-*.json` before writing; skip anything already covered;
  save covered stories immediately after writing. Details: `context/dedup.md`.
- **`beats.json` is the source of truth** for which beats run.
- **Voice is a fixed Kokoro clone of Kyle — don't swap it.**

## Voices
- **BASIL** (Kokoro `bm_daniel`) — Anchor, confident, leads segments.
- **BROOKE** (Kokoro `af_heart`) — Commentator, analytical, adds perspective.

TTS engine: Kokoro (local MLX, `mlx-community/Kokoro-82M-bf16`). Fallback: Edge
TTS (`--engine edge`).

## Episode format conventions
- **Length:** ~14,000-18,000 words (≈60 min). Cover everything; at minimum hit
  every story's highlights.
- **Speaker tags:** `[BASIL]`, `[BROOKE]`, `[TRANSITION]` only. Alternate
  speakers — never two consecutive same-speaker blocks. Use `[TRANSITION]` (not
  `---`) between beats; `---` would be read aloud.
- **Show name:** "The Killen Time Update for [Day], [Month] [Date], [Year]." Get
  the day of week RIGHT:
  `python3 -c "from datetime import date; print(date.today().strftime('%A'))"`.
- **Episode file:** `scripts/killen-time-YYYY-MM-DD.txt` (add `-02` for a second
  daily episode).
- **Greeting** matches the production time of day (morning/afternoon/evening);
  never say "tonight" for a morning show.

## Files

| File | Purpose |
|------|---------|
| `generate-episode.sh` | Production entrypoint (launchd): ingest → build-pitch → 2-pass write → QC → render → mix → publish |
| `ingest.py` | RSS + YouTube + podcast + Twitch fetch, score, rank, dedup |
| `transcribe.py` | mlx-whisper transcription engine (podcast.py + twitch.py) |
| `substack.py` | Substack full-article pipeline → `.tmp/articles/` |
| `podcast.py` | Podcast RSS download + transcription |
| `twitch.py` | Twitch VOD download + transcription |
| `youtube.py` | YouTube transcript pipeline |
| `positions.py` | Kalshi position change tracker (Locksy, Foster) |
| `voice.py` | TTS rendering (2 voices), cleans stale segments |
| `mixer.py` | FFmpeg concat + loudness normalization |
| `artwork.py` | Per-episode artwork generation |
| `config.py` | Constants, paths, voice assignments, publishing config |
| `publish.py` | Upload MP3 to GitHub Releases, generate RSS, push to Pages |
| `cleanup-scratch.sh` | Prune old `.tmp` media scratch (disk-fill guard) |
| `feeds.json` | Feed list + podcast configs + Twitch channels |
| `beats.json` | Beat reporter definitions (source of truth for active beats) |
| `profile.json` | Interest graph from X follows + Spotify podcasts |
| `build-pitches/` | Durable Build-Pitch-of-the-Day records |
| `scripts/` | Archived scripts + `.covered-*.json` tracking |
| `output/` | Final MP3s |
| `.tmp/` | Cached transcripts, downloaded audio, build-pitch summary |

## Automated schedule
launchd runs `generate-episode.sh` daily. Three jobs run together —
`com.mojo.brainrot-radio` (generator), `com.mojo.brainrot-ingest` (ingest),
`com.mojo.brainrot-check` (health/recovery check). If you disable one for
testing, note which and re-enable it. The generator uses a 2-pass writer for
throughput (see `context/architecture.md`); its QC step delegates to
`/qc-episode` so QC logic stays shared with the interactive path.

## Known Issues
- Anthropic blog RSS returns 404; The Diff (Substack) 400; The Economist 403
  (paywall); The Free Press returns empty.
- Edge TTS voices are staccato (need SSML/longer segments) — Kokoro is primary.
- No intro/outro music yet (only silence pads).
- HiveLive (X Spaces) not yet capturable — monitoring X feed only.
- `youtube.py` truncates transcripts to 2000 chars and skips channels with no
  channel_id (why the Build-Pitch Reporter pulls full transcripts itself).
