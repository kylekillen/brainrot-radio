#!/usr/bin/env python3
"""Latency check for the dictation path: upload a synthetic Chrome-style webm/opus
clip the way the phone page does, N times, optionally while the big shared model
is busy with fleet-style work, and print the end-to-end seconds for each run.

    python3 code-voice/bench_dictate.py [--url URL] [--runs 5] [--load 3]
"""
import argparse
import json
import subprocess
import tempfile
import threading
import time
import urllib.request
import uuid

TEXT = ("Um, so I was thinking that the second act needs a midpoint reversal where, like, "
        "Dana finds out the letters were never real. And uh, we should send the draft to "
        "Alyssa on Thursday, no wait, Friday. You know, it should feel earned.")


def make_clip() -> bytes:
    d = tempfile.mkdtemp()
    subprocess.run(["say", "-v", "Samantha", "-o", f"{d}/t.aiff", TEXT], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{d}/t.aiff", "-c:a", "libopus",
                    "-b:a", "32k", "-ar", "48000", f"{d}/t.webm"], check=True)
    return open(f"{d}/t.webm", "rb").read()


def upload(url: str, audio: bytes) -> tuple[float, dict]:
    b = uuid.uuid4().hex
    body = (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="dictation.webm"\r\n'
            f'Content-Type: audio/webm\r\n\r\n').encode() + audio + (
            f'\r\n--{b}\r\nContent-Disposition: form-data; name="source"\r\n\r\npage\r\n--{b}--\r\n').encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.loads(r.read())
    return time.perf_counter() - t0, out


def load_big_model(stop: threading.Event, base: str, model: str) -> None:
    while not stop.is_set():
        try:
            req = urllib.request.Request(f"{base}/api/chat", data=json.dumps({
                "model": model, "stream": False, "think": False,
                "messages": [{"role": "user", "content": "Write a long story about a lighthouse keeper."}],
            }).encode(), headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=120).read()
        except Exception:  # noqa: BLE001
            time.sleep(1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://kyles-mac-mini.tailb7cb3e.ts.net/dictate/v1/audio/transcriptions?source=page")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--load", type=int, default=0, help="concurrent fleet-style requests on the big model")
    ap.add_argument("--big", default="http://127.0.0.1:11434")
    ap.add_argument("--big-model", default="qwen3.6:35b-a3b")
    a = ap.parse_args()
    audio = make_clip()
    stop = threading.Event()
    for _ in range(a.load):
        threading.Thread(target=load_big_model, args=(stop, a.big, a.big_model), daemon=True).start()
    if a.load:
        time.sleep(4)
    times = []
    for i in range(a.runs):
        secs, out = upload(a.url, audio)
        times.append(secs)
        print(f"run {i+1}: {secs:.2f}s cleanup={out.get('cleanup')} text={out.get('text')!r}", flush=True)
    stop.set()
    print(f"max={max(times):.2f}s mean={sum(times)/len(times):.2f}s (load={a.load})")
