#!/usr/bin/env python3
"""Brainrot Radio v0.2 — Podcast Transcript Pipeline.

Fetches recent podcast episodes via RSS feeds and obtains transcripts using
a tiered strategy:
  1. RSS podcast:transcript tag (instant, free, highest quality)
  2. Episode web page scraping (fast, free, good quality)
  3. mlx-whisper local transcription (slow, last resort)

Usage:
    python3 podcast.py                     # Fetch all podcasts
    python3 podcast.py --show ringer_nba   # Fetch one podcast
    python3 podcast.py --json              # Output raw JSON
    python3 podcast.py --hours 72          # Custom lookback
"""

import argparse
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config import FEEDS_JSON, TEMP_DIR, FFMPEG
from transcribe import cached_transcribe

# ── Constants ─────────────────────────────────────────────────────
DEFAULT_LOOKBACK_HOURS = 48
DEFAULT_MAX_EPISODES = 3
DEFAULT_MAX_AUDIO_MINUTES = 30
TRANSCRIPT_SUMMARY_CHARS = 4000  # For scoring in topic brief
PODCAST_CACHE_DIR = TEMP_DIR / "podcasts"
TRANSCRIPT_CACHE_DIR = TEMP_DIR / "transcripts"


def load_podcast_config():
    """Load podcast entries from feeds.json.

    Podcasts are identified by type="podcast" in the feeds array,
    or in a dedicated "podcasts" section.
    """
    with open(FEEDS_JSON) as f:
        config = json.load(f)

    podcasts = []

    # Check dedicated "podcasts" section first
    if "podcasts" in config:
        podcasts.extend(config["podcasts"])

    # Also collect type="podcast" from main feeds array
    for feed in config.get("feeds", []):
        if feed.get("type") == "podcast":
            # Don't duplicate if already in podcasts section
            if not any(p.get("id") == feed.get("id") for p in podcasts):
                podcasts.append(feed)

    return podcasts, config.get("topic_weights", {})


def fetch_recent_episodes(feed_url, lookback_hours=DEFAULT_LOOKBACK_HOURS,
                          max_episodes=DEFAULT_MAX_EPISODES):
    """Parse podcast RSS feed and return recent episodes with MP3 enclosure URLs.

    Returns list of dicts: {guid, title, published, mp3_url, duration, description}
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    try:
        req = urllib.request.Request(feed_url, headers={
            "User-Agent": "BrainrotRadio/0.2",
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read().decode("utf-8", errors="replace")

        root = ET.fromstring(data)
        episodes = []

        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            pubdate_str = (item.findtext("pubDate") or "").strip()
            guid = (item.findtext("guid") or title).strip()
            description = (item.findtext("description") or "").strip()
            # Strip HTML from description
            description = re.sub(r"<[^>]+>", " ", description)
            description = re.sub(r"\s+", " ", description).strip()

            # Parse published date
            pub_dt = _parse_rfc2822(pubdate_str)
            if pub_dt:
                # Ensure timezone-aware for comparison
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    continue

            # Find MP3 enclosure
            enclosure = item.find("enclosure")
            mp3_url = None
            if enclosure is not None:
                enc_url = enclosure.get("url", "")
                enc_type = enclosure.get("type", "")
                if enc_url and ("audio" in enc_type or enc_url.endswith(".mp3")):
                    mp3_url = enc_url

            # Also check for media:content
            if not mp3_url:
                for ns_prefix in [
                    "{http://search.yahoo.com/mrss/}",
                    "{http://www.itunes.com/dtds/podcast-1.0.dtd}",
                ]:
                    media = item.find(f"{ns_prefix}content")
                    if media is not None:
                        media_url = media.get("url", "")
                        if media_url and ("audio" in media.get("type", "") or media_url.endswith(".mp3")):
                            mp3_url = media_url
                            break

            # Get iTunes duration if available
            itunes_ns = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
            duration_str = (item.findtext(f"{itunes_ns}duration") or "").strip()

            link = (item.findtext("link") or "").strip()

            # Check for podcast:transcript tag (Podcasting 2.0 namespace)
            transcript_url = None
            transcript_type = None
            for ns_uri in [
                "{https://podcastindex.org/namespace/1.0}",
                "{https://github.com/Podcastindex-org/podcast-namespace/blob/main/docs/1.0.md}",
            ]:
                tx_el = item.find(f"{ns_uri}transcript")
                if tx_el is not None:
                    transcript_url = tx_el.get("url", "")
                    transcript_type = tx_el.get("type", "")
                    break

            episodes.append({
                "guid": guid,
                "title": title,
                "published": pub_dt.isoformat() if pub_dt else pubdate_str,
                "mp3_url": mp3_url,
                "link": link,
                "duration": duration_str,
                "description": description[:500],
                "transcript_url": transcript_url,
                "transcript_type": transcript_type,
            })

            if len(episodes) >= max_episodes:
                break

        return episodes

    except Exception as e:
        print(f"  [WARN] Podcast RSS fetch failed for {feed_url}: {e}", file=sys.stderr)
        return []


def _parse_rfc2822(date_str):
    """Parse RFC 2822 date string."""
    if not date_str:
        return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str)
    except Exception:
        pass
    # Fallback: try ISO format
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        pass
    return None


def _safe_filename(text, max_len=60):
    """Convert text to a safe filename."""
    safe = re.sub(r"[^\w\s-]", "", text)
    safe = re.sub(r"\s+", "-", safe).strip("-").lower()
    return safe[:max_len]


def download_episode(mp3_url, episode_guid, podcast_id):
    """Download podcast MP3 to cache directory. Returns path or None."""
    PODCAST_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Use podcast_id + sanitized guid for filename
    safe_guid = _safe_filename(episode_guid)
    filename = f"{podcast_id}_{safe_guid}.mp3"
    filepath = PODCAST_CACHE_DIR / filename

    if filepath.exists() and filepath.stat().st_size > 1000:
        print(f"  Cache hit: {filename}", file=sys.stderr)
        return filepath

    print(f"  Downloading {mp3_url[:80]}...", file=sys.stderr)
    try:
        req = urllib.request.Request(mp3_url, headers={
            "User-Agent": "BrainrotRadio/0.2",
        })
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()

        filepath.write_bytes(data)
        size_mb = len(data) / (1024 * 1024)
        print(f"  → Downloaded {size_mb:.1f} MB", file=sys.stderr)
        return filepath

    except Exception as e:
        print(f"  [WARN] Download failed: {e}", file=sys.stderr)
        return None


def transcribe_episode(mp3_path, episode_guid, max_minutes=DEFAULT_MAX_AUDIO_MINUTES):
    """Transcribe a podcast episode with local Whisper. LAST RESORT — slow."""
    cache_key = f"podcast_{_safe_filename(episode_guid)}"
    return cached_transcribe(
        mp3_path,
        cache_key=cache_key,
        max_minutes=max_minutes,
    )


def fetch_rss_transcript(transcript_url, transcript_type):
    """Fetch transcript from a podcast:transcript URL. Returns text or None."""
    if not transcript_url:
        return None
    try:
        req = urllib.request.Request(transcript_url, headers={
            "User-Agent": "BrainrotRadio/0.2",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode("utf-8", errors="replace")

        if not data or len(data) < 100:
            return None

        # Parse based on type
        if transcript_type in ("text/vtt", "application/x-subrip"):
            # VTT/SRT: strip timestamps and formatting, keep text
            lines = []
            for line in data.split("\n"):
                line = line.strip()
                # Skip timestamp lines, headers, and blank lines
                if not line or "-->" in line or line.startswith("WEBVTT"):
                    continue
                if re.match(r"^\d+$", line):  # SRT sequence numbers
                    continue
                # Strip VTT tags
                line = re.sub(r"<[^>]+>", "", line)
                if line:
                    lines.append(line)
            return " ".join(lines)

        elif transcript_type == "application/json":
            obj = json.loads(data)
            # Common JSON transcript formats
            if isinstance(obj, list):
                return " ".join(seg.get("text", seg.get("body", "")) for seg in obj if isinstance(seg, dict))
            if isinstance(obj, dict) and "segments" in obj:
                return " ".join(seg.get("text", "") for seg in obj["segments"])
            return None

        else:
            # text/plain or text/html
            text = re.sub(r"<[^>]+>", " ", data)
            text = re.sub(r"\s+", " ", text).strip()
            return text if len(text) > 200 else None

    except Exception as e:
        print(f"    [WARN] RSS transcript fetch failed: {e}", file=sys.stderr)
        return None


def fetch_web_transcript(episode_link):
    """Try to scrape transcript from an episode's web page. Returns text or None."""
    if not episode_link:
        return None
    try:
        req = urllib.request.Request(episode_link, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        if len(html) < 500:
            return None

        # Look for transcript sections — common patterns across podcast sites
        transcript_text = None

        # Pattern 1: <div/section class="transcript">...</div>
        m = re.search(
            r'<(?:div|section|article)[^>]*(?:class|id)=["\'][^"\']*transcript[^"\']*["\'][^>]*>(.*?)</(?:div|section|article)>',
            html, re.DOTALL | re.IGNORECASE
        )
        if m and len(m.group(1)) > 500:
            transcript_text = m.group(1)

        # Pattern 2: NYT-style — look for large text blocks after "transcript" header
        if not transcript_text:
            m = re.search(
                r'(?:transcript|full.?text|read.?the.?transcript)[^<]*</(?:h[1-6]|p|div)>(.*)',
                html, re.DOTALL | re.IGNORECASE
            )
            if m and len(m.group(1)) > 1000:
                # Take first 50K chars to avoid processing entire page
                transcript_text = m.group(1)[:50000]

        if not transcript_text:
            return None

        # Clean HTML
        text = re.sub(r"<script[^>]*>.*?</script>", "", transcript_text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        from html import unescape
        text = unescape(text)
        text = re.sub(r"\s+", " ", text).strip()

        # Only return if we got a substantial transcript (not just a blurb)
        if len(text) > 1000:
            print(f"    → Web transcript: {len(text)} chars", file=sys.stderr)
            return text
        return None

    except Exception as e:
        print(f"    [WARN] Web transcript scrape failed: {e}", file=sys.stderr)
        return None


def get_transcript(episode, podcast_id, max_minutes=DEFAULT_MAX_AUDIO_MINUTES):
    """Tiered transcript strategy. Returns (transcript_text, source_method)."""
    guid = episode.get("guid", "")
    cache_key = f"podcast_{_safe_filename(guid)}"
    cache_path = TRANSCRIPT_CACHE_DIR / f"{cache_key}.txt"

    # Skip if already used in a previous episode (archived to .tmp/used/)
    used_path = TEMP_DIR / "used" / f"{cache_key}.txt"
    if used_path.exists():
        print(f"  Already used: {cache_key} (in .tmp/used/), skipping", file=sys.stderr)
        return None, None

    # Check cache first (regardless of how it was obtained)
    if cache_path.exists() and cache_path.stat().st_size > 100:
        text = cache_path.read_text()
        print(f"  Cache hit: {cache_key} ({len(text)} chars)", file=sys.stderr)
        return text, "cache"

    # Tier 1: RSS podcast:transcript tag
    if episode.get("transcript_url"):
        print(f"    Trying RSS transcript...", file=sys.stderr)
        text = fetch_rss_transcript(episode["transcript_url"], episode.get("transcript_type"))
        if text and len(text) > 500:
            _save_transcript_cache(cache_path, text)
            print(f"    → RSS transcript: {len(text)} chars", file=sys.stderr)
            return text, "rss_transcript"

    # Tier 2: Scrape episode web page
    if episode.get("link"):
        print(f"    Trying web page transcript...", file=sys.stderr)
        text = fetch_web_transcript(episode["link"])
        if text and len(text) > 500:
            _save_transcript_cache(cache_path, text)
            return text, "web_scrape"

    # Tier 3: Download MP3 + Whisper (last resort)
    if episode.get("mp3_url"):
        print(f"    No pre-existing transcript found, falling back to Whisper...", file=sys.stderr)
        mp3_path = download_episode(episode["mp3_url"], guid, podcast_id)
        if mp3_path:
            text = transcribe_episode(mp3_path, guid, max_minutes)
            if text:
                return text, "whisper"

    return None, None


def _save_transcript_cache(cache_path, text):
    """Save transcript to cache file."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(text)


def fetch_podcast_articles(lookback_hours=DEFAULT_LOOKBACK_HOURS):
    """Fetch all podcasts and return articles in ingest.py format.

    Returns list of dicts matching fetch_feed_raw() output:
        {title, updated, link, content, _source_id, _source_name, _topic, _weight}
    """
    podcasts, topic_weights = load_podcast_config()
    if not podcasts:
        return []

    all_articles = []

    for pod in podcasts:
        pod_id = pod.get("id", "unknown")
        pod_name = pod.get("name", pod_id)
        feed_url = pod.get("url")
        topic = pod.get("topic", "general")
        weight = pod.get("weight", 1.0)
        max_eps = pod.get("max_episodes", DEFAULT_MAX_EPISODES)
        max_mins = pod.get("max_audio_minutes", DEFAULT_MAX_AUDIO_MINUTES)

        if not feed_url:
            print(f"  [WARN] No URL for podcast '{pod_name}', skipping", file=sys.stderr)
            continue

        print(f"  Fetching podcast: {pod_name} [{topic}]...", file=sys.stderr)
        episodes = fetch_recent_episodes(feed_url, lookback_hours, max_eps)
        print(f"    → {len(episodes)} recent episodes", file=sys.stderr)

        for ep in episodes:
            content = ep.get("description", "")

            # Tiered transcript: RSS tag → web scrape → Whisper
            # get_transcript returns (None, None) if already archived in .tmp/used/
            transcript, method = get_transcript(ep, pod_id, max_mins)

            # Skip episodes whose transcripts were already used in a previous episode
            if transcript is None and method is None:
                guid = ep.get("guid", "")
                cache_key = f"podcast_{_safe_filename(guid)}"
                used_path = TEMP_DIR / "used" / f"{cache_key}.txt"
                if used_path.exists():
                    print(f"    [SKIP] Already used in previous episode: \"{ep['title'][:50]}\"", file=sys.stderr)
                    continue

            if transcript:
                content = transcript[:TRANSCRIPT_SUMMARY_CHARS]
                print(f"    → Transcript via {method}: {len(transcript)} chars", file=sys.stderr)

            # Skip episodes with no audio URL and no transcript — truly inaccessible
            if not transcript and not ep.get("mp3_url"):
                print(f"    [SKIP] No audio or transcript available: \"{ep['title'][:50]}\"", file=sys.stderr)
                continue

            all_articles.append({
                "title": f"[Podcast] {ep['title']}",
                "updated": ep["published"],
                "link": ep.get("link", ""),
                "content": content,
                "_source_id": pod_id,
                "_source_name": pod_name,
                "_topic": topic,
                "_weight": weight,
                "_type": "podcast",
                "_guid": ep.get("guid", ""),
                "_has_transcript": bool(transcript),
                "_transcript_method": method,
                "_full_transcript": transcript,
            })

    return all_articles


def main():
    parser = argparse.ArgumentParser(description="Brainrot Radio — Podcast Pipeline")
    parser.add_argument("--show", help="Fetch only this podcast ID")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--hours", type=int, default=DEFAULT_LOOKBACK_HOURS,
                        help=f"Lookback window (default: {DEFAULT_LOOKBACK_HOURS}h)")
    parser.add_argument("--list-only", action="store_true",
                        help="List episodes without downloading/transcribing")
    parser.add_argument("--check-feeds", action="store_true",
                        help="Verify all podcast feeds are reachable and show latest episode")
    args = parser.parse_args()

    if args.check_feeds:
        podcasts, _ = load_podcast_config()
        healthy = 0
        total = len(podcasts)
        recent_48h = 0
        now = datetime.now(timezone.utc)
        cutoff_48h = now - timedelta(hours=48)

        for pod in podcasts:
            pod_name = pod.get("name", pod.get("id"))
            feed_url = pod.get("url", "")
            try:
                episodes = fetch_recent_episodes(feed_url, lookback_hours=168, max_episodes=1)
                if episodes:
                    ep = episodes[0]
                    pub_dt = _parse_rfc2822(ep["published"]) if not ep["published"].startswith("2") else None
                    if pub_dt is None:
                        try:
                            pub_dt = datetime.fromisoformat(ep["published"].replace("Z", "+00:00"))
                        except (ValueError, AttributeError):
                            pub_dt = None

                    if pub_dt:
                        if pub_dt.tzinfo is None:
                            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                        age = now - pub_dt
                        if age.total_seconds() < 3600:
                            age_str = f"{int(age.total_seconds() / 60)}m ago"
                        elif age.total_seconds() < 86400:
                            age_str = f"{int(age.total_seconds() / 3600)}h ago"
                        else:
                            age_str = f"{int(age.days)}d ago"
                        if pub_dt > cutoff_48h:
                            recent_48h += 1
                    else:
                        age_str = "unknown age"

                    has_mp3 = "MP3" if ep.get("mp3_url") else "NO MP3"
                    print(f"  \u2713 {pod_name} — \"{ep['title'][:60]}\" ({age_str}) [{has_mp3}]")
                    healthy += 1
                else:
                    print(f"  \u2713 {pod_name} — no recent episodes (feed reachable)")
                    healthy += 1
            except Exception as e:
                print(f"  \u2717 {pod_name} — {e}")

        print(f"\nSummary: {healthy}/{total} feeds healthy, {recent_48h} episodes in last 48h")
        return

    if args.list_only:
        podcasts, _ = load_podcast_config()
        for pod in podcasts:
            if args.show and pod.get("id") != args.show:
                continue
            print(f"\n{'='*60}")
            print(f" {pod.get('name', pod.get('id'))}")
            print(f" URL: {pod.get('url')}")
            print(f"{'='*60}")
            episodes = fetch_recent_episodes(
                pod["url"], args.hours, pod.get("max_episodes", 3)
            )
            for ep in episodes:
                mp3 = "MP3" if ep.get("mp3_url") else "NO MP3"
                print(f"  [{mp3}] {ep['title']}")
                print(f"         Published: {ep['published']}")
                if ep.get("duration"):
                    print(f"         Duration: {ep['duration']}")
        return

    articles = fetch_podcast_articles(lookback_hours=args.hours)

    if args.show:
        articles = [a for a in articles if a.get("_source_id") == args.show]

    if args.json:
        # Remove _full_transcript from JSON output (too large)
        for a in articles:
            a.pop("_full_transcript", None)
        print(json.dumps(articles, indent=2))
    else:
        if not articles:
            print("No recent podcast episodes found.")
            return

        print(f"\n{'='*70}")
        print(f" Podcast Pipeline — {len(articles)} episodes")
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
