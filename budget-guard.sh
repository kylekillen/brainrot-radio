#!/bin/bash
# budget-guard.sh — preserve the trading money-monitor's Claude pool by standing
# down NON-CRITICAL Claude-hungry jobs (the daily podcast, the Fleet Optimizer
# daily scan) when the shared pool is under cap-pressure.
#
# Usage:
#   budget-guard.sh check    # exit 0 = clear to run; exit 1 = stand down
#
# Detection — honest about what's observable. On the Max plan there is NO
# remaining-budget API, so we can't predict "nearing" precisely. What we CAN
# observe is a cap-hit that already happened: the trading sentinel's alarm
# responder writes <id>.error files when its `claude -p` worker fails, and a
# FRESH one mentioning a spend/rate/overload limit means the shared pool is
# exhausted RIGHT NOW. While that's true within a cooldown window, non-critical
# jobs stand down so the money-monitor keeps whatever headroom remains. The guard
# auto-clears once no recent cap-hit (pool recovered).
#
# This is the interim software stopgap. The durable fix is per-workload KEY
# TIERING (see agent-os/proposal-tiered-failover-2026-06-18.md) — separate pools
# make the podcast unable to starve trading in the first place, retiring this guard.
set -euo pipefail

ALARM_ACTIVE="${ALARM_ACTIVE:-$HOME/.observer/alarms/active}"
COOLDOWN_MIN="${BUDGET_COOLDOWN_MIN:-360}"   # 6h
PATTERN='spend limit|usage limit|rate limit|overloaded|monthly spend|429'

cmd="${1:-check}"
case "$cmd" in
  check)
    if [ -d "$ALARM_ACTIVE" ]; then
      hit=$(find "$ALARM_ACTIVE" -name '*.error' -mmin "-${COOLDOWN_MIN}" -print0 2>/dev/null \
            | xargs -0 grep -lEi "$PATTERN" 2>/dev/null | head -1 || true)
      if [ -n "${hit:-}" ]; then
        echo "BUDGET-PRESSURE: recent cap-hit in $(basename "$hit") (within ${COOLDOWN_MIN}m) — stand down non-critical job" >&2
        exit 1
      fi
    fi
    exit 0
    ;;
  *)
    echo "usage: $0 check" >&2
    exit 2
    ;;
esac
