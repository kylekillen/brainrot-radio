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

    $CLAUDE --dangerously-skip-permissions -p "$(cat "$prompt_file")" >> "$RESULT_LOG" 2>&1 &
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

# ─── Step 2a: Pass 1 — Intro + AI/Tech + Prediction Markets ─────────────────
cat > "$BRAINROT_DIR/.tmp/step2a-pass1.txt" <<PROMPT_EOF
You are producing the FIRST HALF of a Killen Time episode. Your working directory is /Users/kylekillen/brainrot-radio.

Read CLAUDE.md for full editorial guidelines, voice format, and content direction.

TIME OF DAY: ${GREETING_HINT}

YOUR JOB: Write the INTRO and the first half of the episode covering AI/TECH and PREDICTION MARKETS beats. Write to: ${SCRIPT_FILE}

You are writing ONLY the first half. Another pass will write the second half (NBA, Entertainment, Economics/Culture, and the outro). Do NOT write an outro or sign-off — end your section with a [TRANSITION] tag.

Steps:
1. Read .tmp/topic-brief.txt for today's ranked stories
2. Read up to 3 podcast transcripts from .tmp/transcripts/ — pick the ones most relevant to AI/tech and prediction markets.
3. Read Substack full articles in .tmp/articles/ — focus on AI/tech and prediction market articles.
4. Read ALL scripts/.covered-*.json files for dedup.
5. Read recent episode scripts (see DEDUP CONTEXT below) for dedup.
6. Write to ${SCRIPT_FILE}:
   - Show intro: cold open with the biggest story, show name + date
   - AI & Technology segments (2-3 segments, ~3000-4000 words): Feature high-signal essays, technical breakthroughs, pieces getting discussion
   - Prediction Markets & Trading segments (2-3 segments, ~3000-4000 words): Positions, strategies, specific markets, edge. Quote from podcasts/streams.
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

if ! run_claude_step 2400 "$BRAINROT_DIR/.tmp/step2a-pass1.txt" "write-pass1"; then
    log "Pass 1 script writing failed, aborting"
    exit 1
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

YOUR JOB: APPEND the second half to the EXISTING script file. Cover NBA, Entertainment, Economics/Culture, and write the outro. Do NOT rewrite or duplicate anything from the first half.

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

if ! run_claude_step 2400 "$BRAINROT_DIR/.tmp/step2b-pass2.txt" "write-pass2"; then
    log "Pass 2 script writing failed, proceeding with pass 1 only"
    # Don't abort — pass 1 alone may be enough to render
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

# ─── Step 4: Render + Artwork + Mix + Publish ────────────────────────────────
SCRIPT_BASENAME=$(basename "$NEW_SCRIPT" .txt)
ARTWORK_PATH="assets/episode-artwork/artwork-${SCRIPT_BASENAME#killen-time-}.jpg"

cat > "$BRAINROT_DIR/.tmp/step4-render-publish.txt" <<PROMPT_EOF
You are completing a Killen Time episode. Your working directory is /Users/kylekillen/brainrot-radio.

The script is at: $NEW_SCRIPT

Execute these steps IN ORDER:
1. Render audio: python3 voice.py $NEW_SCRIPT
2. Generate artwork: python3 artwork.py --title 'EPISODE TITLE' --topics 'COMMA-SEPARATED-TOPICS'
   (Read the script to determine a good title and topic list)
3. Song of the Day: python3 song_of_the_day.py
   This is OPTIONAL — if ACE-Step is not running or it fails, skip it (not fatal).
   If it succeeds, capture the output path printed as "OUTPUT: /path/to/song.mp3"
4. Mix: python3 mixer.py --output output/${SCRIPT_BASENAME}.mp3 --artwork $ARTWORK_PATH
   (Add --song-of-the-day /path/to/sotd.mp3 only if step 3 succeeded)
5. Publish: python3 publish.py output/${SCRIPT_BASENAME}.mp3 --title 'Killen Time — ${TODAY}' --description 'Brief summary' --artwork $ARTWORK_PATH
   (Read the script to write a proper brief description)

If voice rendering fails, that is fatal — stop. If artwork or song-of-the-day fails, continue without them.
PROMPT_EOF

if ! run_claude_step 2700 "$BRAINROT_DIR/.tmp/step4-render-publish.txt" "render-publish"; then
    log "Render/publish failed"
    exit 1
fi

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
