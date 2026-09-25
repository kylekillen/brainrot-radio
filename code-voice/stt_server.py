#!/usr/bin/env python3
"""Code Voice — local Parakeet STT server (OpenAI-compatible).

Exposes POST /v1/audio/transcriptions (the OpenAI audio-transcription shape)
backed by local mlx-audio Parakeet, with mlx-whisper retained as a fallback.
ccgram points CCGRAM_WHISPER_BASE_URL at this — so voice notes from the phone
are transcribed locally, free, no cloud key.

Telegram voice notes are OGG/Opus; mlx-audio decodes via ffmpeg, so the
format is handled transparently.

Run via LaunchAgent (com.codevoice.stt). Manual:
    cd ~/brainrot-radio && source venv/bin/activate && python3 code-voice/stt_server.py
"""
import email
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# The LaunchAgent starts this file by absolute path, so make the repository
# root importable for the shared transcription engine.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import FFMPEG  # noqa: E402
import qos  # noqa: E402
from transcribe import FALLBACK_MODEL, PRIMARY_MODEL, transcribe as transcribe_file  # noqa: E402

HOST = "127.0.0.1"
PORT = int(os.environ.get("CODEVOICE_STT_PORT", "8766"))
MODEL = PRIMARY_MODEL
FALLBACK = FALLBACK_MODEL
LOG = Path.home() / "brainrot-radio" / "code-voice" / "stt_server.log"

# Parakeet on the CPU (onnx-asr, int8): the MLX build runs on the GPU, which the fleet's
# big local model saturates; measured 2026-09-24 the same 15s clip took 5-80s there
# vs 0.5-0.7s here, regardless of GPU load. The MLX path stays as the fallback.
ONNX_MODEL = "nemo-parakeet-tdt-0.6b-v3"

_warm = False
_onnx = None
_onnx_lock = threading.Lock()


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, file=sys.stderr, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


# A real recording is many KB; anything smaller is an aborted/empty capture.
MIN_AUDIO_BYTES = 1024


class TinyUpload(ValueError):
    """The uploaded audio is too small to be a real recording."""


def to_wav(src: str, dst: str) -> None:
    """Transcode any upload to 16 kHz mono wav, the one shape Parakeet always accepts.

    Chrome on the phone sends webm/opus, which Parakeet's loader rejects
    ("unsupported file format"), silently sending every take to a cold Whisper.
    """
    proc = subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error", "-i", src, "-ar", "16000", "-ac", "1", dst],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg transcode failed: {proc.stderr.strip()[-200:]}")


def _onnx_recognize(wav: str) -> str:
    global _onnx
    with _onnx_lock:
        if _onnx is None:
            import onnx_asr

            _onnx = onnx_asr.load_model(ONNX_MODEL, quantization="int8",
                                        providers=["CPUExecutionProvider"])
    return (_onnx.recognize(wav) or "").strip()


def transcribe_bytes(audio_bytes: bytes, filename: str) -> str:
    if len(audio_bytes) < MIN_AUDIO_BYTES:
        raise TinyUpload(f"audio too small ({len(audio_bytes)} bytes) - empty or aborted recording")
    suffix = os.path.splitext(filename)[1].lower() or ".ogg"
    fd, path = tempfile.mkstemp(prefix="codevoice_stt_", suffix=suffix)
    os.close(fd)
    with open(path, "wb") as f:
        f.write(audio_bytes)
    wav = path + ".wav"
    try:
        try:
            t0 = time.perf_counter()
            to_wav(path, wav)
            log(f"transcode {time.perf_counter()-t0:.2f}s")
        except Exception as e:  # noqa: BLE001
            # Not fatal: hand the original to the MLX engine and let Whisper try.
            log(f"transcode failed ({e}); passing original file through")
            wav = path
        if wav != path:
            try:
                t0 = time.perf_counter()
                text = _onnx_recognize(wav)
                log(f"cpu parakeet {time.perf_counter()-t0:.2f}s")
                return text
            except Exception as e:  # noqa: BLE001
                log(f"cpu parakeet failed ({e}); falling back to MLX")
        return transcribe_file(wav, model=MODEL)
    finally:
        for f in {path, wav}:
            try:
                os.unlink(f)
            except OSError:
                pass


KEEP_HOT_SECS = 15


def keep_hot(wav: str) -> None:
    """Re-run the CPU model on silence so its weights stay resident.

    The mini is deep in swap (fseventsd alone holds ~27 GB), and a model idle for
    ~20 s came back at 5.9 s for the first phone take instead of 0.5 s.
    """
    qos.set_interactive()
    while True:
        time.sleep(KEEP_HOT_SECS)
        try:
            _onnx_recognize(wav)
        except Exception as e:  # noqa: BLE001
            log(f"keep-hot failed: {e}")


def warmup():
    """Trigger model load now so the first real voice note is fast."""
    global _warm
    qos.set_interactive()
    try:
        import numpy as np
        import soundfile as sf

        fd, path = tempfile.mkstemp(prefix="codevoice_warm_", suffix=".wav")
        os.close(fd)
        sf.write(path, np.zeros(16000, dtype="float32"), 16000)  # 1s silence
        with open(path, "rb") as f:
            transcribe_bytes(f.read(), "warm.wav")
        _warm = True
        log("warmup complete — STT model is hot")
        keep_hot(path)
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
            self._json(
                200,
                {
                    "ok": True,
                    "warm": _warm,
                    "model": MODEL,
                    "fallback_model": FALLBACK,
                },
            )
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        qos.set_interactive()
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
            if len(audio) < MIN_AUDIO_BYTES:
                self._json(400, {"error": f"audio too small ({len(audio)} bytes) - empty or aborted recording"})
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
    qos.set_interactive()
    log(f"Code Voice STT server starting on {HOST}:{PORT}")
    threading.Thread(target=warmup, daemon=True).start()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
