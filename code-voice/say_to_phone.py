#!/usr/bin/env python3
"""Code Voice — speak text to Kyle's phone as a Telegram voice note.

The voice-OUT-only path: take text (my response), synthesize it in the
Brooke/Kokoro voice via the local warm server, and deliver it to the phone
as a Telegram voice note (tap-and-play, with a push notification). Reuses
Kyle's EXISTING Telegram bot — sending to your own chat needs no BotFather
setup. No STT, no ccgram, no new bot.

Text comes from argv (joined) or stdin. Markdown is stripped; code blocks
dropped. Reads creds from env (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID), or
falls back to the env block in ~/.claude/settings.json.

    echo "hello from your phone" | python3 say_to_phone.py
    python3 say_to_phone.py "hello from your phone"
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from text_clean import strip_markdown  # noqa: E402

TTS_ENDPOINT = "http://127.0.0.1:8765/v1/audio/speech"
VOICE = "af_heart"  # Brooke
FFMPEG = "/opt/homebrew/bin/ffmpeg"


def _creds():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "") or os.getenv("CHAT_ID", "")
    if token and chat:
        return token, chat
    # Fallback: pull from the Claude settings env block.
    try:
        s = json.loads((Path.home() / ".claude" / "settings.json").read_text())
        env = s.get("env", {})
        token = token or env.get("TELEGRAM_BOT_TOKEN", "")
        chat = chat or (env.get("TELEGRAM_ALLOWED_SENDER_IDS", "").split(",")[0].strip())
    except Exception:  # noqa: BLE001
        pass
    return token, chat


def synth_mp3(text: str) -> bytes:
    payload = json.dumps({"model": "kokoro", "voice": VOICE, "input": text}).encode()
    # Retry on transient connection failures. The TTS server serializes synthesis
    # behind a lock, but it can still be briefly unavailable (e.g. mid-restart, or
    # a request that landed during a crash before the lock was added). A short
    # backoff lets the note survive that window instead of vanishing silently.
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(
                TTS_ENDPOINT, data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            last = e
            time.sleep(1.5 * (attempt + 1))  # 1.5s, 3s, 4.5s
    raise last if last else RuntimeError("synth failed")


def mp3_to_opus_ogg(mp3: bytes) -> str:
    fd, mp3p = tempfile.mkstemp(suffix=".mp3")
    os.write(fd, mp3)
    os.close(fd)
    oggp = mp3p[:-4] + ".ogg"
    subprocess.run(
        [FFMPEG, "-y", "-i", mp3p, "-c:a", "libopus", "-b:a", "32k", oggp],
        capture_output=True, check=True,
    )
    os.unlink(mp3p)
    return oggp


def send_voice(token: str, chat: str, ogg_path: str):
    """Multipart POST to Telegram sendVoice (stdlib, no deps)."""
    boundary = "----codevoice7e3f"
    with open(ogg_path, "rb") as f:
        audio = f.read()
    parts = []
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat}\r\n".encode())
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"voice\"; filename=\"reply.ogg\"\r\n"
        f"Content-Type: audio/ogg\r\n\r\n".encode()
    )
    parts.append(audio)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendVoice",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def main():
    text = " ".join(sys.argv[1:]).strip() or sys.stdin.read()
    text = strip_markdown(text)
    if not text.strip():
        print("nothing to say", file=sys.stderr)
        return 0
    token, chat = _creds()
    if not token or not chat:
        print("missing TELEGRAM_BOT_TOKEN / chat id", file=sys.stderr)
        return 1
    ogg = mp3_to_opus_ogg(synth_mp3(text))
    try:
        resp = send_voice(token, chat, ogg)
        print("ok" if resp.get("ok") else f"telegram error: {resp}", file=sys.stderr)
        return 0 if resp.get("ok") else 1
    finally:
        try:
            os.unlink(ogg)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
