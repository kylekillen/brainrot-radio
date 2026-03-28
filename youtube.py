#!/usr/bin/env python3
"""Brainrot Radio — YouTube Transcript Pipeline.

Fetches recent videos from YouTube channels listed in feeds.json
(youtube_channels section), pulls auto-generated captions via yt-dlp,
and returns articles in the same format as ingest.py's fetch_feed_raw().

Usage:
    python3 youtube.py              # Print recent videos with transcript snippets
    python3 youtube.py --json       # Output raw JSON
    python3 youtube.py --hours 72   # Look back 72 hours instead of default 48
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

from config import FEEDS_JSON, PROJECT_DIR

# ── Constants ─────────────────────────────────────────────────────
YTDLP = str(PROJECT_DIR / "venv" / "bin" / "yt-dlp")
DEFAULT_LOOKBACK_HOURS = 48
TRANSCRIPT_MAX_CHARS = 2000
TEMP_DIR = PROJECT_DIR / ".tmp" / "youtube"


def load_youtube_channels():
    """Load YouTube channel configs from feeds.json."""
    with open(FEEDS_JSON) as f:
        config = json.load(f)
    return config.get("youtube_channels", [])


def fetch_recent_videos_rss(channel_id, lookback_hours=DEFAULT_LOOKBACK_HOURS):
    """Fetch recent videos from a YouTube channel's RSS feed.

    YouTube exposes an Atom feed at:
      https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID

    Returns list of dicts: {video_id, title, published, link}
    """
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    try:
        req = Request(url, headers={"User-Agent": "BrainrotRadio/0.1"})
        with urlopen(req, timeout=15) as resp:
            data = resp.read().decode("utf-8")

        root = ET.fromstring(data)
        ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}

        videos = []
        for entry in root.findall("atom:entry", ns):
            video_id = entry.findtext("yt:videoId", "", ns).strip()
            title = entry.findtext("atom:title", "", ns).strip()
            published_str = entry.findtext("atom:published", "", ns).strip()

            # Parse published date
            try:
                published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue

            # Filter by recency
            if published < cutoff:
                continue

            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else f"https://www.youtube.com/watch?v={video_id}"

            videos.append({
                "video_id": video_id,
                "title": title,
                "published": published.isoformat(),
                "link": link,
            })

        return videos

    except Exception as e:
        print(f"  [WARN] YouTube RSS fetch failed for {channel_id}: {e}", file=sys.stderr)
        return []


def fetch_transcript(video_id):
    """Pull auto-generated English captions for a video using yt-dlp.

    Downloads VTT subtitle file, parses it, and returns clean text.
    Returns None if no captions available.
    """
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    # Use a temp directory for this video's subtitle files
    with tempfile.TemporaryDirectory(dir=TEMP_DIR) as tmpdir:
        out_template = os.path.join(tmpdir, "%(id)s")

        cmd = [
            YTDLP,
            "--write-auto-sub",
            "--sub-lang", "en",
            "--skip-download",
            "--sub-format", "vtt",
            "--no-warnings",
            "--quiet",
            "-o", out_template,
            f"https://www.youtube.com/watch?v={video_id}",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            print(f"  [WARN] yt-dlp timeout for {video_id}", file=sys.stderr)
            return None

        if result.returncode != 0:
            # Common: no subs available — not an error worth logging loudly
            return None

        # Find the VTT file — yt-dlp names it {id}.en.vtt or similar
        vtt_files = list(Path(tmpdir).glob("*.vtt"))
        if not vtt_files:
            return None

        vtt_text = vtt_files[0].read_text(encoding="utf-8", errors="replace")
        return parse_vtt(vtt_text)


def parse_vtt(vtt_text):
    """Parse WebVTT captions into clean deduplicated text.

    YouTube auto-subs use rolling captions where each cue repeats the
    previous line plus adds a new one. This deduplicates those overlaps.
    """
    lines = vtt_text.split("\n")
    seen_lines = []
    prev_text = ""

    for line in lines:
        line = line.strip()

        # Skip VTT headers, timestamps, cue markers, and blank lines
        if not line:
            continue
        if line.startswith("WEBVTT"):
            continue
        if line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if line.startswith("NOTE"):
            continue
        # Skip timestamp lines: 00:00:01.234 --> 00:00:04.567
        if re.match(r"\d{2}:\d{2}:\d{2}\.\d{3}\s*-->", line):
            continue
        # Skip numeric cue identifiers
        if re.match(r"^\d+$", line):
            continue

        # Strip VTT formatting tags: <c>, </c>, <00:00:01.234>, etc.
        clean = re.sub(r"<[^>]+>", "", line)
        # Strip alignment/position tags
        clean = re.sub(r"align:start position:\d+%", "", clean)
        clean = clean.strip()

        if not clean:
            continue

        # Deduplicate: YouTube rolling captions repeat lines
        # Only add if this line isn't a substring of or identical to previous
        if clean == prev_text:
            continue
        if clean in prev_text:
            continue

        # Check if this is a rolling extension (previous line + new content)
        # In that case, just keep the new portion
        if prev_text and clean.startswith(prev_text):
            new_part = clean[len(prev_text):].strip()
            if new_part:
                seen_lines.append(new_part)
                prev_text = clean
            continue

        seen_lines.append(clean)
        prev_text = clean

    text = " ".join(seen_lines)
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text if text else None


def fetch_youtube_articles(lookback_hours=DEFAULT_LOOKBACK_HOURS):
    """Fetch all YouTube channels and return articles in ingest.py format.

    Returns list of dicts matching fetch_feed_raw() output:
        {title, updated, link, content}
    """
    channels = load_youtube_channels()
    if not channels:
        return []

    all_articles = []

    for ch in channels:
        channel_id = ch.get("channel_id")
        channel_handle = ch.get("channel")
        name = ch.get("name", channel_handle or channel_id)

        if not channel_id:
            print(f"  [WARN] No channel_id for YouTube channel '{name}', skipping", file=sys.stderr)
            continue

        print(f"  Fetching YouTube: {name} [{ch.get('topic', '?')}]...", file=sys.stderr)
        videos = fetch_recent_videos_rss(channel_id, lookback_hours)
        print(f"    → {len(videos)} recent videos", file=sys.stderr)

        for video in videos:
            transcript = None
            if ch.get("transcript_pull", True):
                print(f"    Pulling transcript: {video['title'][:60]}...", file=sys.stderr)
                transcript = fetch_transcript(video["video_id"])
                if transcript:
                    print(f"      → {len(transcript)} chars", file=sys.stderr)
                else:
                    print(f"      → No transcript available", file=sys.stderr)

            content = transcript[:TRANSCRIPT_MAX_CHARS] if transcript else f"[YouTube video — no transcript available] {video['title']}"

            all_articles.append({
                "title": video["title"],
                "updated": video["published"],
                "link": video["link"],
                "content": content,
                # Extra metadata for ingest.py scoring
                "_source_id": ch.get("id", ""),
                "_source_name": name,
                "_topic": ch.get("topic", "general"),
                "_weight": ch.get("weight", 1.0),
            })

    return all_articles


def main():
    parser = argparse.ArgumentParser(description="Brainrot Radio — YouTube Transcript Pipeline")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--hours", type=int, default=DEFAULT_LOOKBACK_HOURS,
                        help=f"Lookback window in hours (default: {DEFAULT_LOOKBACK_HOURS})")
    parser.add_argument("--channel", help="Fetch only this channel_id")
    args = parser.parse_args()

    articles = fetch_youtube_articles(lookback_hours=args.hours)

    if args.channel:
        articles = [a for a in articles if a.get("_source_id") == args.channel
                     or args.channel in a.get("link", "")]

    if args.json:
        print(json.dumps(articles, indent=2))
    else:
        if not articles:
            print("No recent YouTube videos found in the lookback window.")
            return

        print(f"\n{'='*70}")
        print(f" YouTube Transcript Pipeline — {len(articles)} videos")
        print(f" Lookback: {args.hours} hours")
        print(f"{'='*70}\n")

        for i, article in enumerate(articles, 1):
            print(f"## {i}. {article['title']}")
            print(f"   Source: {article.get('_source_name', '?')} | Topic: {article.get('_topic', '?')}")
            print(f"   Published: {article['updated']}")
            print(f"   Link: {article['link']}")
            print()

            content = article["content"]
            # Show first 500 chars as snippet
            snippet = content[:500]
            if len(content) > 500:
                snippet += "..."
            print(f"   {snippet}")
            print()
            print(f"   [Full transcript: {len(content)} chars]")
            print(f"\n{'─'*70}\n")


if __name__ == "__main__":
    main()
