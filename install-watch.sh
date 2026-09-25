#!/bin/bash
# Install/refresh the run watcher launchd job from the repo copy. Idempotent.
# Run after merging changes to watch-episode.sh / run_guard.sh / the plist:
#   cd ~/brainrot-radio && git pull --ff-only && bash install-watch.sh
# (The plists are source-controlled in launchd/; a merge alone does not update the live copy.)
set -e
SRC="$(cd "$(dirname "$0")" && pwd)/launchd/com.mojo.brainrot-watch.plist"
DST="$HOME/Library/LaunchAgents/com.mojo.brainrot-watch.plist"
plutil -lint "$SRC" >/dev/null
cp "$SRC" "$DST"
launchctl bootout "gui/$(id -u)/com.mojo.brainrot-watch" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DST"
launchctl print "gui/$(id -u)/com.mojo.brainrot-watch" | grep -E "state|interval" | head -3
echo "brainrot-watch installed (every 10 min, watches 04:00-13:00 local)"
