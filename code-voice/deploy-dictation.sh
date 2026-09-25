#!/bin/bash
# Deploy merged dictation changes to the live mini and prove the latency claim.
# Idempotent. Run after the PR is on main:  bash code-voice/deploy-dictation.sh
set -euo pipefail
REPO="$HOME/brainrot-radio"
UID_=$(id -u)
cd "$REPO"
[ "$(git rev-parse --abbrev-ref HEAD)" = main ] || { echo "FAIL: $REPO is not on main" >&2; exit 1; }
git pull --ff-only -q origin main

"$REPO/venv/bin/python" -c "import onnx_asr" 2>/dev/null || "$REPO/venv/bin/pip" install -q "onnx-asr[cpu,hub]"

# The dedicated cleanup ollama: (re)install its plist only if it changed.
SRC="$REPO/code-voice/com.codevoice.ollama.plist"; DST="$HOME/Library/LaunchAgents/com.codevoice.ollama.plist"
if ! cmp -s "$SRC" "$DST"; then
  launchctl bootout "gui/$UID_/com.codevoice.ollama" 2>/dev/null || true
  cp "$SRC" "$DST"
  launchctl bootstrap "gui/$UID_" "$DST"
fi
launchctl print "gui/$UID_/com.codevoice.ollama" >/dev/null
for i in $(seq 1 30); do curl -sf 127.0.0.1:11435/api/tags >/dev/null && break; sleep 1; done
curl -sf 127.0.0.1:11435/api/tags | grep -q "qwen3:4b-instruct-2507-q4_K_M" || OLLAMA_HOST=127.0.0.1:11435 ollama pull qwen3:4b-instruct-2507-q4_K_M

launchctl kickstart -k "gui/$UID_/com.codevoice.stt"
launchctl kickstart -k "gui/$UID_/com.codevoice.dictate"
for i in $(seq 1 90); do
  curl -sf 127.0.0.1:8766/health | grep -q '"warm": true' && curl -sf 127.0.0.1:8767/health | grep -q '"clean_model_loaded": true' && break
  sleep 2
done
curl -s 127.0.0.1:8766/health; echo; curl -s 127.0.0.1:8767/health; echo
sleep 20  # let the first keep-hot cycle run, like a real idle gap
{ date -u +%FT%TZ; python3 "$REPO/code-voice/bench_dictate.py" --runs 5 --load "${LOAD:-2}"; } | tee -a "$HOME/.observer/dictation/deploy-bench.log"
