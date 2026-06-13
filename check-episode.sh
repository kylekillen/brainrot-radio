#!/bin/bash
# Check if today's Killen Time episode was published.
# Run via launchd at multiple times throughout the morning.
# If no episode exists and pipeline is hung or not running, trigger recovery.

BRAINROT_DIR="/Users/kylekillen/brainrot-radio"
TODAY=$(date '+%Y-%m-%d')
TODAY_COMPACT=${TODAY//-/}
LOGFILE="$BRAINROT_DIR/logs/check-episode.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOGFILE"
}

# Success: episode MP3 exists
OUTPUT_FILE="$BRAINROT_DIR/output/killen-time-${TODAY}.mp3"
if [ -f "$OUTPUT_FILE" ]; then
    SCRIPT_FILE="$BRAINROT_DIR/scripts/killen-time-${TODAY}.txt"
    WORDS=$(wc -w < "$SCRIPT_FILE" 2>/dev/null | tr -d ' ')
    log "OK: Episode published ($WORDS words)"
    exit 0
fi

# Check if a claude process is running and how long
CLAUDE_PIDS=$(pgrep -f "claude.*dangerously-skip-permissions" 2>/dev/null)
if [ -n "$CLAUDE_PIDS" ]; then
    # Check each process — kill stale ones (>90 min), but if any are young, wait
    HAS_YOUNG=0
    for pid in $CLAUDE_PIDS; do
        ELAPSED=$(ps -o etime= -p "$pid" 2>/dev/null | awk '{
            n=split($0, t, ":");
            if (n == 3) print t[1]*3600 + t[2]*60 + t[3];
            else if (n == 2) print t[1]*60 + t[2];
            else print t[1];
        }')
        ELAPSED=${ELAPSED:-0}
        if [ "$ELAPSED" -gt 5400 ]; then
            log "Killing stale claude process $pid (${ELAPSED}s old)"
            kill -9 "$pid" 2>/dev/null
        else
            HAS_YOUNG=1
        fi
    done

    if [ "$HAS_YOUNG" -eq 1 ]; then
        log "WAIT: Active claude process running (under 90min)"
        exit 0
    fi
fi

# Check render/mix/publish still running
if pgrep -f "voice\.py\|mixer\.py\|publish\.py" > /dev/null 2>&1; then
    log "WAIT: Render/publish still in progress"
    exit 0
fi

# Nothing running, no episode — recovery needed
log "FAIL: No episode for $TODAY and nothing running"

LAST_LOG=$(ls -t "$BRAINROT_DIR"/logs/generate-${TODAY_COMPACT}*.log 2>/dev/null | head -1)
if [ -n "$LAST_LOG" ]; then
    FAILURE=$(grep -E 'TIMED OUT|FAILED|aborting' "$LAST_LOG" | tail -3)
    log "Failure details: $FAILURE"
fi

RECOVERY_LOG="$BRAINROT_DIR/logs/recovery-${TODAY_COMPACT}.log"
if [ -f "$RECOVERY_LOG" ]; then
    RECOVERY_SIZE=$(wc -c < "$RECOVERY_LOG" 2>/dev/null | tr -d ' ')
    # If the recovery log is tiny (<100 bytes), it crashed immediately — allow retry
    if [ "${RECOVERY_SIZE:-0}" -gt 100 ]; then
        log "SKIP: Recovery already attempted today (see $RECOVERY_LOG, $RECOVERY_SIZE bytes)"
        exit 1
    fi
    log "Recovery log is empty, allowing retry"
fi

log "RECOVERY: Starting generate-episode.sh"
nohup /usr/bin/env \
    HOME=/Users/kylekillen \
    PATH=/Users/kylekillen/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin \
    SHELL=/bin/bash \
    /bin/bash -l -c 'cd /Users/kylekillen/brainrot-radio && source venv/bin/activate && bash generate-episode.sh' \
    >> "$RECOVERY_LOG" 2>&1 &
log "Recovery PID: $!"
