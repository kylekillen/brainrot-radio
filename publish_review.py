#!/usr/bin/env python3
"""publish_review.py — route a "review artifact" (a build plan/pitch generated
FOR KYLE'S REVIEW) to his PRIVATE podcast feed as audio, idempotently.

Kyle's standing rule (2026-06-25, #fleet-optimizer): anything generated for his
review — build plans, the daily build-pitch, Fleet-Optimizer build slates —
should reach him as AUDIO on his podcast RSS, either auto-routed or one-button
from the dashboard. Reading on a phone in transit is friction; listening on a
walk is not. A pitch that rots unread in a folder is the failure this closes.

This is the REUSABLE primitive any fleet component can call to push a review
artifact to the private "Killen Time — Private Briefings" feed:

    publish_review.py --title "Fleet Build Slate — 2026-06-25" --md-file slate.md

It wraps the proven render_report.py (Kokoro TTS -> mp3 -> publish_private ->
here.now RSS) and adds the two things render_report deliberately lacks:
  * IDEMPOTENCY — a content-hash ledger so re-runs / retries never double-publish
    the same artifact (the daily build-pitch generator calls this every run, and
    generate-episode.sh may run more than once a day).
  * SKIP-ON-EMPTY — an empty or NO_VERIFIED_PITCH artifact produces NO episode
    (we don't narrate "nothing to pitch today").

Fail-loud: a real render/publish error raises / exits NONZERO. Callers that treat
audio as best-effort (so a kokoro outage never blocks pitch generation) should
catch that and continue — the markdown still exists for the dashboard "Send to
podcast" button fallback.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
VENV_PY = BASE / "venv" / "bin" / "python3"
RENDER = BASE / "render_report.py"
DEFAULT_LEDGER = Path(os.path.expanduser("~/.observer/private-feed/.review-published.json"))

NO_PITCH_MARKERS = ("NO_VERIFIED_PITCH",)


def _content_for_hash(text):
    """Normalize whitespace/case so trivial header or formatting churn doesn't
    force a re-publish, but a real content change does."""
    return re.sub(r"\s+", " ", text).strip().lower()


def _is_empty_or_no_pitch(text):
    """True when there's nothing worth narrating: blank, or the first real
    (non-blank, non-heading) line is a NO_VERIFIED_PITCH marker."""
    body = text.strip()
    if not body:
        return True
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        return any(s.startswith(m) for m in NO_PITCH_MARKERS)
    return True


def _load_ledger(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}


def _save_ledger(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    os.replace(tmp, p)  # atomic


def _render_and_publish(title, md_path, description, python_bin=None, render=None):
    """Call render_report.py as a subprocess (keeping the proven daily-podcast
    code path untouched); return the episode mp3 URL. Raises on failure."""
    py = str(python_bin or (VENV_PY if VENV_PY.exists() else sys.executable))
    cmd = [py, str(render or RENDER), "--title", title, "--text-file", str(md_path)]
    if description:
        cmd += ["--description", description]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"render_report failed (exit {proc.returncode}): {proc.stderr.strip()[-500:]}"
        )
    url = None
    for line in proc.stdout.splitlines():
        if line.startswith("EPISODE_URL:"):
            url = line.split("EPISODE_URL:", 1)[1].strip()
    if not url:
        raise RuntimeError(
            f"render_report produced no EPISODE_URL; stdout tail: {proc.stdout.strip()[-300:]}"
        )
    return url


def publish_review(title, md_path, description=None, ledger_path=DEFAULT_LEDGER,
                   force=False, source=None, python_bin=None, render=None):
    """Idempotently publish a review-artifact markdown file to the private feed.

    Returns {"state": "published"|"skipped-duplicate"|"skipped-empty",
             "url": <url or None>, "sha": <hash or None>}.
    Raises RuntimeError on a real render/publish failure (fail loud).
    """
    md_path = Path(md_path)
    text = md_path.read_text(encoding="utf-8")
    if _is_empty_or_no_pitch(text):
        return {"state": "skipped-empty", "url": None, "sha": None}

    sha = hashlib.sha256(_content_for_hash(text).encode("utf-8")).hexdigest()
    ledger = _load_ledger(ledger_path)
    if not force and sha in ledger:
        return {"state": "skipped-duplicate", "url": ledger[sha].get("url"), "sha": sha}

    url = _render_and_publish(title, md_path, description, python_bin=python_bin, render=render)
    ledger[sha] = {
        "title": title,
        "url": url,
        "source": str(source or md_path),
        "ts": int(time.time()),
    }
    _save_ledger(ledger_path, ledger)
    return {"state": "published", "url": url, "sha": sha}


def main_argv(argv=None):
    ap = argparse.ArgumentParser(
        description="Publish a review-artifact markdown to Kyle's private podcast feed (idempotent)."
    )
    ap.add_argument("--title", required=True, help="Episode title")
    ap.add_argument("--md-file", required=True, help="Path to the review-artifact markdown")
    ap.add_argument("--description", help="Episode description")
    ap.add_argument("--ledger", default=str(DEFAULT_LEDGER),
                    help="Idempotency ledger path (default: ~/.observer/private-feed/.review-published.json)")
    ap.add_argument("--force", action="store_true",
                    help="Re-publish even if this content was already published.")
    args = ap.parse_args(argv)
    try:
        result = publish_review(
            args.title, args.md_file, args.description,
            ledger_path=args.ledger, force=args.force,
        )
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if result["state"] == "published":
        print(f"EPISODE_URL: {result['url']}")
    elif result["state"] == "skipped-duplicate":
        print(f"SKIP (already published): {result['url']}", file=sys.stderr)
    else:
        print("SKIP (empty / NO_VERIFIED_PITCH): no episode published", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main_argv())
