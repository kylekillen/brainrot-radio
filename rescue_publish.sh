#!/bin/bash
# rescue_publish.sh <YYYY-MM-DD> — ship a Killen Time episode the pipeline lost.
#
# WHY. The external/claude write engines have no top-up loop (only gemini does), so an
# undershoot ends the day at voice.py's 6,000-word floor. 09-25, 09-27 (x2) and 10-01
# were all lost this way. That is a day of Kyle's protected daily show.
#
# WHAT IT DOES, in order:
#   1. waits for any in-flight generate-episode.sh run to finish (the 05:15 recovery)
#   2. exits if the recovery itself shipped the episode — never double-publish
#   3. tops the script up with grounded new segments (topup_writer.py)
#   4. refuses to continue on a script under the floor, or one with a fleet-private leak
#   5. renders -> artwork -> mix -> publish, exactly as generate-episode.sh does
#   6. commits the covered-story ledger from the FINAL script
#
# It never touches MIN_WORD_COUNT or any guard. It is the rescue path, not the fix;
# the fix is task 6996baded6e84f19b687233d3e1cf495.
set -u
DATE="${1:?usage: rescue_publish.sh YYYY-MM-DD}"
cd /Users/kylekillen/brainrot-radio || exit 1
LOG="logs/rescue-${DATE}.log"
exec >>"$LOG" 2>&1
echo "=== rescue_publish ${DATE} started $(date -u +%FT%TZ) pid $$ ==="

SCRIPT="scripts/killen-time-${DATE}.txt"
MP3="output/killen-time-${DATE}.mp3"
TARGET=6400
MAX_WAIT_MIN=45

# ── 1. let the scheduled recovery run finish before touching anything ─────────────
waited=0
while pgrep -f "generate-episode.sh" >/dev/null 2>&1; do
  [ "$waited" -ge $((MAX_WAIT_MIN * 2)) ] && { echo "gave up waiting for the recovery run"; break; }
  sleep 30; waited=$((waited + 1))
  [ $((waited % 4)) -eq 0 ] && echo "…still waiting on generate-episode.sh (${waited}x30s)"
done
echo "waited ${waited}x30s for the recovery run to clear"

# ── 2. if the show already shipped, stop — do not double-publish ─────────────────
if [ -f "$MP3" ]; then
  echo "RESCUE NOT NEEDED: ${MP3} already exists ($(stat -f%z "$MP3") bytes) — exiting"
  exit 0
fi
[ -f "$SCRIPT" ] || { echo "RESCUE FAILED: no ${SCRIPT} to rescue"; exit 1; }
cp "$SCRIPT" "/tmp/rescue-base-${DATE}.txt"
echo "base script backed up to /tmp/rescue-base-${DATE}.txt ($(wc -w < "$SCRIPT") raw words)"

# ── 3. grounded top-up ───────────────────────────────────────────────────────────
./venv/bin/python topup_writer.py --script "$SCRIPT" --out "/tmp/rescue-topup-${DATE}.txt" \
    --target "$TARGET" --rounds 2
TOPUP_RC=$?
if [ "$TOPUP_RC" -ne 0 ] || [ ! -s "/tmp/rescue-topup-${DATE}.txt" ]; then
  echo "RESCUE FAILED: topup_writer.py rc=${TOPUP_RC} — script left untouched at ${SCRIPT}"
  exit 1
fi

# ── 4. gates: word floor (never lowered) and no fleet-private leakage on air ──────
cp "/tmp/rescue-topup-${DATE}.txt" "$SCRIPT"
WORDS=$(./venv/bin/python -c 'import sys, topup_writer as t; print(t.spoken_words(open(sys.argv[1]).read()))' "$SCRIPT")
FLOOR=$(./venv/bin/python -c 'import config; print(config.MIN_WORD_COUNT)')
echo "final script: ${WORDS} spoken words (floor ${FLOOR})"
if [ "$WORDS" -lt "$FLOOR" ]; then
  echo "RESCUE FAILED: ${WORDS} < ${FLOOR} — the floor stands, not shipping a stub"
  exit 1
fi
LEAKS=$(grep -aiEc 'observer-system|STATUS\.md|HANDOFF|INBOX|launchd|tickler|alarm-responder|\bfleet\b|\bdispatch\b|this script|word count|top-up' "$SCRIPT" || true)
if [ "${LEAKS}" -gt 0 ]; then
  echo "RESCUE FAILED: ${LEAKS} fleet-private term(s) in the script — refusing to air:"
  grep -ainE 'observer-system|STATUS\.md|HANDOFF|INBOX|launchd|tickler|alarm-responder|\bfleet\b|\bdispatch\b|this script|word count|top-up' "$SCRIPT" | head -10
  exit 1
fi
echo "leak scan clean"

# ── 5. render -> artwork -> mix -> publish (mirrors generate-episode.sh step 4) ─────
echo "rendering TTS…"
./venv/bin/python voice.py "$SCRIPT" || { echo "RESCUE FAILED: voice render"; exit 1; }
BASE=$(basename "$SCRIPT" .txt); BASE="${BASE#killen-time-}"
ART="assets/episode-artwork/artwork-${BASE}.jpg"
TITLE="Killen Time — $(date '+%B %-d, %Y')"
./venv/bin/python artwork.py --title "$TITLE" --topics "AI, Agents & Building, NFL, Entertainment, Economics" || echo "artwork failed (non-fatal)"
echo "mixing…"
MIX_ARGS=(--output "$MP3"); [ -f "$ART" ] && MIX_ARGS+=(--artwork "$ART")
./venv/bin/python mixer.py "${MIX_ARGS[@]}" || { echo "RESCUE FAILED: mix"; exit 1; }
echo "publishing…"
PUB_ARGS=("$MP3" --title "Killen Time — ${DATE}" --description "Today's Killen Time Update.")
[ -f "$ART" ] && PUB_ARGS+=(--artwork "$ART")
./venv/bin/python publish.py "${PUB_ARGS[@]}" || { echo "RESCUE FAILED: publish"; exit 1; }

# ── 6. covered-story ledger from the FINAL script ────────────────────────────────
./venv/bin/python covered_guard.py commit "$SCRIPT" --date "$DATE" || echo "covered_guard commit failed (non-fatal)"

echo "=== RESCUE COMPLETE $(date -u +%FT%TZ): ${MP3} $(stat -f%z "$MP3" 2>/dev/null) bytes, ${WORDS} words ==="
