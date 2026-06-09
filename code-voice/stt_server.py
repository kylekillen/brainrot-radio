#!/usr/bin/env python3
"""Code Voice — local Whisper STT server (OpenAI-compatible).

Exposes POST /v1/audio/transcriptions (the OpenAI audio-transcription shape)
backed by local mlx-whisper (whisper-large-v3-turbo, already cached in this
workspace). ccgram points CCGRAM_WHISPER_BASE_URL at this — so voice notes
from the phone are transcribed locally, free, no cloud key.

Telegram voice notes are OGG/Opus; mlx-whisper decodes via ffmpeg, so the
format is handled transparently.

Run via LaunchAgent (com.codevoice.stt). Manual:
    cd ~/brainrot-radio && source venv/bin/activate && python3 code-voice/stt_server.py
"""
import email
import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8766
MODEL = "mlx-community/whisper-large-v3-turbo"  # cached; matches transcribe.py
LOG = Path.home() / "brainrot-radio" / "code-voice" / "stt_server.log"

_warm = False
_lock = threading.Lock()  # mlx-whisper isn't thread-safe; serialize calls


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, file=sys.stderr, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def transcribe_bytes(audio_bytes: bytes, filename: str) -> str:
    import mlx_whisper

    suffix = os.path.splitext(filename)[1] or ".ogg"
    fd, path = tempfile.mkstemp(prefix="codevoice_stt_", suffix=suffix)
    os.close(fd)
    with open(path, "wb") as f:
        f.write(audio_bytes)
    try:
        with _lock:
            result = mlx_whisper.transcribe(path, path_or_hf_repo=MODEL)
        return (result.get("text") or "").strip()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def warmup():
    """Trigger model load now so the first real voice note is fast."""
    global _warm
    try:
        import numpy as np
        import soundfile as sf

        fd, path = tempfile.mkstemp(prefix="codevoice_warm_", suffix=".wav")
        os.close(fd)
        sf.write(path, np.zeros(16000, dtype="float32"), 16000)  # 1s silence
        with open(path, "rb") as f:
            transcribe_bytes(f.read(), "warm.wav")
        os.unlink(path)
        _warm = True
        log("warmup complete — STT model is hot")
    except Exception as e:  # noqa: BLE001
        log(f"warmup failed: {e}")


def parse_upload(content_type: str, body: bytes):
    """Pull the uploaded file out of a multipart/form-data body (stdlib email)."""
    header = b"Content-Type: " + content_type.encode() + b"\r\n\r\n"
    msg = email.message_from_bytes(header + body)
    for part in msg.walk():
        if part.get_filename():
            return part.get_payload(decode=True), part.get_filename()
    return None, None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"ok": True, "warm": _warm})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path not in ("/v1/audio/transcriptions", "/audio/transcriptions"):
            self._json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            ctype = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in ctype:
                self._json(400, {"error": "expected multipart/form-data"})
                return
            audio, filename = parse_upload(ctype, body)
            if not audio:
                self._json(400, {"error": "no file part"})
                return
            t0 = time.perf_counter()
            text = transcribe_bytes(audio, filename or "audio.ogg")
            log(f"transcribed {len(audio)} bytes in {time.perf_counter()-t0:.2f}s: {text[:80]!r}")
            self._json(200, {"text": text})
        except Exception as e:  # noqa: BLE001
            log(f"transcribe error: {e}")
            self._json(500, {"error": str(e)})


def main():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    log(f"Code Voice STT server starting on {HOST}:{PORT}")
    threading.Thread(target=warmup, daemon=True).start()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
