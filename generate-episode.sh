#!/bin/bash
# Generate a Killen Time episode end-to-end.
# Called by launchd daily at 5:30 AM, or manually.
#
# v3: Two-pass script writing. Each pass produces ~8K words for different beats,
#     then they're combined into one 14-18K word episode. Prevents the short-script
#     problem where a single Claude -p call caps out at ~9K words.

set -e

BRAINROT_DIR="/Users/kylekillen/brainrot-radio"
LOGFILE="$BRAINROT_DIR/logs/generate.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
RUN_ID=$(date '+%Y%m%d-%H%M%S')
RESULT_LOG="$BRAINROT_DIR/logs/generate-$RUN_ID.log"
CLAUDE="/Users/kylekillen/.local/bin/claude"
TODAY=$(date '+%Y-%m-%d')

# Code Voice: mute phone read-aloud for this non-interactive pipeline so the
# 5:30 AM podcast generation never narrates its turns to Kyle's phone.
export CODE_VOICE_MUTE=1

cd "$BRAINROT_DIR"
source venv/bin/activate
mkdir -p logs .tmp

# Determine time-of-day greeting context for the episode script
HOUR=$(date '+%H')
if [ "$HOUR" -lt 12 ]; then
    TIME_OF_DAY="morning"
    GREETING_HINT="This is a morning episode (produced around $(date '+%-I:%M %p')). Use morning greetings like 'good morning'. Do NOT say 'tonight' or 'this evening'."
elif [ "$HOUR" -lt 17 ]; then
    TIME_OF_DAY="afternoon"
    GREETING_HINT="This is an afternoon episode (produced around $(date '+%-I:%M %p')). Use afternoon greetings. Do NOT say 'tonight' or 'this evening'."
else
    TIME_OF_DAY="evening"
    GREETING_HINT="This is an evening episode (produced around $(date '+%-I:%M %p')). Evening greetings like 'good evening' or 'tonight' are appropriate."
fi

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOGFILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$RESULT_LOG"
}

# Run claude with a timeout. Args: timeout_seconds prompt_file step_name
run_claude_step() {
    local timeout=$1
    local prompt_file=$2
    local step_name=$3

    log "Step [$step_name] starting (timeout=${timeout}s)..."

    $CLAUDE --dangerously-skip-permissions --model sonnet -p "$(cat "$prompt_file")" >> "$RESULT_LOG" 2>&1 &
    local pid=$!
    local elapsed=0

    while kill -0 $pid 2>/dev/null; do
        sleep 10
        elapsed=$((elapsed + 10))
        if [ $elapsed -ge $timeout ]; then
            kill -9 $pid 2>/dev/null
            log "Step [$step_name] TIMED OUT after ${timeout}s"
            return 1
        fi
    done

    wait $pid
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        log "Step [$step_name] FAILED with exit code $exit_code"
        return 1
    fi

    log "Step [$step_name] complete"
    return 0
}

log "Episode generation starting (run=$RUN_ID)..."

# ─── Guard: skip if today's episode already published ────────────────────────
if [ -f "$BRAINROT_DIR/output/killen-time-${TODAY}.mp3" ]; then
    log "Episode already published for $TODAY, skipping"
    exit 0
fi

# ─── Concurrency gate: don't let two runs double-publish ─────────────────────
# The primary 4 AM launchd job (com.mojo.brainrot-radio) plus its recovery
# checker (com.mojo.brainrot-check at 5:15/5:45 → check-episode.sh) can overlap:
# if the 4 AM run is still rendering/publishing when the checker fires, the
# MP3-existence guard above isn't enough on its own and both runs publish a
# second episode (ep-...-02). This lock makes the later run stand down while an
# earlier run for the same day is still alive, so recovery only does real work
# if the primary actually died. A dead/stale (>3h) lock holder is taken over so
# a crashed primary doesn't block recovery.
#
# NOTE (2026-06-09): a third trigger — a 5 AM Claude Desktop scheduled task
# ("podcast") — used to run this script a second time each morning and was the
# main duplicate source. That backup was REMOVED at Kyle's request; only the
# 4 AM job + 5:15/5:45 recovery checker remain. The lock is kept as a safety net.
LOCK="$BRAINROT_DIR/.tmp/generate-${TODAY}.lock"
if [ -f "$LOCK" ]; then
    LOCK_PID=$(cat "$LOCK" 2>/dev/null || true)
    if [ -n "$LOCK_PID" ] && kill -0 "$LOCK_PID" 2>/dev/null \
       && [ -z "$(find "$LOCK" -mmin +180 2>/dev/null)" ]; then
        log "Another generation for $TODAY is already running (pid $LOCK_PID); standing down"
        exit 0
    fi
    log "Stale lock for $TODAY (pid ${LOCK_PID:-none}); taking over"
fi
echo "$$" > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

# ─── Step 1: Ingest ──────────────────────────────────────────────────────────
log "Running ingest..."
python3 ingest.py --report -n 40 -o .tmp/topic-brief.txt >> "$RESULT_LOG" 2>&1

if [ ! -f ".tmp/topic-brief.txt" ]; then
    log "No topic brief generated, aborting"
    exit 1
fi
log "Ingest complete"

# ─── Build dedup context (shared by both passes) ─────────────────────────────
LATEST_SCRIPTS=$(find "$BRAINROT_DIR"/scripts -name "killen-time-*.txt" -type f | sort | tail -3)
DEDUP_CONTEXT=""
if [ -n "$LATEST_SCRIPTS" ]; then
    DEDUP_CONTEXT="
DEDUP — Previous episodes:
Read these recent episode scripts BEFORE writing. Do NOT repeat ANY stories, arguments, quotes, or talking points:
$LATEST_SCRIPTS

Also read ALL scripts/.covered-*.json files. The 'segments' dict lists SPECIFIC FACTS already stated on-air.
Any fact already in these summaries MUST NOT be restated, even from a different source.
If a topic was covered in ANY previous episode, SKIP IT unless there are genuinely new developments
(a price moved, a deal closed, someone resigned, new data was released — a new TAKE on the same facts is NOT new).
When in doubt, SKIP. A fresh story is always better than a retread."
fi

SCRIPT_FILE="scripts/killen-time-${TODAY}.txt"

# ─── Step 2a: Pass 1 — Intro + AI/Tech + Agents & Building ───────────────────
cat > "$BRAINROT_DIR/.tmp/step2a-pass1.txt" <<PROMPT_EOF
You are producing the FIRST HALF of a Killen Time episode. Your working directory is /Users/kylekillen/brainrot-radio.

Read CLAUDE.md for full editorial guidelines, voice format, and content direction.

TIME OF DAY: ${GREETING_HINT}

YOUR JOB: Write the INTRO and the first half of the episode covering AI/TECH and the featured AGENTS & BUILDING WITH AI beat. Write to: ${SCRIPT_FILE}

You are writing ONLY the first half. Another pass will write the second half (NBA, Entertainment, Economics/Culture, a brief prediction-markets quick-hit, and the outro). Do NOT write an outro or sign-off — end your section with a [TRANSITION] tag.

Steps:
1. Read .tmp/topic-brief.txt for today's ranked stories
2. Read up to 3 podcast transcripts from .tmp/transcripts/ — pick the ones most relevant to AI/tech and to how people build with / run AI agents.
3. Read Substack full articles in .tmp/articles/ — focus on AI/tech and agent-building/practitioner articles.
4. Read ALL scripts/.covered-*.json files for dedup.
5. Read recent episode scripts (see DEDUP CONTEXT below) for dedup.
6. Write to ${SCRIPT_FILE}:
   - Show intro: cold open with the biggest story, show name + date
   - AI & Technology segments (1-2 segments, ~2500-3500 words): Feature high-signal essays, technical breakthroughs, pieces getting discussion
   - **Agents & Building With AI segments (2-3 segments, ~3500-4500 words) — THIS IS THE FEATURED BEAT OF THE SHOW.** How people are actually running their agents: personalized harness structures, CLAUDE.md / context engineering, subagents and multi-agent orchestration, project organization, evals, MCP and tooling, and dev-loop optimization. Pull concrete, stealable practices from Claude Code releases, Latent Space, Simon Willison, One Useful Thing, AI and I, The Cognitive Revolution, No Priors, a16z, Dwarkesh, Karpathy. Frame every story through "what can WE learn for our own multi-agent setup" — Kyle is building a team of delegated AIs and wants to optimize that system. Be specific and practitioner-level; quote the actual techniques, not vibes.
   - End with a [TRANSITION] tag — do NOT write an outro
   - Use BASIL/BROOKE/TRANSITION format (speaker tags in square brackets)
   - Include specific quotes from podcast transcripts and Substack articles
   - Alternate speakers — never two consecutive same-speaker blocks
   - Target 7000-9000 words for this half

IMPORTANT: Do NOT save covered stories or archive sources yet. That happens after both passes are complete.

STOP after writing the script file. Do NOT render, mix, or publish.
${DEDUP_CONTEXT}

Begin by reading CLAUDE.md, then .tmp/topic-brief.txt, then the previous episode scripts.
PROMPT_EOF

if ! run_claude_step 1800 "$BRAINROT_DIR/.tmp/step2a-pass1.txt" "write-pass1"; then
    log "Pass 1 attempt 1 failed, retrying..."
    sleep 15
    if ! run_claude_step 1800 "$BRAINROT_DIR/.tmp/step2a-pass1.txt" "write-pass1-retry"; then
        log "Pass 1 retry also failed, aborting"
        exit 1
    fi
fi

# Verify pass 1 produced a script
if [ ! -f "$BRAINROT_DIR/$SCRIPT_FILE" ]; then
    log "Pass 1 did not produce $SCRIPT_FILE, aborting"
    exit 1
fi

PASS1_WORDS=$(wc -w < "$BRAINROT_DIR/$SCRIPT_FILE" | tr -d ' ')
log "Pass 1 complete: $PASS1_WORDS words in $SCRIPT_FILE"

# ─── Step 2b: Pass 2 — NBA + Entertainment + Economics/Culture + Outro ───────
cat > "$BRAINROT_DIR/.tmp/step2b-pass2.txt" <<PROMPT_EOF
You are producing the SECOND HALF of a Killen Time episode. Your working directory is /Users/kylekillen/brainrot-radio.

Read CLAUDE.md for full editorial guidelines, voice format, and content direction.

The first half of the episode has already been written to: ${SCRIPT_FILE}
READ IT FIRST so you know what topics and stories have already been covered in this episode.

YOUR JOB: APPEND the second half to the EXISTING script file. Cover NBA, Entertainment, Economics/Culture, an optional brief prediction-markets quick-hit, and write the outro. Do NOT rewrite or duplicate anything from the first half.

Steps:
1. Read ${SCRIPT_FILE} — this is the first half you are continuing from. Note which stories were already covered.
2. Read .tmp/topic-brief.txt for remaining stories not yet covered
3. Read podcast transcripts from .tmp/transcripts/ — focus on NBA, entertainment, and economics podcasts
4. Read Substack articles in .tmp/articles/ — focus on economics, culture, and entertainment articles
5. Read scripts/.covered-*.json files for dedup against previous episodes
6. APPEND to ${SCRIPT_FILE} (do NOT overwrite — add to the end of the existing file):
   - NBA & Sports segments (2-3 segments, ~2500-3500 words): Trades, transactions, storylines. Pull analyst quotes.
   - Entertainment & Film/TV segments (1-2 segments, ~2000-3000 words): Industry news, deals, box office. Engage at screenwriter/producer level.
   - Economics/Culture segment (1-2 segments, ~1500-2500 words): Best pieces from the rationalist/policy blogosphere
   - Prediction Markets quick-hit (OPTIONAL, ~300-600 words, ONE short exchange max): Prediction markets are now a DE-EMPHASIZED beat. Include this only if there is genuinely notable movement today — a big position change, a market resolving, a real edge worth flagging. If nothing rises to that bar, SKIP it entirely. Do not pad. No full multi-segment trading block.
   - Quick Hits: 2-3 shorter items that didn't warrant full segments
   - Outro: Brief recap of the most interesting thread, short sign-off. Keep it tight.
   - Use BASIL/BROOKE/TRANSITION format (speaker tags in square brackets)
   - Include specific quotes from podcast transcripts and Substack articles
   - Alternate speakers — never two consecutive same-speaker blocks
   - Target 7000-9000 words for this half

7. After appending, save ALL covered stories from BOTH halves:
   Use: from ingest import save_covered_stories; save_covered_stories(list_of_slugs, dict_of_summaries, podcast_guids=list_of_guids)
   Include ALL story slugs from both halves AND all podcast episode GUIDs referenced.
   The summaries dict MUST include the specific talking points, quotes, and arguments used for EVERY story.
8. Archive used sources:
   Use: from ingest import archive_used_sources; archive_used_sources(used_transcript_guids=list_of_guids, used_article_paths=list_of_paths)

CRITICAL: You must APPEND to the file, not overwrite it. The first half is already written. Use the Edit tool or append mode. If you accidentally overwrite the first half, the episode is ruined.

STOP after saving covered stories and archiving. Do NOT render, mix, or publish.
${DEDUP_CONTEXT}

Begin by reading the existing ${SCRIPT_FILE}, then .tmp/topic-brief.txt for remaining stories.
PROMPT_EOF

if ! run_claude_step 1800 "$BRAINROT_DIR/.tmp/step2b-pass2.txt" "write-pass2"; then
    log "Pass 2 attempt 1 failed, retrying..."
    sleep 15
    if ! run_claude_step 1800 "$BRAINROT_DIR/.tmp/step2b-pass2.txt" "write-pass2-retry"; then
        log "Pass 2 retry also failed, proceeding with pass 1 only"
    fi
fi

# Check combined word count
NEW_SCRIPT="$BRAINROT_DIR/$SCRIPT_FILE"
TOTAL_WORDS=$(wc -w < "$NEW_SCRIPT" | tr -d ' ')
log "Combined script: $TOTAL_WORDS words"

# ─── Step 3: QC Review ───────────────────────────────────────────────────────
cat > "$BRAINROT_DIR/.tmp/step3-qc.txt" <<PROMPT_EOF
You are a QC reviewer for a Killen Time episode. Your working directory is /Users/kylekillen/brainrot-radio.

Read CLAUDE.md for editorial guidelines.

Read the script at: $NEW_SCRIPT

This script was written in two passes (first half: AI/tech + prediction markets, second half: NBA + entertainment + economics). Check for:
- Awkward transitions between the two halves (especially around the [TRANSITION] where they join)
- Duplicated stories or talking points across the two halves
- Orphaned/duplicated content
- Segments out of logical order
- Repeated signoffs or intro phrases
- Segments that reference stories not introduced yet
- Incorrect day of week (verify with Python: from datetime import date; date.today().strftime('%A'))
- Missing topic coverage promised in the intro
- Stories presented as "breaking" that are >48h old
- Missing source quotes — each segment should cite at least one source
- Speaker tag errors (must be [BASIL], [BROOKE], or [TRANSITION])
- Two consecutive same-speaker blocks
- Any redundant [TRANSITION] tags where the halves join (clean up to one)

If issues are found, fix them directly in the script file. If the script is clean, just confirm it passes QC.
PROMPT_EOF

if ! run_claude_step 900 "$BRAINROT_DIR/.tmp/step3-qc.txt" "qc-review"; then
    log "QC review failed (non-fatal), proceeding to render"
fi

# ─── Step 4: Render + Artwork + Mix + Publish (direct, no Claude) ───────────
SCRIPT_BASENAME=$(basename "$NEW_SCRIPT" .txt)
ARTWORK_PATH="assets/episode-artwork/artwork-${SCRIPT_BASENAME#killen-time-}.jpg"
OUTPUT_MP3="output/${SCRIPT_BASENAME}.mp3"

log "Rendering TTS audio..."
if ! python3 voice.py "$NEW_SCRIPT" >> "$RESULT_LOG" 2>&1; then
    log "Voice render failed, aborting"
    exit 1
fi
log "TTS render complete"

log "Generating artwork..."
# Extract title and topics from script (simple heuristic — first line and first 5 segment topics)
TITLE="Killen Time — $(date '+%B %-d, %Y')"
python3 artwork.py --title "$TITLE" --topics "AI, Agents & Building, NBA, Entertainment, Economics" >> "$RESULT_LOG" 2>&1 || log "Artwork generation failed (non-fatal)"

log "Mixing audio..."
MIX_ARGS=(--output "$OUTPUT_MP3")
if [ -f "$ARTWORK_PATH" ]; then
    MIX_ARGS+=(--artwork "$ARTWORK_PATH")
fi
if ! python3 mixer.py "${MIX_ARGS[@]}" >> "$RESULT_LOG" 2>&1; then
    log "Mix failed, aborting"
    exit 1
fi
log "Mix complete"

log "Publishing..."
PUB_ARGS=("$OUTPUT_MP3" --title "Killen Time — ${TODAY}" --description "Today's Killen Time Update.")
if [ -f "$ARTWORK_PATH" ]; then
    PUB_ARGS+=(--artwork "$ARTWORK_PATH")
fi
if ! python3 publish.py "${PUB_ARGS[@]}" >> "$RESULT_LOG" 2>&1; then
    log "Publish failed"
    exit 1
fi
log "Publish complete"

# ─── Step 5: Archive sources (safety net) ────────────────────────────────────
log "Archiving used sources (safety net)..."
python3 -c "
from pathlib import Path
import shutil

tmp = Path('.tmp')
used = tmp / 'used'
used.mkdir(exist_ok=True)

moved = 0
for f in (tmp / 'articles').glob('*.txt'):
    shutil.move(str(f), str(used / f.name))
    moved += 1

for f in (tmp / 'transcripts').glob('*.txt'):
    shutil.move(str(f), str(used / f.name))
    moved += 1

print(f'Archived {moved} source files to .tmp/used/')
" >> "$RESULT_LOG" 2>&1

log "Episode generation complete (log: $RESULT_LOG)"
