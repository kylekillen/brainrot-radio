#!/bin/bash
# sandboxed-claude.sh [claude args...] — run the claude CLI for a step that READS THE
# OPEN WEB (beat reporters, build-pitch, write passes, QC, top-up) inside a macOS
# Seatbelt box, so a poisoned page can't turn into a stolen key.
# Trifecta audit lane 1 (2026-10-26, ~/.observer/wiki/agent-os/trifecta-audit.md).
#
# What the box does (observer.mcp.sandbox.build_agent_profile): reads of ~/.config
# (gh token, personal-os *.env), ~/.ssh and ~/.observer/secrets are refused by the
# kernel; writes go only to this repo + the CLI's own state + temp; the environment
# is rebuilt from a short allowlist (no GH_TOKEN, API keys, OBSERVER_*). Network,
# shell and the web tools still work, so the steps behave as before. The publish
# step (publish.py) is NOT run through this wrapper and keeps its tokens.
#
# Modes, loudest-first:
#   BRAINROT_CLAUDE_SANDBOX=off   escape hatch / rollback: today's unfenced behavior.
#   sandbox-exec unavailable      DEGRADED: scrubbed env + --tools "Read,Write,Edit,
#                                 WebSearch,WebFetch" (no shell). Partial: WebFetch
#                                 can still carry a URL out, but nothing is in reach.
# Uses exec, so the caller's `$!` / kill -9 still lands on claude itself.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAUDE_BIN="${CLAUDE_BIN:-/Users/kylekillen/.local/bin/claude}"
OBS_PY="${OBS_PY:-$HOME/observer-system/.venv/bin/python}"
WRITE_DIR="${BRAINROT_SANDBOX_WRITE:-$HERE}"
# Pipeline state the steps read from their env (generate-episode.sh exports these).
KEEP_ENV=(BEAT_LEDGER_DIR COVERED_DEFER CODE_VOICE_MUTE RG_RUN_ID RG_DIR PODCAST_ENGINE ROUTER_MODE BRAINROT_DIR)

if [ "${BRAINROT_CLAUDE_SANDBOX:-on}" = "off" ]; then
    echo "sandboxed-claude: ⚠️  BRAINROT_CLAUDE_SANDBOX=off — running claude UNFENCED" >&2
    exec "$CLAUDE_BIN" "$@"
fi

keep=()
for n in "${KEEP_ENV[@]}"; do keep+=(--keep-env "$n"); done

# Match the marker, not the exit code: an observer-system checkout that predates this CLI
# exits 0 from `-m observer.mcp.sandbox` having run nothing.
if [ -x "$OBS_PY" ] && [ "$("$OBS_PY" -m observer.mcp.sandbox available 2>/dev/null)" = "sandbox-exec-ok" ]; then
    exec "$OBS_PY" -m observer.mcp.sandbox exec --write "$WRITE_DIR" "${keep[@]}" -- "$CLAUDE_BIN" "$@"
fi

echo "sandboxed-claude: ⚠️  Seatbelt unavailable (OBS_PY=$OBS_PY) — DEGRADED: scrubbed env, no shell tool" >&2
env_args=()
for n in PATH HOME USER LOGNAME SHELL LANG LC_ALL TERM TMPDIR "${KEEP_ENV[@]}"; do
    [ -n "${!n+x}" ] && env_args+=("$n=${!n}")
done
exec env -i "${env_args[@]}" "$CLAUDE_BIN" --tools "Read,Write,Edit,WebSearch,WebFetch" "$@"
