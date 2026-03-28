#!/usr/bin/env python3
"""Brainrot Radio v0.1 — Daily AI News Show Generator.

Usage:
    python3 brainrot.py scripts/brainrot-radio-2026-03-02.txt    # Full pipeline from script
    python3 brainrot.py --ingest-only                             # Just fetch & rank stories
    python3 brainrot.py --date 2026-03-02 scripts/test.txt        # Override date
"""

import argparse
import logging
import subprocess
import sys
from datetime import date
from pathlib import Path

from config import LOGS_DIR, OUTPUT_DIR, SCRIPTS_DIR

# ── Logging ────────────────────────────────────────────────────────
LOGS_DIR.mkdir(parents=True, exist_ok=True)
log_file = LOGS_DIR / f"brainrot-{date.today().isoformat()}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("brainrot")


def run_ingest(output_file=None):
    """Run the ingestion pipeline and save the topic brief."""
    from ingest import fetch_all_feeds, format_report

    log.info("Starting RSS ingestion...")
    articles = fetch_all_feeds()
    log.info(f"Fetched and ranked {len(articles)} articles")

    brief = format_report(articles)

    if output_file:
        with open(output_file, "w") as f:
            f.write(brief)
        log.info(f"Topic brief saved to {output_file}")
    else:
        print(brief)

    return articles


def run_voice(script_path):
    """Render the script to audio segments."""
    from voice import render_script

    log.info(f"Rendering script: {script_path}")
    segment_files = render_script(script_path)

    if not segment_files:
        log.error("Voice rendering produced no segments")
        return None

    speech_count = sum(1 for s, _ in segment_files if s != "TRANSITION")
    log.info(f"Rendered {speech_count} audio segments")
    return segment_files


def run_mix(segment_files, output_path, show_date=None):
    """Mix segments into final MP3."""
    from mixer import mix_segments

    log.info(f"Mixing {len(segment_files)} segments...")
    success = mix_segments(segment_files, output_path, show_date)

    if success:
        size_mb = output_path.stat().st_size / (1024 * 1024)
        log.info(f"Final mix: {output_path} ({size_mb:.1f} MB)")
    else:
        log.error("Mixing failed")

    return success


def notify(message):
    """Send Telegram notification via shared mojo_notify module."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path.home() / "mojo-daemon/src"))
        from mojo_notify import notify_system
        notify_system("Killen Time", "Episode Ready", message, emoji="🎙️")
        log.info(f"Telegram notification sent: {message}")
    except Exception as e:
        log.warning(f"Notification failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="Brainrot Radio — Daily AI News Show")
    parser.add_argument("script", nargs="?", help="Path to show script (.txt)")
    parser.add_argument("--ingest-only", action="store_true", help="Only fetch & rank stories")
    parser.add_argument("--date", help="Show date (YYYY-MM-DD)")
    parser.add_argument("--skip-notify", action="store_true", help="Skip push notification")
    args = parser.parse_args()

    show_date = args.date or date.today().isoformat()
    output_path = OUTPUT_DIR / f"brainrot-radio-{show_date}.mp3"

    # Skip if today's episode already exists
    if output_path.exists() and not args.ingest_only:
        log.info(f"Episode already exists: {output_path}")
        print(f"Episode already exists: {output_path}")
        return

    # ── Ingest ─────────────────────────────────────────────────────
    if args.ingest_only:
        brief_path = SCRIPTS_DIR / f"brief-{show_date}.txt"
        SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        run_ingest(brief_path)
        return

    # ── Full Pipeline ──────────────────────────────────────────────
    if not args.script:
        print("Provide a script path, or use --ingest-only for topic brief.", file=sys.stderr)
        sys.exit(1)

    script_path = Path(args.script)
    if not script_path.exists():
        log.error(f"Script not found: {script_path}")
        sys.exit(1)

    # Copy script to scripts/ for archival
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    archive_name = f"brainrot-radio-{show_date}.txt"
    archive_path = SCRIPTS_DIR / archive_name
    if not archive_path.exists():
        archive_path.write_text(script_path.read_text())
        log.info(f"Script archived to {archive_path}")

    # Voice rendering
    segment_files = run_voice(str(script_path))
    if not segment_files:
        sys.exit(1)

    # Mixing
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    success = run_mix(segment_files, output_path, show_date)
    if not success:
        sys.exit(1)

    # Notify
    if not args.skip_notify:
        notify(f"Brainrot Radio {show_date} is ready! ({output_path.stat().st_size // 1024}KB)")

    log.info("Pipeline complete.")
    print(f"\nDone: {output_path}")


if __name__ == "__main__":
    main()
