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

# Writer engine: claude (default) | gemini. Sourced from a config file so the daily
# job AND the recovery checker both honor it. Switch back to Claude any time with:
#   echo claude > ~/.observer/data/podcast-engine     (or: rm that file)
PODCAST_ENGINE="${PODCAST_ENGINE:-$(cat "$HOME/.observer/data/podcast-engine" 2>/dev/null || echo claude)}"
export PODCAST_ENGINE

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

# OFFLOAD FALLBACK writer — used ONLY when a Claude write pass has already failed
# (its own retry included), or when PODCAST_FORCE_OPENROUTER=1 forces it for a
# manual quality test. The daily default path is 100% Claude (flat-rate Max pool,
# $0 marginal). The offload provider is whatever ~/.config/personal-os/offload.env
# configures — currently FREE Gemini Flash (so the fallback is also $0; only a
# pay-per-token provider would cost). or_writer.py gathers the same inputs the
# Claude pass would have read and writes/appends the script identically, so QC +
# dedup downstream are unchanged. Args: pass_no (1|2)
run_kimi_pass() {
    local pass_no=$1
    log "⚠️  FALLBACK: routing write-pass $pass_no to the configured offload provider (offload.env — currently free Gemini Flash) because the Claude pass failed (or was force-overridden). Normal days run on Claude only."
    if python3 or_writer.py --pass "$pass_no" --script "$SCRIPT_FILE" --greeting "$GREETING_HINT" >> "$RESULT_LOG" 2>&1; then
        log "FALLBACK pass $pass_no via OpenRouter (Kimi) complete"
        return 0
    fi
    log "FALLBACK pass $pass_no via OpenRouter (Kimi) FAILED"
    return 1
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

# ─── Budget guard: preserve the trading pool ─────────────────────────────────
# If the shared Claude pool is under cap-pressure (a recent money-monitor cap-hit),
# stand THIS non-critical job down so the trading sentinel keeps its headroom.
# Reversible/override: BUDGET_GUARD_OFF=1. Durable fix = per-workload key tiering
# (agent-os/proposal-tiered-failover-2026-06-18.md).
if [ -x "$BRAINROT_DIR/budget-guard.sh" ] && [ -z "${BUDGET_GUARD_OFF:-}" ]; then
    if ! "$BRAINROT_DIR/budget-guard.sh" check 2>>"$RESULT_LOG"; then
        log "BUDGET GUARD: shared pool under cap-pressure — standing down today's episode to preserve trading functions. (override with BUDGET_GUARD_OFF=1)"
        exit 0
    fi
fi

# ─── Step 1: Ingest ──────────────────────────────────────────────────────────
log "Running ingest..."
python3 ingest.py --report -n 40 -o .tmp/topic-brief.txt >> "$RESULT_LOG" 2>&1

if [ ! -f ".tmp/topic-brief.txt" ]; then
    log "No topic brief generated, aborting"
    exit 1
fi
log "Ingest complete"

# ─── Step 1.1: Scratch retention sweep ───────────────────────────────────────
# Ingest just downloaded source MP3s into .tmp/podcasts/ (Whisper path) whose
# transcripts are now cached in .tmp/transcripts/. Delete media scratch older
# than the retention window so .tmp can't grow unbounded (it hit ~98GB and
# filled the disk on 2026-06-13). mtime guard keeps today's files; non-fatal.
log "Pruning old .tmp media scratch..."
bash "$BRAINROT_DIR/cleanup-scratch.sh" >> "$RESULT_LOG" 2>&1 || log "Scratch sweep failed (non-fatal); continuing"

# ─── Step 1.5: Build-Pitch Reporter (Claude Lab) ─────────────────────────────
# A dedicated reporter that scans recent YouTube transcripts from Claude-technique
# channels, RESEARCHES + VERIFIES anything interesting against other sources, and
# writes verified upgrade pitches Kyle can greenlight off the show. Non-fatal: if
# it fails, the episode still generates and the AI block just omits the segment.
mkdir -p build-pitches
PITCH_FILE="build-pitches/${TODAY}.md"
PITCH_SUMMARY=".tmp/build-pitches.md"
rm -f "$PITCH_SUMMARY"
cat > "$BRAINROT_DIR/.tmp/step1b-build-pitch.txt" <<PROMPT_EOF
You are the CLAUDE LAB Build-Pitch Reporter for the Killen Time podcast. Working directory: /Users/kylekillen/brainrot-radio.

Read .claude/context/beats/claude-lab.md and the "claude_lab" beat in beats.json for your full brief.

MISSION: Your lens is Kyle's WHOLE SYSTEM, not this podcast. Answer, from a whole-fleet vantage: what is the single highest-leverage thing Kyle could build or adopt right now to improve his entire Agent OS / fleet? Find it in the latest techniques on (a) Claude technique/prompting/harness design, (b) running agents and multi-agent orchestration, (c) Claude/Claude Code system upgrades, and (d) optimization (dev-loop, evals, cost/latency, memory & state) — VERIFY before reporting, and turn the survivors into concrete BUILD PITCHES. The podcast is the delivery surface; build-pitches/ is also a feed the weekly Fleet Optimizer survey reads for its slate.

LENS — need-first, NOT technique-first. Do this BEFORE scanning:
1. Read the fleet's current biggest needs so your hunt is aimed at real pain: ~/fleet-optimizer/STATUS.md (the Fleet Optimizer's current slate + open problems), ~/.observer/wiki/agent-os/credit-resilience-plan.md (credit/SPOF/cost pain), ~/.observer/wiki/agent-os/ (system design, fragility, the multi-agent unlock), and recent breakage/alarm patterns.
2. Rank every candidate by LEVERAGE toward Kyle's priorities, in order: (1) income—screenwriting, served by protecting his attention / removing friction; (2) income—AI businesses, the unlock being multi-agent collaboration that carries work forward without his constant attention; (3) resilience of the trading systems. Whole-fleet/cross-cutting beats single-project polish. Score = leverage × evidence ÷ cost.
3. ADAPTIVE search: derive your keyword queries from the needs you just read, NOT a fixed list — what you hunt for changes as the system changes. Name the need each pitch serves.
Do NOT treat the podcast as an optimization target (it's the delivery surface). You MAY surface a money/trading-practice improvement, but tag it "money — discuss first" (not auto-buildable).

SOURCES — recent (last ~7 days) YouTube from the claude_lab channels in feeds.json (IndyDevDan, Cole Medin, AI Jason, GosuCoder, Matthew Berman, Anthropic). To get the candidate list with snippets cheaply, run:
    python3 youtube.py --hours 168 --json
and focus on items whose "_topic" is "claude_lab". You may also use the yt-search skill and targeted searches ("Claude Code subagents", "agent harness", "Claude Code optimization", "running AI agents", "Claude context engineering") to find more. For any candidate worth investigating, pull the FULL transcript (yt-search skill or: ./venv/bin/yt-dlp --write-auto-sub --sub-lang en --skip-download --sub-format vtt -o '.tmp/youtube/%(id)s' 'VIDEO_URL') — the youtube.py snippet is truncated to 2000 chars and is only a triage signal.

DISCIPLINE — this is the whole point, do NOT skip it:
1. For each interesting technique, RESEARCH it. Use WebSearch / WebFetch (and the other claude_lab sources: Claude Code releases, Simon Willison, Latent Space) to check whether other people are doing the same or similar thing, and whether there's real evidence it works — not just a slick demo or hype.
2. VERIFY it's real, interesting, and meaningful. Discard anything vague, unverifiable, contradicted by other sources, or that Kyle already does (his stack: observer-system, the COS, the dispatcher / PR-reviewer loop, this podcast pipeline, a multi-agent delegation setup — read ~/.observer/wiki and ~/observer-system/CLAUDE.md if you need to check what's already in place).
3. Keep only the 1-3 strongest survivors. Quality over quantity. A single well-verified pitch beats three thin ones. If NOTHING survives, that's a valid outcome — say so.

OUTPUT — write BOTH files:
A) ${PITCH_FILE} — the durable record. For each verified pitch include: **Technique** (1-2 sentences), **Who's doing it** (specific video titles + URLs + corroborating source links), **Evidence it's real** (what you cross-checked), **Need it serves** (which fleet pain + which of Kyle's priorities 1–3 it moves), **Whole-fleet leverage** (one line the Fleet Optimizer can rank on), **Build sketch** (concrete first steps an agent could take), **Status: pitched** (or **money — discuss first** for trading/money changes). Start the file with a one-line date header. If nothing survived, write a short "No verified pitch today — here's what I looked at and why it didn't clear the bar" note instead.
B) ${PITCH_SUMMARY} — a tight summary (200-400 words) the episode writer will fold into the show. Lead with the single best pitch: what it is, who's doing it, why it's verified/real, and the one-line "here's how it'd upgrade our setup." End with: "Logged in ${PITCH_FILE} for Kyle to greenlight." If there's no verified pitch, write exactly: "NO_VERIFIED_PITCH" on the first line, then a one-sentence reason.

NEVER fabricate a pitch or overstate evidence. Honesty about a thin day is the correct behavior. STOP after writing both files.
PROMPT_EOF

if [ "${PODCAST_ENGINE:-claude}" = "gemini" ]; then
    log "Build-Pitch Reporter on GEMINI (grounded claude_lab transcript combing)..."
    python3 gemini_buildpitch.py >> "$RESULT_LOG" 2>&1 \
        || log "Gemini build-pitch failed (non-fatal); AI block will omit the segment"
elif ! run_claude_step 1500 "$BRAINROT_DIR/.tmp/step1b-build-pitch.txt" "build-pitch-reporter"; then
    log "Build-Pitch Reporter failed (non-fatal); AI block will omit the build-pitch segment"
fi
if [ -f "$BRAINROT_DIR/$PITCH_SUMMARY" ]; then
    log "Build-Pitch Reporter wrote summary ($(wc -w < "$BRAINROT_DIR/$PITCH_SUMMARY" | tr -d ' ') words)"
fi

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

# ─── Step 2: Write the episode (engine-dependent) ────────────────────────────
if [ "${PODCAST_ENGINE:-claude}" = "gemini" ]; then
    # All-Gemini write: per-segment, faithful beats, dedup + covered-story saving.
    log "Writing episode on GEMINI (per-segment, faithful beats + covered-save)..."
    if ! GEMINI_OUT="$BRAINROT_DIR/$SCRIPT_FILE" python3 gemini_episode.py >> "$RESULT_LOG" 2>&1; then
        log "Gemini write failed, aborting"; exit 1
    fi
else
# ─── Step 2a: Pass 1 — Intro + AI/Tech + Agents & Building ───────────────────
cat > "$BRAINROT_DIR/.tmp/step2a-pass1.txt" <<PROMPT_EOF
You are producing the FIRST HALF of a Killen Time episode. Your working directory is /Users/kylekillen/brainrot-radio.

Read CLAUDE.md for full editorial guidelines, voice format, and content direction.

TIME OF DAY: ${GREETING_HINT}

YOUR JOB: Write the INTRO and the first half of the episode covering AI/TECH and the featured AGENTS & BUILDING WITH AI beat. Write to: ${SCRIPT_FILE}

You are writing ONLY the first half. Another pass will write the second half (NBA, Entertainment, Economics/Culture, a brief prediction-markets quick-hit, and the outro). Do NOT write an outro or sign-off — end your section with a [TRANSITION] tag.

Steps:
1. Read .tmp/topic-brief.txt for today's ranked stories
2. Read up to 3 podcast transcripts from .tmp/transcripts/ — PRIORITIZE the two anchor AI shows when fresh episodes exist: the AI Daily Brief (Nathaniel Whittemore) and Moonshots (Peter Diamandis). After those, pick what's most relevant to how people build with / run AI agents.
3. Read Substack full articles in .tmp/articles/ — focus on AI/tech and agent-building/practitioner articles.
4. Read .tmp/build-pitches.md if it exists — this is the verified output of the Claude Lab Build-Pitch Reporter (see step 6 for how to use it).
5. Read ALL scripts/.covered-*.json files for dedup.
6. Read recent episode scripts (see DEDUP CONTEXT below) for dedup.
7. Write to ${SCRIPT_FILE}:
   - Show intro: cold open with the biggest story, show name + date
   - **AI & Technology segments (1-2 segments, ~2500-3500 words) — FOCUS ON HIGH-SIGNAL AI.** Anchor this block on the AI Daily Brief and Moonshots: lead with their framing and actual arguments/quotes whenever a fresh episode exists, and give each real airtime (not a passing mention). Use the RSS news headlines (Techmeme, TechCrunch, Ars) as context AROUND that podcast discussion, not as the spine. Then feature high-signal essays and technical breakthroughs getting discussion in circles Kyle follows. Skip generic news-summary filler.
   - **Agents & Building With AI segments (2-3 segments, ~3500-4500 words) — THIS IS THE FEATURED BEAT OF THE SHOW.** How people are actually running their agents: personalized harness structures, CLAUDE.md / context engineering, subagents and multi-agent orchestration, project organization, evals, MCP and tooling, and dev-loop optimization. Pull concrete, stealable practices from Claude Code releases, Latent Space, Simon Willison, One Useful Thing, AI and I, The Cognitive Revolution, No Priors, a16z, Dwarkesh, Karpathy. Frame every story through "what can WE learn for our own multi-agent setup" — Kyle is building a team of delegated AIs and wants to optimize that system. Be specific and practitioner-level; quote the actual techniques, not vibes.
   - **BUILD PITCH OF THE DAY:** If .tmp/build-pitches.md exists AND its first line is not "NO_VERIFIED_PITCH", give the top verified pitch its own dedicated exchange inside the Agents & Building block (~400-700 words): what the technique is, who's doing it (name the source), the evidence it's real, and exactly how it would upgrade Kyle's own setup. Then have a host say plainly that it's logged in the build-pitches folder so Kyle can point an agent at it and greenlight the build if he likes it. If the file is missing or says NO_VERIFIED_PITCH, skip this — do NOT invent a pitch.
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

if [ -n "${PODCAST_FORCE_OPENROUTER:-}" ]; then
    # Manual escape hatch / quality test ONLY. Never set in the launchd default.
    log "PODCAST_FORCE_OPENROUTER=1 — skipping Claude for pass 1 and writing via OpenRouter (Kimi) directly."
    if ! run_kimi_pass 1; then
        log "Forced OpenRouter pass 1 failed, aborting"
        exit 1
    fi
elif ! run_claude_step 1800 "$BRAINROT_DIR/.tmp/step2a-pass1.txt" "write-pass1"; then
    log "Pass 1 attempt 1 failed, retrying..."
    sleep 15
    if ! run_claude_step 1800 "$BRAINROT_DIR/.tmp/step2a-pass1.txt" "write-pass1-retry"; then
        log "Pass 1 Claude retry also failed — falling back to OpenRouter (Kimi) so the episode still ships."
        if ! run_kimi_pass 1; then
            log "Pass 1 OpenRouter fallback also failed, aborting"
            exit 1
        fi
    fi
fi

# Verify pass 1 produced a script
if [ ! -f "$BRAINROT_DIR/$SCRIPT_FILE" ]; then
    log "Pass 1 did not produce $SCRIPT_FILE, aborting"
    exit 1
fi

PASS1_WORDS=$(wc -w < "$BRAINROT_DIR/$SCRIPT_FILE" | tr -d ' ')
log "Pass 1 complete: $PASS1_WORDS words in $SCRIPT_FILE"

# ─── Step 2b: Pass 2 — NFL/NBA + Entertainment + Economics/Culture + Outro ───
cat > "$BRAINROT_DIR/.tmp/step2b-pass2.txt" <<PROMPT_EOF
You are producing the SECOND HALF of a Killen Time episode. Your working directory is /Users/kylekillen/brainrot-radio.

Read CLAUDE.md for full editorial guidelines, voice format, and content direction.

The first half of the episode has already been written to: ${SCRIPT_FILE}
READ IT FIRST so you know what topics and stories have already been covered in this episode.

YOUR JOB: APPEND the second half to the EXISTING script file. Cover SPORTS (NFL-led, NBA winding down), Entertainment, Economics/Culture, an optional brief prediction-markets quick-hit, and write the outro. Do NOT rewrite or duplicate anything from the first half.

Steps:
1. Read ${SCRIPT_FILE} — this is the first half you are continuing from. Note which stories were already covered.
2. Read .tmp/topic-brief.txt for remaining stories not yet covered
3. Read podcast transcripts from .tmp/transcripts/ — focus on NFL/football, NBA, entertainment, and economics podcasts
4. Read Substack articles in .tmp/articles/ — focus on economics, culture, and entertainment articles
5. Read scripts/.covered-*.json files for dedup against previous episodes
6. APPEND to ${SCRIPT_FILE} (do NOT overwrite — add to the end of the existing file):
   - **Sports segments (2-3 segments, ~2500-3500 words) — LEAD WITH NFL FOOTBALL; NBA is winding down.** NFL is the growing half of this beat as the NBA season ends. Lead with football: build around the Ringer Fantasy Football Show (Kyle's named anchor) plus Fantasy Footballers and Bill Barnwell — rankings, values/busts, roster strategy, real-football roster moves and league trends, with specific analyst quotes from the transcripts. Then cover NBA only for genuinely notable storylines (Finals, draft, major trades/free agency) and keep it tighter than before. Don't force a connection between the two — just move from football to basketball.
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

if [ -n "${PODCAST_FORCE_OPENROUTER:-}" ]; then
    # Manual escape hatch / quality test ONLY. Never set in the launchd default.
    log "PODCAST_FORCE_OPENROUTER=1 — skipping Claude for pass 2 and writing via OpenRouter (Kimi) directly."
    run_kimi_pass 2 || log "Forced OpenRouter pass 2 failed, proceeding with pass 1 only"
elif ! run_claude_step 1800 "$BRAINROT_DIR/.tmp/step2b-pass2.txt" "write-pass2"; then
    log "Pass 2 attempt 1 failed, retrying..."
    sleep 15
    if ! run_claude_step 1800 "$BRAINROT_DIR/.tmp/step2b-pass2.txt" "write-pass2-retry"; then
        log "Pass 2 Claude retry also failed — falling back to OpenRouter (Kimi) so the back half still gets written."
        run_kimi_pass 2 || log "Pass 2 OpenRouter fallback also failed, proceeding with pass 1 only"
    fi
fi

fi   # end engine branch (gemini | claude write)

# Check combined word count
NEW_SCRIPT="$BRAINROT_DIR/$SCRIPT_FILE"
TOTAL_WORDS=$(wc -w < "$NEW_SCRIPT" | tr -d ' ')
log "Combined script: $TOTAL_WORDS words"

# ─── Step 3: QC Review (independent outcome grader) ──────────────────────────
# Claude engine: 3-skeptic adversarial QC (below). Gemini engine: gemini_qc.py —
# a FRESH-context Gemini grader that sees ONLY the finished script + rubric (never
# the writer's context, so it can't inherit the writer's blind spots — the
# Independent Outcome Grader pattern) plus deterministic verifiable checks. Both
# end on a greppable `QC VERDICT:` and gate the same fail-loud way. Gemini path
# stays 100% Claude-free / $0.
if [ "${PODCAST_ENGINE:-claude}" != "gemini" ]; then
# Delegates to the .claude/commands/qc-episode.md command — the single source of
# truth for QC, shared with the interactive `/qc-episode` path. That command
# launches 3 independent adversarial agents (Freshness/Dedup, Coherence,
# Sourcing) each told to REFUTE the script from one angle, then a synthesizer
# keeps only issues ≥2 agents agree on (MUST-FIX) vs single-agent ADVISORY, fixes
# the MUST-FIX items, and prints `QC VERDICT: PASS`/`FAIL`. We read+follow the
# file rather than rely on slash-command expansion so the daily run is robust.
cat > "$BRAINROT_DIR/.tmp/step3-qc.txt" <<PROMPT_EOF
Read the file .claude/commands/qc-episode.md and follow its instructions exactly.
Your working directory is /Users/kylekillen/brainrot-radio.
The script to QC (the "\$1" argument the command refers to) is: $NEW_SCRIPT

This episode was written in two passes (front half: AI/tech + agents/building +
build-pitch; back half: NFL/NBA + entertainment + economics), so pay particular
attention to the half-join: a BASIL/BASIL collision and back-to-back [TRANSITION]
tags are the recurring two-pass defects.

Launch the three skeptics in parallel as the command directs, synthesize, fix all
MUST-FIX issues directly in the script file, and end with the QC VERDICT line.
PROMPT_EOF

# QC GATE. The QC command emits a literal `QC VERDICT: PASS`/`FAIL` (see
# .claude/commands/qc-episode.md). Previously this step only checked the claude
# call's EXIT code and rendered regardless — so an episode that ran QC, found
# MUST-FIX issues it couldn't fully fix, and printed `QC VERDICT: FAIL` still
# shipped silently. Now we read the verdict and re-run QC until it PASSes (each
# pass fixes more), bounded by QC_MAX_ATTEMPTS. If it never passes we FAIL LOUDLY
# (flag file + prominent log) instead of publishing a known-bad episode silently.
# QC_FAIL_ACTION decides the fallback: `publish` (default — a visible-but-flagged
# episode beats a silent missing one, and it's no longer silent) or `abort`.
# NB: this is the deterministic, headless-safe analog of Claude Code's interactive
# `/goal` ("work until the condition holds") — a cron pipeline wants a fixed,
# greppable verdict loop with no judge-model dependency or extra pool burn.
QC_MAX_ATTEMPTS=${QC_MAX_ATTEMPTS:-3}
QC_FAIL_ACTION=${QC_FAIL_ACTION:-publish}   # publish | abort
QC_VERDICT="none"
for attempt in $(seq 1 "$QC_MAX_ATTEMPTS"); do
    log "QC review attempt $attempt/$QC_MAX_ATTEMPTS (3 skeptics + synthesis + fixes)..."
    before=$(wc -l < "$RESULT_LOG")
    run_claude_step 1500 "$BRAINROT_DIR/.tmp/step3-qc.txt" "qc-review-$attempt" \
        || log "QC review step errored on attempt $attempt (continuing to verdict check)"
    # Scope the verdict to THIS attempt's NEW log lines so a timed-out attempt that
    # emits nothing can't inherit a prior attempt's stale PASS/FAIL.
    QC_VERDICT=$(tail -n +$((before + 1)) "$RESULT_LOG" \
        | grep -aoE "QC VERDICT: (PASS|FAIL)" | tail -1 | awk '{print $3}')
    QC_VERDICT=${QC_VERDICT:-none}
    log "QC verdict (attempt $attempt): $QC_VERDICT"
    [ "$QC_VERDICT" = "PASS" ] && break
done
if [ "$QC_VERDICT" != "PASS" ]; then
    QC_FLAG="$BRAINROT_DIR/logs/qc-FAIL-${RUN_ID}.flag"
    echo "QC did not reach PASS after $QC_MAX_ATTEMPTS attempts (last verdict: $QC_VERDICT) — script: $NEW_SCRIPT" > "$QC_FLAG"
    log "⚠️  QC GATE FAILED after $QC_MAX_ATTEMPTS attempts (last verdict: $QC_VERDICT). Flag: $QC_FLAG"
    if [ "$QC_FAIL_ACTION" = "abort" ]; then
        log "QC_FAIL_ACTION=abort → NOT publishing today's episode. Investigate $NEW_SCRIPT."
        exit 1
    fi
    log "QC_FAIL_ACTION=publish → publishing anyway, but this episode is FLAGGED sub-par (see $QC_FLAG)."
fi
else
    # Gemini engine: Independent Outcome Grader (separate-context rubric grade +
    # deterministic verifiable checks). Same fail-loud gate as Claude QC; $0/zero-Claude.
    # gemini_qc.py exits 0=PASS, non-zero=FAIL and prints the QC VERDICT line.
    QC_FAIL_ACTION=${QC_FAIL_ACTION:-publish}   # publish | abort
    log "QC review on GEMINI (independent outcome grader: fresh-context rubric + deterministic checks)..."
    if GEMINI_OUT="$NEW_SCRIPT" python3 gemini_qc.py "$NEW_SCRIPT" >> "$RESULT_LOG" 2>&1; then
        log "Gemini QC verdict: PASS"
    else
        QC_FLAG="$BRAINROT_DIR/logs/qc-FAIL-${RUN_ID}.flag"
        echo "Gemini QC did not reach PASS — script: $NEW_SCRIPT" > "$QC_FLAG"
        log "⚠️  GEMINI QC GATE FAILED. Flag: $QC_FLAG"
        if [ "$QC_FAIL_ACTION" = "abort" ]; then
            log "QC_FAIL_ACTION=abort → NOT publishing today's episode. Investigate $NEW_SCRIPT."
            exit 1
        fi
        log "QC_FAIL_ACTION=publish → publishing anyway, but this episode is FLAGGED sub-par (see $QC_FLAG)."
    fi
fi   # end QC engine branch

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
python3 artwork.py --title "$TITLE" --topics "AI, Agents & Building, NFL, Entertainment, Economics" >> "$RESULT_LOG" 2>&1 || log "Artwork generation failed (non-fatal)"

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

# ─── Step 6: Emit compound-loop signals (shared fleet brain) ─────────────────
# The podcast is a loop; after it publishes it writes signals other loops READ
# (the COS orientation, dispatched workers). 'covered' = what's already handled
# today (so other loops don't re-prioritize a covered story); 'gap' = a weakness
# worth a fix. Optional + non-fatal — absent signals.py changes nothing.
SIGNALS_PY="$HOME/observer-system/scripts/signals.py"
if [ -f "$SIGNALS_PY" ]; then
    COVERED=$(python3 - <<'PY' 2>/dev/null
import json, glob
files = sorted(glob.glob('scripts/.covered-*.json'))
if files:
    d = json.load(open(files[-1]))
    keys = list((d.get('segments') or {}).keys())[:8]
    print('; '.join(k.replace('-', ' ') for k in keys))
PY
)
    if [ -n "$COVERED" ]; then
        python3 "$SIGNALS_PY" emit --source brainrot-radio --category covered \
            --summary "Podcast covered today: $COVERED" --tags podcast \
            --linked "$SCRIPT_FILE" >> "$RESULT_LOG" 2>&1 && log "Signal: covered topics emitted."
    fi
    if [ -f "logs/qc-FAIL-${RUN_ID}.flag" ]; then
        python3 "$SIGNALS_PY" emit --source brainrot-radio --category gap \
            --summary "Today's episode shipped FLAGGED sub-par by QC (logs/qc-FAIL-${RUN_ID}.flag)" \
            --tags podcast >> "$RESULT_LOG" 2>&1 && log "Signal: QC-gap emitted."
    fi
fi

log "Episode generation complete (log: $RESULT_LOG)"
