#!/usr/bin/env python3
"""Code Voice — resident warm TTS server.

Loads Kokoro (mlx-audio) ONCE and keeps it resident so per-turn synthesis
is ~0.6s instead of the ~4.8s cold-start measured on this machine. The
Stop hook POSTs raw response text here; this server summarizes it
(local Ollama, free) and speaks it in the Killen Time "Brooke" voice
(af_heart) via afplay, with a single playback worker so audio never
overlaps.

Run via the LaunchAgent (com.codevoice.server). For manual runs:
    cd ~/brainrot-radio && source venv/bin/activate
    python3 code-voice/server.py

Endpoints:
    POST /speak   {"text": "...", "session": "optional-id"}  -> 200, fire-and-forget
    GET  /health  -> {"ok": true, "warm": bool, "queue": N}
"""
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from text_clean import strip_markdown, is_short  # noqa: E402

HOST = "127.0.0.1"
PORT = 8765
VOICE = "af_heart"          # Killen Time "Brooke" — confirmed stock Kokoro voice
LANG = "a"
KOKORO_MODEL = "mlx-community/Kokoro-82M-bf16"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:7b"
LOG = Path.home() / "brainrot-radio" / "code-voice" / "server.log"
MAX_QUEUE = 4               # drop oldest beyond this so stale turns don't pile up

SUMMARY_SYSTEM = (
    "You rewrite an AI coding assistant's chat response into spoken-word form "
    "to be read aloud to the user. This is NOT a terse headline — it is a "
    "faithful spoken version. Rules, in priority order:\n"
    "1. NEVER drop a question the response asks the user, or a decision the "
    "user is being asked to make. Every distinct question must survive, "
    "phrased as a question.\n"
    "2. Cover every distinct point the response makes — one clause or short "
    "sentence each. Length scales with content: a one-idea reply is one "
    "sentence; a reply that raises three points and a question is four-plus "
    "sentences. Do not collapse multiple points into one.\n"
    "3. Keep specific numbers, file names, blockers, and decisions made.\n"
    "4. Lead with the outcome or bottom line.\n"
    "5. Drop only pleasantries, restated context, and code. Replace code with "
    "a brief description of what it does.\n"
    "Plain spoken prose, no markdown, no lists, no headers. Add no information "
    "that isn't in the response. Output ONLY the spoken text."
)

_model = None
_warm = False
_jobs: "queue.Queue" = queue.Queue()
# Loading the Kokoro model touches the GPU. If two threads call get_model()
# concurrently (e.g. warmup racing the first request) they both run Metal work
# at once and abort the process. Make the load atomic.
_model_lock = threading.Lock()


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, file=sys.stderr, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:  # re-check under lock
                from mlx_audio.tts.utils import load_model
                log(f"loading Kokoro model {KOKORO_MODEL} ...")
                _model = load_model(KOKORO_MODEL)
                log("Kokoro model loaded")
    return _model


def summarize(text: str) -> str:
    """Compress via local Ollama. Falls back to the cleaned text on any error."""
    if is_short(text):
        return text
    payload = {
        "model": OLLAMA_MODEL,
        "system": SUMMARY_SYSTEM,
        "prompt": text,
        "stream": False,
        "keep_alive": "30m",  # keep summarizer resident through a work session
        "options": {"temperature": 0.2},
    }
    try:
        req = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            out = json.loads(resp.read()).get("response", "").strip()
        if out:
            return out
        log("summarize: empty response, falling back to cleaned text")
    except Exception as e:  # noqa: BLE001
        log(f"summarize failed ({e}); falling back to cleaned text")
    # Fallback: first few sentences so we don't dump the whole thing.
    sentences = text.replace("\n", " ").split(". ")
    return ". ".join(sentences[:3]).strip()


FFMPEG = "/opt/homebrew/bin/ffmpeg"

# mlx Kokoro is NOT thread-safe. ThreadingHTTPServer handles each request in its
# own thread, so when two turns end close together their /v1/audio/speech calls
# hit model.generate() concurrently and CRASH THE WHOLE SERVER PROCESS (launchd
# then restarts it, and every in-flight request dies with RemoteDisconnected /
# "no response" — so no voice note for any of them). This was the dominant cause
# of "long summaries never reach Telegram" once synthesis was detached: parallel
# sessions (overseer + forecast) collide constantly. Serialize ALL synthesis
# through one lock so overlapping turns queue (~25s each) instead of crashing.
_synth_lock = threading.Lock()


def synth_to_wav(text: str, voice: str = VOICE) -> str:
    import numpy as np
    import soundfile as sf

    with _synth_lock:
        model = get_model()
        chunks = []
        sr = None
        for r in model.generate(text, voice=voice, lang_code=LANG):
            # r.audio is a LAZY mlx array — the GPU work is deferred until
            # something reads its buffer. np.asarray() forces that eval NOW,
            # while we still hold _synth_lock. If we defer it to the
            # np.concatenate() below (outside the lock), two concurrent
            # requests run Metal command buffers at once and abort the whole
            # process (Gather::eval_gpu Metal-encoder assertion). The lock
            # only protected model.generate(); the eval leaked past it. Pull
            # the eval inside the lock so ALL GPU work is serialized.
            chunks.append(np.asarray(r.audio))
            sr = r.sample_rate
    if not chunks:
        raise RuntimeError("no audio generated")
    audio = np.concatenate(chunks)
    fd, path = tempfile.mkstemp(prefix="codevoice_", suffix=".wav")
    os.close(fd)
    sf.write(path, audio, sr)
    return path


def synth_to_mp3_bytes(text: str, voice: str = VOICE) -> bytes:
    """Synthesize -> mp3 bytes (for the OpenAI-compatible /v1/audio/speech route)."""
    wav = synth_to_wav(text, voice=voice)
    mp3 = wav[:-4] + ".mp3"
    try:
        subprocess.run(
            [FFMPEG, "-y", "-i", wav, "-c:a", "libmp3lame", "-b:a", "128k", mp3],
            capture_output=True, check=True,
        )
        with open(mp3, "rb") as f:
            return f.read()
    finally:
        for p in (wav, mp3):
            try:
                os.unlink(p)
            except OSError:
                pass


def worker():
    """Single playback worker — guarantees no overlapping audio."""
    while True:
        raw = _jobs.get()
        if raw is None:
            return
        try:
            spoken = summarize(raw)
            spoken = spoken.strip()
            if not spoken:
                continue
            log(f"speaking ({len(spoken)} chars): {spoken[:120]!r}")
            wav = synth_to_wav(spoken)
            try:
                subprocess.run(["afplay", wav], check=False)
            finally:
                try:
                    os.unlink(wav)
                except OSError:
                    pass
        except Exception as e:  # noqa: BLE001
            log(f"worker error: {e}")
        finally:
            _jobs.task_done()


def warmup():
    global _warm
    try:
        get_model()
        # tiny synth to trigger first-call warmup cost now, not on first turn
        synth_to_wav("Code voice is ready.")
        _warm = True
        log("warmup complete — synthesis path is hot")
    except Exception as e:  # noqa: BLE001
        log(f"warmup failed: {e}")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # silence default stderr spam
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
            self._json(200, {"ok": True, "warm": _warm, "queue": _jobs.qsize()})
        else:
            self._json(404, {"error": "not found"})

    def _audio(self, code, data: bytes, ctype="audio/mpeg"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        # OpenAI-compatible TTS endpoint (ccgram / any OpenAI-TTS client points here).
        # Returns mp3 bytes for {"input": ..., "voice": ...}. Synchronous (caller
        # wants the audio back), reuses the warm Kokoro model.
        if self.path in ("/v1/audio/speech", "/audio/speech"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(length) or b"{}")
                text = strip_markdown(data.get("input", "") or data.get("text", ""))
                voice = data.get("voice") or VOICE
                if voice not in ("af_heart", "bm_daniel"):
                    voice = VOICE  # ignore OpenAI voice names (alloy/nova/...)
                if not text:
                    self._json(400, {"error": "empty input"})
                    return
                log(f"/v1/audio/speech voice={voice} ({len(text)} chars)")
                self._audio(200, synth_to_mp3_bytes(text, voice=voice))
            except Exception as e:  # noqa: BLE001
                log(f"/v1/audio/speech error: {e}")
                self._json(500, {"error": str(e)})
            return

        if self.path != "/speak":
            self._json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
        except Exception as e:  # noqa: BLE001
            self._json(400, {"error": f"bad request: {e}"})
            return
        text = strip_markdown(data.get("text", ""))
        if not text:
            self._json(200, {"queued": False, "reason": "empty after cleaning"})
            return
        # Drop oldest if backlog builds up (stale turns shouldn't pile up).
        while _jobs.qsize() >= MAX_QUEUE:
            try:
                _jobs.get_nowait()
                _jobs.task_done()
            except queue.Empty:
                break
        _jobs.put(text)
        self._json(200, {"queued": True, "queue": _jobs.qsize()})


def main():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    log(f"Code Voice server starting on {HOST}:{PORT}")
    threading.Thread(target=worker, daemon=True).start()
    # Warm up the model BEFORE opening the HTTP port. mlx Kokoro is not
    # thread-safe; if we accept requests while warmup is still loading the
    # model on the GPU, the in-flight synthesis and the warmup load run two
    # Metal command buffers at once and abort the whole process (launchd then
    # restarts it and the same flood of retried requests crashes it again —
    # the startup crash-loop). Loading synchronously means every request that
    # gets through finds the model already resident and serializes cleanly on
    # _synth_lock. Clients hitting the ~5s load window get connection-refused
    # and retry, which is strictly better than a process abort.
    warmup()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
