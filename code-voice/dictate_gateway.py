#!/usr/bin/env python3
"""Dictate gateway — Kyle's phone dictation, on our own Parakeet.

One small, stdlib-only server that the phone talks to (over Tailscale HTTPS via
``tailscale serve --set-path /dictate``). It gives two things Wispr Flow gives,
without a subscription or a word cap:

* ``POST /v1/audio/transcriptions`` — OpenAI-compatible. Audio goes to the
  resident Parakeet STT server (:8766), then through a short local cleanup pass
  (ollama; fillers out, punctuation in, "no wait, I mean X" applied). The
  Android *Dictate* keyboard points its "own server" setting here. ``?raw=1``
  (or form field ``raw=1``) skips the cleanup.
* ``GET /`` — a one-button long-form recorder page (record → transcribe →
  copy), with a history of everything dictated so nothing is ever lost.

Also ``POST /v1/chat/completions`` (OpenAI-shaped, answered by the local model,
for the keyboard's optional "rewording" feature) and ``GET /history``.

Cleanup never blocks the words: if the local model is cold, slow, or down, the
raw transcript is returned (and the model is warmed in the background).
Everything dictated is appended to ~/.observer/dictation/history.jsonl.

Run via LaunchAgent com.codevoice.dictate. Binds 127.0.0.1 only — the tailnet
reaches it solely through ``tailscale serve``.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HOST = "127.0.0.1"
PORT = int(os.environ.get("DICTATE_PORT", "8767"))
STT_URL = os.environ.get("DICTATE_STT_URL", "http://127.0.0.1:8766/v1/audio/transcriptions")
OLLAMA = os.environ.get("DICTATE_OLLAMA", "http://127.0.0.1:11434")
CLEAN_MODEL = os.environ.get("DICTATE_CLEAN_MODEL", "qwen3.6:35b-a3b")
KEEP_ALIVE = os.environ.get("DICTATE_KEEP_ALIVE", "2h")
DATA = Path(os.environ.get("DICTATE_DATA", str(Path.home() / ".observer" / "dictation")))
HISTORY = DATA / "history.jsonl"
LOG = Path(__file__).resolve().parent / "dictate_gateway.log"

CHUNK_WORDS = 220          # long-form cleanup works paragraph by paragraph
CHUNK_TIMEOUT = 25         # seconds per chunk before we keep the raw chunk
MAX_UPLOAD = 200 * 1024 * 1024

CLEAN_SYSTEM = (
    "You clean up dictated speech into written text. Remove filler words (um, uh, "
    "like, you know, I mean) and false starts, fix punctuation, capitalization and "
    "paragraphing, and apply spoken self-corrections (\"Thursday, no wait, Friday\" "
    "becomes \"Friday\"). Keep the speaker's own words, order and voice. Never "
    "summarize, shorten meaning, add content, or answer questions in the text. "
    "Output only the cleaned text."
)
FEW_SHOT = [
    ("okay so uh send the draft to Alyssa tomorrow and um tell her the call can move "
     "to Thursday no wait Friday",
     "Send the draft to Alyssa tomorrow and tell her the call can move to Friday."),
]

_lock = threading.Lock()


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}\n"
    try:
        with open(LOG, "a") as f:
            f.write(line)
    except OSError:
        pass


def _post_json(url: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _model_loaded() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/ps", timeout=2) as r:
            return any(m.get("name") == CLEAN_MODEL or m.get("model") == CLEAN_MODEL
                       for m in json.loads(r.read()).get("models", []))
    except Exception:  # noqa: BLE001
        return False


def warm_model() -> None:
    try:
        _post_json(f"{OLLAMA}/api/generate",
                   {"model": CLEAN_MODEL, "prompt": "", "keep_alive": KEEP_ALIVE}, 120)
        log(f"cleanup model warmed: {CLEAN_MODEL}")
    except Exception as e:  # noqa: BLE001
        log(f"warm failed: {e}")


_THINK = re.compile(r"<think>.*?</think>", re.S)


def _chat(messages: list[dict], timeout: float, temperature: float = 0.0) -> str:
    out = _post_json(f"{OLLAMA}/api/chat", {
        "model": CLEAN_MODEL, "messages": messages, "stream": False, "think": False,
        "keep_alive": KEEP_ALIVE, "options": {"temperature": temperature},
    }, timeout)
    text = out.get("message", {}).get("content", "")
    return _THINK.sub("", text).split("</think>")[-1].strip()


def _chunks(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks, cur = [], []
    for s in sentences:
        cur.append(s)
        if sum(len(x.split()) for x in cur) >= CHUNK_WORDS:
            chunks.append(" ".join(cur))
            cur = []
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def clean_text(raw: str, *, allow_cold: bool) -> tuple[str, str]:
    """(text, status). status: clean | raw-cold | raw-error | raw-empty."""
    if not raw.strip():
        return raw, "raw-empty"
    if not allow_cold and not _model_loaded():
        threading.Thread(target=warm_model, daemon=True).start()
        return raw, "raw-cold"
    msgs = [{"role": "system", "content": CLEAN_SYSTEM}]
    for q, a in FEW_SHOT:
        msgs += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
    out, failed = [], 0
    for chunk in _chunks(raw):
        try:
            cleaned = _chat(msgs + [{"role": "user", "content": chunk + " /no_think"}],
                            timeout=CHUNK_TIMEOUT if allow_cold or out else 8)
            # A cleanup that shrinks the text by more than half has summarized, not cleaned.
            if not cleaned or len(cleaned.split()) < 0.5 * len(chunk.split()):
                raise ValueError("cleanup dropped too much text")
            out.append(cleaned)
        except Exception as e:  # noqa: BLE001
            log(f"cleanup chunk failed ({e}); keeping raw")
            out.append(chunk)
            failed += 1
    return "\n\n".join(out), ("clean" if not failed else "raw-error" if failed == len(out) else "partial")


def record(entry: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    with _lock, open(HISTORY, "a") as f:
        f.write(json.dumps(entry) + "\n")


def history(limit: int = 50) -> list[dict]:
    try:
        lines = HISTORY.read_text().splitlines()[-limit:]
    except OSError:
        return []
    return [json.loads(x) for x in reversed(lines) if x.strip()]


def _form_field(body: bytes, ctype: str, name: str) -> str | None:
    m = re.search(rb'name="' + name.encode() + rb'"\r\n\r\n([^\r]*)\r\n', body)
    return m.group(1).decode(errors="replace") if m else None


PAGE = (Path(__file__).resolve().parent / "dictate_page.html")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _path(self) -> str:
        p = urlparse(self.path).path
        return p[len("/dictate"):] or "/" if p.startswith("/dictate") else p

    def do_GET(self):
        p = self._path()
        if p in ("/", "/index.html"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif p == "/health":
            self._json(200, {"ok": True, "clean_model": CLEAN_MODEL,
                             "clean_model_loaded": _model_loaded()})
        elif p == "/history":
            self._json(200, history())
        elif p in ("/v1/models", "/models"):
            self._json(200, {"object": "list", "data": [
                {"id": "whisper-1", "object": "model"},
                {"id": "parakeet", "object": "model"},
                {"id": CLEAN_MODEL, "object": "model"}]})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        p = self._path()
        if p in ("/v1/audio/transcriptions", "/audio/transcriptions"):
            return self._transcribe()
        if p in ("/v1/chat/completions", "/chat/completions"):
            return self._chat_completions()
        self._json(404, {"error": "not found"})

    def _transcribe(self):
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0 or length > MAX_UPLOAD:
            return self._json(400, {"error": f"bad upload size {length}"})
        body = self.rfile.read(length)
        ctype = self.headers.get("Content-Type", "")
        qs = parse_qs(urlparse(self.path).query)
        raw_only = (qs.get("raw", ["0"])[0] == "1") or _form_field(body, ctype, "raw") == "1"
        source = qs.get("source", [None])[0] or _form_field(body, ctype, "source") or "keyboard"
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(STT_URL, data=body, headers={"Content-Type": ctype})
            with urllib.request.urlopen(req, timeout=600) as r:
                raw = json.loads(r.read()).get("text", "")
        except Exception as e:  # noqa: BLE001
            DATA.mkdir(parents=True, exist_ok=True)
            keep = DATA / f"failed-{int(time.time())}.bin"
            keep.write_bytes(body)
            log(f"STT failed: {e}; upload kept at {keep}")
            return self._json(502, {"error": f"transcription failed: {e}", "audio_saved": str(keep)})
        t_stt = time.perf_counter() - t0
        if raw_only:
            text, status = raw, "raw-requested"
        else:
            text, status = clean_text(raw, allow_cold=(source == "page"))
        secs = time.perf_counter() - t0
        record({"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source": source, "status": status, "raw": raw, "text": text,
                "stt_s": round(t_stt, 2), "total_s": round(secs, 2)})
        log(f"{source}: {len(raw.split())} words stt={t_stt:.1f}s total={secs:.1f}s {status}")
        self._json(200, {"text": text, "raw": raw, "cleanup": status})

    def _chat_completions(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
            text = _chat(req.get("messages", []), timeout=60,
                         temperature=float(req.get("temperature", 0.2)))
        except Exception as e:  # noqa: BLE001
            return self._json(502, {"error": {"message": f"local model failed: {e}"}})
        self._json(200, {
            "id": f"chatcmpl-{int(time.time()*1000)}", "object": "chat.completion",
            "created": int(time.time()), "model": CLEAN_MODEL,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": text}}],
        })


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    log(f"dictate gateway starting on {HOST}:{PORT} (stt={STT_URL}, clean={CLEAN_MODEL})")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
