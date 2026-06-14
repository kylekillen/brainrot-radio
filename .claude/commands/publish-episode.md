---
description: Steps 6-8 — render TTS, mix audio, and publish the episode
argument-hint: "[path/to/script.txt]"
---

# Render, mix, and publish

Final pipeline steps (6-8). Working directory: `/Users/kylekillen/brainrot-radio`.
Only run this **after `/qc-episode` returns `QC VERDICT: PASS`.**

**Script:** `$1` (default: newest `scripts/killen-time-*.txt`).
Full details: `.claude/context/publishing.md`.

```bash
source venv/bin/activate
SCRIPT="$1"                                   # e.g. scripts/killen-time-2026-06-13.txt
BASE=$(basename "$SCRIPT" .txt)               # killen-time-2026-06-13
OUT="output/$BASE.mp3"

# 6. Render TTS (Kokoro primary; --engine edge fallback)
python3 voice.py "$SCRIPT"

# 7. Mix (FFmpeg concat + loudness normalization; --artwork optional)
python3 mixer.py --output "$OUT"

# 8. Publish (upload MP3 to GitHub Releases, regen RSS, push to Pages)
python3 publish.py "$OUT" \
  --title "Killen Time — ${BASE#killen-time-}" \
  --description "Today's Killen Time Update."
```

If covered-stories were not already saved during assembly, save them now BEFORE
this step (see `.claude/context/dedup.md`) — the next episode must not re-cover
today's stories.

Confirm the MP3 exists in `output/` and the publish step reported success.
