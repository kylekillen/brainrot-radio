#!/bin/bash
# watch-episode.sh — is today's Killen Time run alive, dead, or missing? Alarm if it is
# not going to ship. Run by launchd every 10 min (com.mojo.brainrot-watch); cheap, idempotent.
#
# Covers what generate-episode.sh's own EXIT trap cannot: SIGKILL (check-episode.sh
# `kill -9`s stale claude processes), power loss, a run that hangs, and a run that never
# started at all. Each distinct problem alarms ONCE per day (marker files in $RG_DIR).
#
# Env for tests: BRAINROT_DIR, RG_DIR, RG_ALARM_BIN, WATCH_NOW (epoch), WATCH_HOUR, WATCH_TODAY.

BRAINROT_DIR="${BRAINROT_DIR:-/Users/kylekillen/brainrot-radio}"
RG_DIR="${RG_DIR:-$BRAINROT_DIR/.tmp}"
RG_WORKSPACE="$BRAINROT_DIR"
. "$BRAINROT_DIR/run_guard.sh"

NOW="${WATCH_NOW:-$(date +%s)}"
HOUR="${WATCH_HOUR:-$(date +%H)}"; HOUR=$((10#$HOUR))
TODAY="${WATCH_TODAY:-$(date +%Y-%m-%d)}"
LOG="$BRAINROT_DIR/logs/watch-episode.log"
HANG_MIN="${HANG_MIN:-75}"          # no progress for this long while the pid lives = hung
DEADLINE_HOUR="${DEADLINE_HOUR:-7}" # no episode and nothing running by here = alarm
mkdir -p "$BRAINROT_DIR/logs" 2>/dev/null
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG"; }

# Outside the production window there is nothing to watch.
[ "$HOUR" -ge 4 ] && [ "$HOUR" -lt 13 ] || exit 0
# Published: done.
[ -f "$BRAINROT_DIR/output/killen-time-${TODAY}.mp3" ] && exit 0

# once <key> <summary> <raw>: alarm at most once per (day, key).
once() {
    local marker="$RG_DIR/watch-alarmed-${TODAY}-$1"
    [ -f "$marker" ] && return 0
    log "ALARM: $2"
    if RG_STATE_FILE_OVERRIDE="$marker" rg_alarm "$marker" "$2" "$3"; then :; else log "alarm NOT spooled for $1 — will retry"; fi
}

alive_run=0
problem_seen=0
shopt -s nullglob
for f in "$RG_DIR"/run-state-*.env; do
    [ "$(rg_get "$f" date)" = "$TODAY" ] || continue
    state="$(rg_get "$f" state)"; rid="$(rg_get "$f" run_id)"; pid="$(rg_get "$f" pid)"
    case "$state" in
        running)
            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                alive_run=1
                beat="$(rg_get "$f" heartbeat)"; step="$(rg_get "$f" step)"
                if [ $(( (NOW - ${beat:-$NOW}) / 60 )) -ge "$HANG_MIN" ]; then
                    problem_seen=1
                    once "hung-$rid" "brainrot-radio run $rid looks HUNG: no progress for $(( (NOW - beat) / 60 )) min (pid $pid alive) — last step: $step" "state file $f"
                fi
            else
                # Died without the EXIT trap running (SIGKILL / power loss).
                problem_seen=1
                once "dead-$rid" "brainrot-radio run $rid DIED SILENTLY (pid $pid gone, no success or failure line) — last step: $(rg_get "$f" step)" "state file $f"
            fi ;;
        failed)
            # The run's own trap alarms; this is the retry if that alarm never spooled.
            problem_seen=1
            if [ "$(rg_get "$f" alarmed)" != "1" ]; then
                RG_STATE_FILE_OVERRIDE="$f" rg_alarm "$f" "brainrot-radio run $rid failed: $(rg_get "$f" reason)" "state file $f"
            fi ;;
    esac
done

# Nothing running and nothing shipped by the deadline: alarm once, whatever the reason.
# (A failed/dead/hung run has already alarmed above — don't page twice for the same miss.)
if [ "$alive_run" = "0" ] && [ "$problem_seen" = "0" ] && [ "$HOUR" -ge "$DEADLINE_HOUR" ]; then
    once "no-episode" "brainrot-radio: no episode for $TODAY as of $(date -r "$NOW" '+%H:%M' 2>/dev/null || date -d "@$NOW" '+%H:%M') and no run in progress — Kyle's daily show has not shipped" "see logs/check-episode.log and .tmp/run-state-*.env"
fi
exit 0
