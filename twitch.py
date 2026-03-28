#!/usr/bin/env python3
"""Brainrot Radio v0.2 — Twitch VOD Transcript Pipeline.

Downloads recent Twitch VOD audio via yt-dlp, transcribes with mlx-whisper,
and returns articles in ingest.py format.

Usage:
    python3 twitch.py                       # Fetch all Twitch channels
    python3 twitch.py --channel locksy      # Fetch one channel
    python3 twitch.py --json                # Output raw JSON
    python3 twitch.py --hours 72            # Custom lookback
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config import FEEDS_JSON, TEMP_DIR, PROJECT_DIR
from transcribe import cached_transcribe

# ── Constants ─────────────────────────────────────────────────────
YTDLP = str(PROJECT_DIR / "venv" / "bin" / "yt-dlp")
DEFAULT_LOOKBACK_HOURS = 48
DEFAULT_MAX_VODS = 2
DEFAULT_MAX_AUDIO_MINUTES = 30
TRANSCRIPT_SUMMARY_CHARS = 4000
TWITCH_CACHE_DIR = TEMP_DIR / "twitch"


def load_twitch_config():
    """Load Twitch channel configs from feeds.json.

    Looks in "twitch_channels" section and youtube_channels with platform="twitch".
    """
    with open(FEEDS_JSON) as f:
        config = json.load(f)

    channels = []

    # Dedicated twitch_channels section
    if "twitch_channels" in config:
        channels.extend(config["twitch_channels"])

    # Also check youtube_channels for platform="twitch"
    for ch in config.get("youtube_channels", []):
        if ch.get("platform") == "twitch":
            if not any(c.get("id") == ch.get("id") for c in channels):
                channels.append(ch)

    return channels, config.get("topic_weights", {})


def fetch_recent_vods(channel_name, lookback_hours=DEFAULT_LOOKBACK_HOURS,
                      max_vods=DEFAULT_MAX_VODS):
    """Fetch recent VOD metadata from a Twitch channel using yt-dlp.

    Returns list of dicts: {vod_id, title, published, url, duration}
    """
    channel_url = f"https://www.twitch.tv/{channel_name}/videos?filter=archives"
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    cmd = [
        YTDLP,
        "--flat-playlist",
        "--dump-json",
        "--no-warnings",
        "--playlist-end", str(max_vods + 2),  # Fetch a few extra for date filtering
        channel_url,
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        print(f"  [WARN] yt-dlp timeout for {channel_name}", file=sys.stderr)
        return []

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if stderr:
            print(f"  [WARN] yt-dlp error for {channel_name}: {stderr[:200]}", file=sys.stderr)
        return []

    vods = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        vod_id = entry.get("id", "")
        title = entry.get("title", "")
        upload_date = entry.get("upload_date", "")  # YYYYMMDD format
        url = entry.get("url") or entry.get("webpage_url") or f"https://www.twitch.tv/videos/{vod_id}"
        duration = entry.get("duration")

        # Parse upload_date
        pub_dt = None
        if upload_date and len(upload_date) == 8:
            try:
                pub_dt = datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        # Also try timestamp field
        if not pub_dt and entry.get("timestamp"):
            try:
                pub_dt = datetime.fromtimestamp(entry["timestamp"], tz=timezone.utc)
            except (ValueError, OSError):
                pass

        if pub_dt and pub_dt < cutoff:
            continue

        vods.append({
            "vod_id": vod_id,
            "title": title,
            "published": pub_dt.isoformat() if pub_dt else upload_date,
            "url": url,
            "duration": duration,
        })

        if len(vods) >= max_vods:
            break

    return vods


def download_vod_audio(vod_url, vod_id, max_minutes=DEFAULT_MAX_AUDIO_MINUTES):
    """Download Twitch VOD audio (first N minutes) using yt-dlp.

    Returns path to downloaded MP3 or None.
    """
    TWITCH_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    safe_id = re.sub(r"[^\w-]", "", vod_id)
    filepath = TWITCH_CACHE_DIR / f"{safe_id}.mp3"

    if filepath.exists() and filepath.stat().st_size > 1000:
        print(f"  Cache hit: {filepath.name}", file=sys.stderr)
        return filepath

    # Download section: first N minutes
    duration_secs = max_minutes * 60

    cmd = [
        YTDLP,
        "-x",                                    # Extract audio
        "--audio-format", "mp3",
        "--audio-quality", "5",                   # Lower quality = smaller
        "--download-sections", f"*0-{duration_secs}",
        "--no-warnings",
        "-o", str(filepath),
        vod_url,
    ]

    print(f"  Downloading VOD audio ({max_minutes}min)...", file=sys.stderr)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired:
        print(f"  [WARN] yt-dlp download timeout for {vod_id}", file=sys.stderr)
        return None

    if result.returncode != 0:
        print(f"  [WARN] VOD download failed: {result.stderr[:200]}", file=sys.stderr)
        return None

    # yt-dlp may append format suffix, find the actual file
    if filepath.exists():
        print(f"  → Downloaded {filepath.stat().st_size / (1024*1024):.1f} MB", file=sys.stderr)
        return filepath

    # Check for file with slightly different name
    for candidate in TWITCH_CACHE_DIR.glob(f"{safe_id}*"):
        if candidate.stat().st_size > 1000:
            print(f"  → Downloaded {candidate.stat().st_size / (1024*1024):.1f} MB ({candidate.name})", file=sys.stderr)
            return candidate

    print(f"  [WARN] Download produced no audio file", file=sys.stderr)
    return None


def transcribe_vod(mp3_path, vod_id):
    """Transcribe a Twitch VOD. Returns transcript text."""
    cache_key = f"twitch_{re.sub(r'[^\\w-]', '', vod_id)}"
    return cached_transcribe(mp3_path, cache_key=cache_key)


def fetch_twitch_articles(lookback_hours=DEFAULT_LOOKBACK_HOURS):
    """Fetch all Twitch channels and return articles in ingest.py format.

    Returns list of dicts with standard article fields plus metadata.
    """
    channels, topic_weights = load_twitch_config()
    if not channels:
        return []

    all_articles = []

    for ch in channels:
        ch_id = ch.get("id", "unknown")
        ch_name = ch.get("name", ch_id)
        channel_handle = ch.get("channel", "").lstrip("@")
        topic = ch.get("topic", "general")
        weight = ch.get("weight", 1.0)
        max_vods = ch.get("max_vods", DEFAULT_MAX_VODS)
        max_mins = ch.get("max_audio_minutes", DEFAULT_MAX_AUDIO_MINUTES)

        if not channel_handle:
            print(f"  [WARN] No channel handle for '{ch_name}', skipping", file=sys.stderr)
            continue

        print(f"  Fetching Twitch: {ch_name} ({channel_handle}) [{topic}]...", file=sys.stderr)
        vods = fetch_recent_vods(channel_handle, lookback_hours, max_vods)
        print(f"    → {len(vods)} recent VODs", file=sys.stderr)

        for vod in vods:
            transcript = None

            # Download and transcribe
            mp3_path = download_vod_audio(vod["url"], vod["vod_id"], max_mins)
            if mp3_path:
                transcript = transcribe_vod(mp3_path, vod["vod_id"])

            content = transcript[:TRANSCRIPT_SUMMARY_CHARS] if transcript else f"[Twitch VOD — no transcript] {vod['title']}"

            all_articles.append({
                "title": f"[Twitch] {vod['title']}",
                "updated": vod["published"],
                "link": vod["url"],
                "content": content,
                "_source_id": ch_id,
                "_source_name": ch_name,
                "_topic": topic,
                "_weight": weight,
                "_type": "twitch",
                "_has_transcript": bool(transcript),
                "_full_transcript": transcript,
            })

    return all_articles


def main():
    parser = argparse.ArgumentParser(description="Brainrot Radio — Twitch VOD Pipeline")
    parser.add_argument("--channel", help="Fetch only this channel handle")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--hours", type=int, default=DEFAULT_LOOKBACK_HOURS,
                        help=f"Lookback window (default: {DEFAULT_LOOKBACK_HOURS}h)")
    parser.add_argument("--list-only", action="store_true",
                        help="List VODs without downloading/transcribing")
    args = parser.parse_args()

    if args.list_only:
        channels, _ = load_twitch_config()
        for ch in channels:
            handle = ch.get("channel", "").lstrip("@")
            if args.channel and handle != args.channel:
                continue
            print(f"\n{'='*60}")
            print(f" {ch.get('name', handle)} (@{handle})")
            print(f"{'='*60}")
            vods = fetch_recent_vods(handle, args.hours)
            for vod in vods:
                dur = f"{vod['duration']//60}min" if vod.get("duration") else "?"
                print(f"  [{dur}] {vod['title']}")
                print(f"         Published: {vod['published']}")
                print(f"         URL: {vod['url']}")
        return

    articles = fetch_twitch_articles(lookback_hours=args.hours)

    if args.channel:
        articles = [a for a in articles
                    if args.channel in a.get("_source_name", "").lower()
                    or args.channel in a.get("link", "")]

    if args.json:
        for a in articles:
            a.pop("_full_transcript", None)
        print(json.dumps(articles, indent=2))
    else:
        if not articles:
            print("No recent Twitch VODs found.")
            return

        print(f"\n{'='*70}")
        print(f" Twitch VOD Pipeline — {len(articles)} VODs")
        print(f"{'='*70}\n")

        for i, a in enumerate(articles, 1):
            has_tx = "TRANSCRIBED" if a.get("_has_transcript") else "NO TRANSCRIPT"
            print(f"## {i}. {a['title']}")
            print(f"   Source: {a.get('_source_name')} | Topic: {a.get('_topic')}")
            print(f"   Published: {a['updated']}")
            print(f"   Status: {has_tx}")
            print()
            snippet = a["content"][:500]
            if len(a["content"]) > 500:
                snippet += "..."
            print(f"   {snippet}")
            print(f"\n{'─'*70}\n")


if __name__ == "__main__":
    main()
