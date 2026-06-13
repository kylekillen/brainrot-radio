#!/bin/bash
# cleanup-scratch.sh — retention sweep for the brainrot-radio pipeline scratch.
#
# WHY THIS EXISTS: podcast.py downloads source episode MP3s into .tmp/podcasts/
# (Whisper last-resort path) and NEVER deletes them. Whisper transcripts are
# cached separately in .tmp/transcripts/, so once ingest has run the source MP3
# is dead weight. Left unchecked these accumulated to ~98GB (back to March) and
# filled the disk on 2026-06-13, nearly killing the daily episode.
#
# This sweep deletes AUDIO/VIDEO scratch in .tmp older than RETENTION_DAYS.
# It is deliberately conservative:
#   - Only media files (mp3/wav/m4a/flac/ogg/aac/opus/mp4/mov/webm) + the
#     .tmp/podcasts source dir are eligible. Text scratch (transcripts, articles,
#     topic-brief, prompts), the .tmp/used/ dedup ledger, and helper .py scripts
#     are NEVER touched.
#   - The mtime guard (RETENTION_DAYS, default 2) means an in-progress run's
#     freshly-downloaded files (mtime ~now) are never eligible — this is the
#     primary in-progress safety net, complementing the per-day lock that
#     generate-episode.sh holds while running.
#
# Safe to run standalone or from generate-episode.sh after ingest. Idempotent.

set -euo pipefail

BRAINROT_DIR="${BRAINROT_DIR:-/Users/kylekillen/brainrot-radio}"
TMP_DIR="$BRAINROT_DIR/.tmp"
LOGFILE="${LOGFILE:-$BRAINROT_DIR/logs/generate.log}"
RETENTION_DAYS="${SCRATCH_RETENTION_DAYS:-2}"

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [cleanup-scratch] $1"
    echo "$msg"
    # Best-effort append to the pipeline log; never fail the sweep on a log error.
    echo "$msg" >> "$LOGFILE" 2>/dev/null || true
}

if [ ! -d "$TMP_DIR" ]; then
    log "No .tmp dir at $TMP_DIR; nothing to sweep."
    exit 0
fi

# Media extensions considered re-derivable scratch.
MEDIA_EXPR=( -iname '*.mp3' -o -iname '*.wav' -o -iname '*.m4a' -o -iname '*.flac' \
             -o -iname '*.ogg' -o -iname '*.aac' -o -iname '*.opus' -o -iname '*.mp4' \
             -o -iname '*.mov' -o -iname '*.webm' )

# Report what (and how much) we're about to free, for the log.
before_bytes=$(find "$TMP_DIR" -type f \( "${MEDIA_EXPR[@]}" \) -mtime +"$RETENTION_DAYS" \
                 -print0 2>/dev/null | xargs -0 stat -f '%z' 2>/dev/null \
                 | awk '{s+=$1} END {print s+0}')
count=$(find "$TMP_DIR" -type f \( "${MEDIA_EXPR[@]}" \) -mtime +"$RETENTION_DAYS" 2>/dev/null | wc -l | tr -d ' ')

if [ "${count:-0}" -eq 0 ]; then
    log "No media scratch older than ${RETENTION_DAYS}d; nothing to free."
    exit 0
fi

human=$(awk -v b="${before_bytes:-0}" 'BEGIN{printf "%.1f", b/1024/1024}')
log "Deleting ${count} media scratch file(s) older than ${RETENTION_DAYS}d (~${human} MB)…"

# Delete eligible media files (handles .tmp/podcasts/*.mp3 and any stray test
# audio left in .tmp). -mtime +N guarantees in-progress downloads survive.
find "$TMP_DIR" -type f \( "${MEDIA_EXPR[@]}" \) -mtime +"$RETENTION_DAYS" -delete 2>/dev/null || true

# Prune now-empty directories under .tmp/podcasts (keep the dir itself).
find "$TMP_DIR/podcasts" -mindepth 1 -type d -empty -delete 2>/dev/null || true

log "Sweep complete; freed ~${human} MB."
