#!/bin/bash
# Code Voice — launch the ccgram Telegram<->Claude Code bridge, wired to the
# LOCAL Kokoro TTS (Brooke) and local Whisper STT servers. Fully local, $0.
#
# Prereq: the bot token from @BotFather lives in:
#   ~/.config/codevoice/telegram-bot-token   (one line, just the token)
# and the two local servers (com.codevoice.server :8765, com.codevoice.stt :8766)
# are running. ccgram drives a tmux session named "ccgram"; create Telegram
# forum topics to spawn Claude Code windows in it.

set -euo pipefail
export PATH="/Users/kylekillen/.local/bin:/opt/homebrew/bin:$PATH"

TOKEN_FILE="$HOME/.config/codevoice/telegram-bot-token"
if [ ! -s "$TOKEN_FILE" ]; then
  echo "ERROR: no bot token at $TOKEN_FILE" >&2
  echo "Create a bot with @BotFather, then: echo '<token>' > $TOKEN_FILE" >&2
  exit 1
fi

# Verify local voice servers are up (fail loudly rather than silently using cloud)
for url in "http://127.0.0.1:8765/health" "http://127.0.0.1:8766/health"; do
  if ! curl -sf "$url" >/dev/null 2>&1; then
    echo "ERROR: local voice server not reachable: $url" >&2
    echo "Check: launchctl list | grep codevoice" >&2
    exit 1
  fi
done

export TELEGRAM_BOT_TOKEN="$(tr -d '[:space:]' < "$TOKEN_FILE")"
export ALLOWED_USERS="5063371068"

# Voice IN — local Whisper (OpenAI-compatible) at :8766
export CCGRAM_WHISPER_PROVIDER="openai"
export CCGRAM_WHISPER_BASE_URL="http://127.0.0.1:8766/v1"
export CCGRAM_WHISPER_API_KEY="local"
export CCGRAM_WHISPER_MODEL="whisper-1"

# Voice OUT — local Kokoro "Brooke" (OpenAI-compatible) at :8765
export CCGRAM_TTS_PROVIDER="openai"
export CCGRAM_TTS_BASE_URL="http://127.0.0.1:8765/v1"
export CCGRAM_TTS_API_KEY="local"
export CCGRAM_TTS_VOICE="af_heart"
export CCGRAM_TTS_MODEL="kokoro"

echo "Starting ccgram (local Brooke TTS + local Whisper STT)…"
exec ccgram run --allowed-users "$ALLOWED_USERS" "$@"
