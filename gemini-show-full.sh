#!/bin/bash
# ALL-GEMINI show — ZERO Claude. ingest (free Python+Whisper) → build-pitch (Gemini
# grounding) → write (Gemini per-segment) → render/publish (free). venv python for
# ALL steps so nothing hits the wrong interpreter.
set -e
cd ~/brainrot-radio
PY=~/brainrot-radio/venv/bin/python3
TODAY=$(date +%F)
RLOG="logs/gemini-allgemini-$TODAY.log"; mkdir -p logs
log(){ echo "[$(date +%T)] $1" | tee -a "$RLOG"; }

log "1/5 fresh ingest (free; Python + local Whisper, no Claude)…"
$PY ingest.py --report -n 40 -o .tmp/topic-brief.txt >>"$RLOG" 2>&1

log "2/5 build-pitch on GEMINI (Google Search grounding, no Claude)…"
$PY gemini_buildpitch.py >>"$RLOG" 2>&1 || log "build-pitch failed (non-fatal)"

log "3/5 write on GEMINI (per-segment, full length, no Claude)…"
$PY gemini_episode.py >>"$RLOG" 2>&1

SCRIPT="scripts/killen-time-gemini-$TODAY.txt"
log "4/5 render + mix (free)…"
$PY voice.py "$SCRIPT" >>"$RLOG" 2>&1
$PY mixer.py --output output/killen-time-allgemini.mp3 >>"$RLOG" 2>&1

log "5/5 publish…"
cp output/killen-time-allgemini.mp3 /tmp/killen-time-$TODAY.mp3
$PY publish.py /tmp/killen-time-$TODAY.mp3 \
  --title "Killen Time — All-Gemini Edition (zero Claude)" \
  --description "Whole show on Gemini, no Claude anywhere: fresh ingest (Python+Whisper), build-pitch via Gemini Google-Search grounding, written by Gemini Flash, rendered locally. Free/\$0 — fully decoupled from the Claude pool. A/B vs the Claude shows." \
  --artwork assets/artwork.jpg >>"$RLOG" 2>&1
rm -f /tmp/killen-time-$TODAY.mp3
log "PUBLISHED All-Gemini Edition."
