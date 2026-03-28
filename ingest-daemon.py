#!/usr/bin/env python3
"""Killen Time — Continuous Feed Ingestion Daemon.

Runs on a separate launchd schedule (every 30 min) to pre-cache podcast
transcripts and Substack articles. By the time generate-episode.sh fires,
sources are already downloaded, transcribed, and waiting in .tmp/.

This script ONLY fetches and caches — it does NOT score, rank, or produce
a topic brief. That's still done by ingest.py at episode build time.

Usage:
    python3 ingest-daemon.py           # Run one ingestion cycle
    python3 ingest-daemon.py --status  # Show cache stats
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

BRAINROT_DIR = Path(__file__).parent
TEMP_DIR = BRAINROT_DIR / ".tmp"
LOG_FILE = BRAINROT_DIR / "logs" / "ingest-daemon.log"


def log(msg):
    """Append timestamped message to log file and stderr."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, file=sys.stderr)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def count_cached():
    """Return counts of cached transcripts and articles."""
    transcripts = list((TEMP_DIR / "transcripts").glob("*.txt")) if (TEMP_DIR / "transcripts").exists() else []
    articles = list((TEMP_DIR / "articles").glob("*.txt")) if (TEMP_DIR / "articles").exists() else []
    used = list((TEMP_DIR / "used").glob("*.txt")) if (TEMP_DIR / "used").exists() else []
    return len(transcripts), len(articles), len(used)


def run_ingest():
    """Fetch podcasts and Substack articles, caching transcripts locally."""
    log("Ingest daemon starting...")

    t_before, a_before, _ = count_cached()

    # Podcasts — downloads audio + transcribes via Whisper if no RSS/web transcript
    # Results cached to .tmp/transcripts/podcast_GUID.txt
    pod_count = 0
    try:
        from podcast import fetch_podcast_articles
        pod_articles = fetch_podcast_articles()
        pod_count = sum(1 for a in pod_articles if a.get("_has_transcript"))
        log(f"  Podcasts: {len(pod_articles)} episodes checked, {pod_count} with transcripts")
    except Exception as e:
        log(f"  [ERROR] Podcast fetch failed: {e}")

    # Substack — fetches full article text
    # Results cached to .tmp/articles/SLUG.txt
    sub_count = 0
    try:
        from substack import fetch_all_substack_articles
        sub_articles = fetch_all_substack_articles()
        sub_count = sum(1 for a in sub_articles if a.get("_has_full_text"))
        log(f"  Substack: {len(sub_articles)} articles checked, {sub_count} with full text")
    except Exception as e:
        log(f"  [ERROR] Substack fetch failed: {e}")

    # YouTube — fetches transcripts via yt-dlp
    yt_count = 0
    try:
        from youtube import fetch_youtube_articles
        yt_articles = fetch_youtube_articles()
        yt_count = len(yt_articles)
        log(f"  YouTube: {yt_count} articles fetched")
    except Exception as e:
        log(f"  [ERROR] YouTube fetch failed: {e}")

    t_after, a_after, used = count_cached()
    new_transcripts = t_after - t_before
    new_articles = a_after - a_before

    log(f"  Done. New: {new_transcripts} transcripts, {new_articles} articles. "
        f"Cache: {t_after} transcripts, {a_after} articles, {used} used/archived.")


def show_status():
    """Print cache statistics."""
    t, a, u = count_cached()
    print(f"Cached transcripts: {t}")
    print(f"Cached articles:    {a}")
    print(f"Archived (used):    {u}")

    # Show last daemon run
    if LOG_FILE.exists():
        lines = LOG_FILE.read_text().strip().split("\n")
        last_lines = [l for l in lines if "Ingest daemon starting" in l]
        if last_lines:
            print(f"Last daemon run:    {last_lines[-1][:21]}")


def main():
    parser = argparse.ArgumentParser(description="Killen Time Continuous Ingest Daemon")
    parser.add_argument("--status", action="store_true", help="Show cache stats")
    args = parser.parse_args()

    if args.status:
        show_status()
    else:
        run_ingest()


if __name__ == "__main__":
    main()
