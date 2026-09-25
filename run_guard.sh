#!/bin/bash
# run_guard.sh — sourced by generate-episode.sh (writer side) and watch-episode.sh
# (watcher side). Makes an episode run that ends without a success line RAISE.
#
# Why (2026-09-25): the 05:15 recovery run died at 05:54 after logging only a generic
# "Voice render failed, aborting" into a file nobody reads, and the only checker
# (check-episode.sh, 05:15/05:45) had already run. Nothing raised; the miss was found
# six hours later by a human. Same class as the 09-23 writer hang.
#
# Writer side  : rg_start / rg_beat / rg_finish / rg_on_exit (EXIT trap -> alarm on any
#                exit that never declared ok|standdown, incl. `set -e` aborts, `exit 1`,
#                and TERM/INT/HUP — those are converted to a normal exit so the trap runs).
# Watcher side : watch-episode.sh reads the state file for the one thing a trap cannot
#                cover — SIGKILL / power loss — pid dead or heartbeat stale.
#
# State file: $RG_DIR/run-state-<RUN_ID>.env, key=value lines, written atomically.
#   state=running|ok|standdown|failed   pid  run_id  date  started  heartbeat  step  rc  reason  alarmed
#
# Alarms go through the fleet's alarm pipeline (raise-alarm.sh -> responder dispatches an
# investigating agent). --no-telegram: Telegram is off on purpose (Kyle, 2026-09-23).

RG_DIR="${RG_DIR:-/Users/kylekillen/brainrot-radio/.tmp}"
RG_ALARM_BIN="${RG_ALARM_BIN:-$HOME/.claude/scripts/raise-alarm.sh}"
RG_WORKSPACE="${RG_WORKSPACE:-/Users/kylekillen/brainrot-radio}"
RG_RUN_ID="${RG_RUN_ID:-$(date '+%Y%m%d-%H%M%S')}"
RG_OUTCOME=""
RG_STATE_FILE="$RG_DIR/run-state-${RG_RUN_ID}.env"

# rg_set key=value ... : update keys in the state file atomically (creates it if absent).
rg_set() {
    local f="${RG_STATE_FILE_OVERRIDE:-$RG_STATE_FILE}" tmp kv key
    mkdir -p "$(dirname "$f")" 2>/dev/null
    tmp="$f.tmp.$$"
    { [ -f "$f" ] && cat "$f"; } > "$tmp" 2>/dev/null || : > "$tmp"
    for kv in "$@"; do
        key="${kv%%=*}"
        { grep -v "^${key}=" "$tmp" > "$tmp.2" 2>/dev/null || true; }   # exit 1 = no lines left: fine under set -e
        mv "$tmp.2" "$tmp"
        printf '%s\n' "$kv" | tr '\n' ' ' | sed 's/ $//' >> "$tmp"; printf '\n' >> "$tmp"
    done
    mv "$tmp" "$f"
}

# rg_get file key : value of key in a state file ("" if absent).
rg_get() { sed -n "s/^$2=//p" "$1" 2>/dev/null | tail -1; }

rg_start() {
    rg_set state=running pid=$$ run_id="$RG_RUN_ID" date="$(date '+%Y-%m-%d')" \
           started="$(date +%s)" heartbeat="$(date +%s)" step=start alarmed=0
}

# rg_beat "message": record progress. Cheap; called from log() and the claude poll loop.
rg_beat() {
    if [ -n "${1:-}" ]; then rg_set heartbeat="$(date +%s)" step="$1"; else rg_set heartbeat="$(date +%s)"; fi
}

# rg_finish ok|standdown : declare a legitimate end. Anything else at exit is a failure.
rg_finish() {
    RG_OUTCOME="$1"
    rg_set state="$1" heartbeat="$(date +%s)"
}

# rg_alarm <state-file> <summary> <raw> : raise once per state file. Returns 0 if spooled.
rg_alarm() {
    local f="$1" summary="$2" raw="$3" path
    [ "$(rg_get "$f" alarmed)" = "1" ] && return 0
    path=$("$RG_ALARM_BIN" --no-telegram --print-path brainrot-radio "$RG_WORKSPACE" critical \
        "$summary" "$raw" \
        "Read ~/brainrot-radio/logs/generate-<RUN_ID>.log (tail), logs/generate.log, logs/check-episode.log and .tmp/run-state-*.env. Kyle gets one episode a day; if none shipped, diagnose, fix the guard-class cause (never lower the render word floor), and report." \
        2>/dev/null)
    if [ -n "$path" ]; then
        RG_STATE_FILE_OVERRIDE="$f" rg_set alarmed=1
        return 0
    fi
    return 1   # not spooled: leave alarmed=0 so the watcher retries — noisy, never silent
}

# EXIT trap body for generate-episode.sh.
rg_on_exit() {
    local rc=$?
    [ -n "$RG_OUTCOME" ] && return 0
    local step; step="$(rg_get "$RG_STATE_FILE" step)"
    rg_set state=failed rc="$rc" reason="exit $rc at: $step"
    rg_alarm "$RG_STATE_FILE" \
        "brainrot-radio run $RG_RUN_ID ended without shipping an episode (exit $rc) — last step: $step" \
        "$(tail -n 3 "${RESULT_LOG:-/dev/null}" 2>/dev/null | tr '\n' ' ' | cut -c1-380)" || true
    return 0
}

# Turn catchable signals into a normal exit so the EXIT trap (and its alarm) runs.
trap 'exit 143' TERM
trap 'exit 130' INT
trap 'exit 129' HUP
