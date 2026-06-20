#!/bin/bash
# Faithful end-to-end NEW Gemini show: fresh ingest (free) + fresh Claude build-pitch
# (the residual agentic step) + per-segment Gemini write (free, full-length) + render
# + publish. Honest split: ingest/write/render = free/Gemini; build-pitch research =
# Claude (agentic); QC skipped for this A/B sample.
set -e
cd ~/brainrot-radio
PY=~/brainrot-radio/venv/bin/python3
CLAUDE=~/.local/bin/claude
TODAY=$(date +%F)
RLOG="logs/gemini-show-$TODAY.log"; mkdir -p logs
log(){ echo "[$(date +%T)] $1" | tee -a "$RLOG"; }

log "1/5 fresh ingest (free)…"
$PY ingest.py --report -n 40 -o .tmp/topic-brief.txt >>"$RLOG" 2>&1

log "2/5 build-pitch reporter (Claude — the residual agentic step)…"
$CLAUDE --dangerously-skip-permissions --model sonnet -p "Working dir /Users/kylekillen/brainrot-radio. Read .claude/context/beats/claude-lab.md and the claude_lab beat in beats.json, then run the Build-Pitch Reporter for today: find the single highest-leverage VERIFIED technique for Kyle's fleet from recent claude_lab sources, and write build-pitches/$TODAY.md (durable record) AND .tmp/build-pitches.md (200-400 word summary for the episode writer; first line exactly NO_VERIFIED_PITCH if nothing clears the bar). STOP after writing both files." >>"$RLOG" 2>&1 || log "build-pitch failed (non-fatal; segment will be omitted)"

log "3/5 per-segment Gemini write (free, full length)…"
$PY gemini_episode.py >>"$RLOG" 2>&1

SCRIPT="scripts/killen-time-gemini-$TODAY.txt"
log "4/5 render + mix (free)…"
$PY voice.py "$SCRIPT" >>"$RLOG" 2>&1
$PY mixer.py --output output/killen-time-gemini-v2.mp3 >>"$RLOG" 2>&1

log "5/5 publish…"
cp output/killen-time-gemini-v2.mp3 /tmp/killen-time-$TODAY.mp3
$PY publish.py /tmp/killen-time-$TODAY.mp3 \
  --title "Killen Time — Gemini Edition v2 (fresh + build-pitch)" \
  --description "NEW show end-to-end: fresh ingest, fresh Claude-Lab build-pitch, written 100% by Gemini Flash. A/B vs Claude. Honest split: ingest+write+render free/Gemini; build-pitch research is the residual Claude-agentic step; QC skipped for this sample." \
  --artwork assets/artwork.jpg >>"$RLOG" 2>&1
rm -f /tmp/killen-time-$TODAY.mp3
log "PUBLISHED Gemini Edition v2."
