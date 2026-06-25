#!/usr/bin/env python3
"""Render an arbitrary-length report -> Kokoro TTS (af_heart/Brooke) -> one mp3
-> publish to Kyle's PRIVATE podcast feed (here.now-hosted, unlisted).

PRIVACY (2026-06-25): report deliveries route to the private feed via
publish_private.py — NOT the world-public Killen Time show (publish.py). Kyle's
standing decision: "use it for all future report deliveries instead of the
public channel so that none of this pollutes that feed." Dispatched reports
(finances, family, etc.) must never land in a directory-listed public feed.

CONTRACT A (journal-dispatch pipeline). Unlike voice.py, this enforces NO word
floor — a two-paragraph report renders and publishes just like a long one.
Reuses the chunking / ensure_kokoro / tts-retry / ffmpeg-concat logic from
~/screenwriting/golden-boy/render_brief.py.

CLI:
  render_report.py --title "<T>" --text-file <PATH> [--description "<D>"]

On success the FINAL stdout line is exactly:
  EPISODE_URL: <https url>
and exit code 0. On any failure (kokoro unreachable, render or publish error)
it exits NONZERO and prints the error to stderr (fail loud — never publish an
empty/placeholder episode).
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime

import requests

# Report deliveries go to Kyle's PRIVATE here.now-hosted feed, NOT the
# world-public Killen Time podcast (publish.py). Both expose the same
# publish(mp3, title, description) -> urls dict interface, so this is a
# drop-in swap. See publish_private.py for the full rationale.
from publish_private import publish

BASE = os.path.dirname(os.path.abspath(__file__))
KOKORO_URL = "http://127.0.0.1:8765/v1/audio/speech"
HEALTH_URL = "http://127.0.0.1:8765/health"
FFMPEG = "/opt/homebrew/bin/ffmpeg"
FFPROBE = "/opt/homebrew/bin/ffprobe"
CHUNK_MIN, CHUNK_MAX = 1500, 2400


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", file=sys.stderr, flush=True)


def clean_text(raw):
    paras = re.split(r"\n\s*\n", raw)
    out = []
    for p in paras:
        p = re.sub(r"\s*\n\s*", " ", p).strip()
        if p:
            out.append(p)
    return out


def chunk(paras, cmin, cmax):
    chunks, buf = [], ""
    for p in paras:
        sents = re.split(r"(?<=[.!?])\s+", p)
        for s in sents:
            s = s.strip()
            if not s:
                continue
            if len(buf) + len(s) + 1 > cmax and len(buf) >= cmin:
                chunks.append(buf.strip())
                buf = s
            else:
                buf = (buf + " " + s).strip()
        if len(buf) >= cmax:
            chunks.append(buf.strip())
            buf = ""
    if buf.strip():
        chunks.append(buf.strip())
    return chunks


def ensure_kokoro():
    for _ in range(30):
        try:
            r = requests.get(HEALTH_URL, timeout=5)
            if r.ok and r.json().get("ok"):
                return True
        except Exception:
            pass
        time.sleep(8)
    return False


def tts(text, out_path):
    for attempt in range(6):
        try:
            r = requests.post(
                KOKORO_URL,
                json={"model": "kokoro", "voice": "af_heart", "input": text},
                timeout=300,
            )
            if r.ok and r.content and len(r.content) > 500:
                with open(out_path, "wb") as f:
                    f.write(r.content)
                return True
            log(f"  bad resp status={r.status_code} bytes={len(r.content)} retry {attempt+1}")
        except Exception as e:
            log(f"  err {e} retry {attempt+1}")
        ensure_kokoro()
        time.sleep(8)
    return False


def render(text, out_mp3, workdir):
    """Render text -> out_mp3. Raises RuntimeError on any failure (fail loud)."""
    if not ensure_kokoro():
        raise RuntimeError("kokoro unavailable (health check failed)")
    paras = clean_text(text)
    chunks = chunk(paras, CHUNK_MIN, CHUNK_MAX)
    if not chunks:
        raise RuntimeError("no renderable text in input (empty after cleaning)")
    log(f"{sum(len(p.split()) for p in paras)} words -> {len(chunks)} chunks")
    cdir = os.path.join(workdir, "chunks")
    os.makedirs(cdir, exist_ok=True)
    files = []
    for i, c in enumerate(chunks):
        cp = os.path.join(cdir, f"chunk_{i:03d}.mp3")
        log(f"chunk {i+1}/{len(chunks)} ({len(c)} chars)")
        if not tts(c, cp):
            raise RuntimeError(f"kokoro TTS failed on chunk {i}")
        files.append(cp)
    lst = os.path.join(workdir, "concat.list.txt")
    with open(lst, "w") as f:
        for cf in files:
            f.write(f"file '{cf}'\n")
    subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out_mp3],
        check=True, capture_output=True,
    )
    if not (os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 500):
        raise RuntimeError("ffmpeg concat produced no usable mp3")
    try:
        r = subprocess.run(
            [FFPROBE, "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", out_mp3],
            capture_output=True, text=True,
        )
        dur = float(r.stdout.strip() or 0)
        log(f"DONE -> {out_mp3} ({dur/60:.1f} min)")
    except Exception:
        pass
    return out_mp3


def main_argv(argv=None):
    ap = argparse.ArgumentParser(description="Render+publish an arbitrary-length report episode")
    ap.add_argument("--title", required=True, help="Episode title")
    ap.add_argument("--text-file", required=True, help="Path to UTF-8 text/markdown to render")
    ap.add_argument("--description", help="Episode description")
    args = ap.parse_args(argv)

    try:
        with open(args.text_file, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"ERROR: cannot read --text-file: {e}", file=sys.stderr)
        return 1
    if not text.strip():
        print("ERROR: --text-file is empty", file=sys.stderr)
        return 1

    # killen-time-<YYYY-MM-DD>.mp3 (today, MT) so publish.py's parse_episode_tag
    # accepts it; publish auto-increments the episode number itself.
    date_str = datetime.now().strftime("%Y-%m-%d")
    mp3_name = f"killen-time-{date_str}.mp3"

    with tempfile.TemporaryDirectory(prefix="render_report_") as workdir:
        out_mp3 = os.path.join(workdir, mp3_name)
        try:
            render(text, out_mp3, workdir)
        except Exception as e:
            print(f"ERROR: render failed: {e}", file=sys.stderr)
            return 1
        try:
            urls = publish(out_mp3, args.title, args.description)
        except Exception as e:
            print(f"ERROR: publish failed: {e}", file=sys.stderr)
            return 1
        if not urls or not urls.get("mp3"):
            print("ERROR: publish returned no mp3 url", file=sys.stderr)
            return 1
        print(f"EPISODE_URL: {urls['mp3']}")
        return 0


if __name__ == "__main__":
    sys.exit(main_argv())
