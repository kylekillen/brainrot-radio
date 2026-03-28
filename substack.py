#!/usr/bin/env python3
"""Brainrot Radio v0.2 — Substack Full-Article Pipeline.

Fetches full article content from Substack RSS feeds (content:encoded),
strips HTML, saves to .tmp/articles/, and returns articles with full text
for the episode-writing Claude session to use as source material.

Usage:
    python3 substack.py                        # Fetch all Substacks
    python3 substack.py --show the_zvi         # Fetch one feed
    python3 substack.py --check-feeds          # Check feed health
    python3 substack.py --hours 24             # Custom lookback
"""

import argparse
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path

from config import FEEDS_JSON, TEMP_DIR

# ── Constants ─────────────────────────────────────────────────────
DEFAULT_LOOKBACK_HOURS = 48
DEFAULT_MAX_ARTICLES = 5
ARTICLE_CACHE_DIR = TEMP_DIR / "articles"
# Max chars to include in the topic brief summary (full text saved separately)
SUMMARY_CHARS = 4000
# Max chars to save per article (Zvi posts can be 250K+ of HTML)
MAX_ARTICLE_CHARS = 80000


def load_substack_config():
    """Load Substack feeds from feeds.json (type='substack')."""
    with open(FEEDS_JSON) as f:
        config = json.load(f)

    substacks = []
    for feed in config.get("feeds", []):
        if feed.get("type") == "substack":
            substacks.append(feed)

    return substacks, config.get("topic_weights", {})


def strip_html_full(text):
    """Thorough HTML stripping for article content."""
    # Remove script/style blocks
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Remove source/img tags (srcset is very verbose)
    text = re.sub(r"<(?:source|img|picture)[^>]*>", "", text, flags=re.IGNORECASE)
    # Convert headers to markdown-style
    text = re.sub(r"<h([1-6])[^>]*>(.*?)</h\1>", lambda m: "\n" + "#" * int(m.group(1)) + " " + m.group(2) + "\n", text, flags=re.IGNORECASE | re.DOTALL)
    # Convert paragraphs and divs to newlines
    text = re.sub(r"<(?:p|div|br|li)[^>]*>", "\n", text, flags=re.IGNORECASE)
    # Convert links to text [label](url)
    text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r"[\2](\1)", text, flags=re.IGNORECASE | re.DOTALL)
    # Remove remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities
    text = unescape(text)
    # Clean up whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _parse_date(date_str):
    """Parse date string (RFC 2822 or ISO 8601)."""
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        pass
    return None


def _safe_filename(text, max_len=80):
    """Convert text to a safe filename."""
    safe = re.sub(r"[^\w\s-]", "", text)
    safe = re.sub(r"\s+", "-", safe).strip("-").lower()
    return safe[:max_len]


def fetch_substack_articles(feed_url, feed_id, lookback_hours=DEFAULT_LOOKBACK_HOURS,
                            max_articles=DEFAULT_MAX_ARTICLES):
    """Fetch full articles from a Substack RSS feed.

    Returns list of dicts with full article text extracted from content:encoded.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    try:
        req = urllib.request.Request(feed_url, headers={
            "User-Agent": "BrainrotRadio/0.2",
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read().decode("utf-8", errors="replace")

        root = ET.fromstring(data)
        articles = []

        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            pubdate_str = (item.findtext("pubDate") or "").strip()
            link = (item.findtext("link") or "").strip()
            guid = (item.findtext("guid") or link).strip()

            # Parse date and check recency
            pub_dt = _parse_date(pubdate_str)
            if pub_dt:
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    continue

            # Get full article from content:encoded (Substack always includes this)
            content_encoded = (item.findtext(
                "{http://purl.org/rss/1.0/modules/content/}encoded"
            ) or "").strip()

            # Fallback to description
            description = (item.findtext("description") or "").strip()

            if content_encoded:
                full_text = strip_html_full(content_encoded)
            elif description:
                full_text = strip_html_full(description)
            else:
                full_text = ""

            # Truncate extremely long articles
            if len(full_text) > MAX_ARTICLE_CHARS:
                full_text = full_text[:MAX_ARTICLE_CHARS] + "\n\n[Article truncated — full version at source]"

            # Skip paywalled articles — Substack paywall stubs are short
            # with subscriber-only language. Real articles are 500+ words.
            word_count = len(full_text.split())
            is_paywall = (
                word_count < 200
                or "this post is for paid subscribers" in full_text.lower()
                or "subscribe to continue" in full_text.lower()
                or "this is a preview" in full_text.lower()
                or "upgrade to paid" in full_text.lower()
                or "read the rest of this post" in full_text.lower()
            )
            if is_paywall:
                print(f"    [SKIP] Paywalled: \"{title[:50]}\" ({word_count} words)", file=sys.stderr)
                continue

            articles.append({
                "guid": guid,
                "title": title,
                "published": pub_dt.isoformat() if pub_dt else pubdate_str,
                "link": link,
                "full_text": full_text,
                "word_count": len(full_text.split()),
            })

            if len(articles) >= max_articles:
                break

        return articles

    except Exception as e:
        print(f"  [WARN] Substack fetch failed for {feed_url}: {e}", file=sys.stderr)
        return []


def save_article(feed_id, article):
    """Save full article text to .tmp/articles/ for episode-writing session."""
    ARTICLE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    safe_title = _safe_filename(article["title"])
    filename = f"{feed_id}_{safe_title}.txt"
    filepath = ARTICLE_CACHE_DIR / filename

    # Skip if already used in a previous episode (archived to .tmp/used/)
    used_path = TEMP_DIR / "used" / filename
    if used_path.exists():
        return None

    # Skip if already cached and recent
    if filepath.exists() and filepath.stat().st_size > 100:
        return filepath

    header = f"# {article['title']}\n"
    header += f"Source: {feed_id} | Published: {article['published']}\n"
    header += f"Link: {article['link']}\n"
    header += f"Words: {article['word_count']}\n"
    header += "---\n\n"

    filepath.write_text(header + article["full_text"])
    return filepath


def fetch_all_substack_articles(lookback_hours=DEFAULT_LOOKBACK_HOURS):
    """Fetch all Substack feeds and return articles in ingest.py format.

    Returns list of dicts matching fetch_feed_raw() output format.
    """
    substacks, topic_weights = load_substack_config()
    if not substacks:
        return []

    all_articles = []

    for sub in substacks:
        sub_id = sub.get("id", "unknown")
        sub_name = sub.get("name", sub_id)
        feed_url = sub.get("url")
        topic = sub.get("topic", "general")
        weight = sub.get("weight", 1.0)
        max_arts = sub.get("max_articles", DEFAULT_MAX_ARTICLES)

        if not feed_url:
            continue

        print(f"  Fetching Substack: {sub_name} [{topic}]...", file=sys.stderr)
        articles = fetch_substack_articles(feed_url, sub_id, lookback_hours, max_arts)
        print(f"    → {len(articles)} recent articles", file=sys.stderr)

        for art in articles:
            # Save full article to cache (returns None if already used)
            saved_path = save_article(sub_id, art)
            if saved_path is None:
                print(f"    Skipping (already used): {art['title'][:60]}", file=sys.stderr)
                continue

            # Summary for scoring (first N chars)
            summary = art["full_text"][:SUMMARY_CHARS] if art["full_text"] else ""

            all_articles.append({
                "title": art["title"],
                "updated": art["published"],
                "link": art["link"],
                "content": summary,
                "_source_id": sub_id,
                "_source_name": sub_name,
                "_topic": topic,
                "_weight": weight,
                "_type": "substack",
                "_has_full_text": bool(art["full_text"]),
                "_full_text": art["full_text"],
                "_word_count": art["word_count"],
                "_article_path": str(saved_path) if saved_path else None,
            })

    return all_articles


def main():
    parser = argparse.ArgumentParser(description="Brainrot Radio — Substack Pipeline")
    parser.add_argument("--show", help="Fetch only this feed ID")
    parser.add_argument("--hours", type=int, default=DEFAULT_LOOKBACK_HOURS,
                        help=f"Lookback window (default: {DEFAULT_LOOKBACK_HOURS}h)")
    parser.add_argument("--check-feeds", action="store_true",
                        help="Check all Substack feed health")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    if args.check_feeds:
        substacks, _ = load_substack_config()
        healthy = 0
        total = len(substacks)
        recent_48h = 0
        now = datetime.now(timezone.utc)
        cutoff_48h = now - timedelta(hours=48)

        for sub in substacks:
            sub_name = sub.get("name", sub.get("id"))
            feed_url = sub.get("url", "")
            try:
                articles = fetch_substack_articles(feed_url, sub["id"],
                                                   lookback_hours=168, max_articles=1)
                if articles:
                    art = articles[0]
                    pub_dt = _parse_date(art["published"])
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
                        age_str = "unknown"
                    print(f"  \u2713 {sub_name} — \"{art['title'][:60]}\" ({age_str}, {art['word_count']} words)")
                    healthy += 1
                else:
                    print(f"  \u2713 {sub_name} — no recent articles (feed reachable)")
                    healthy += 1
            except Exception as e:
                print(f"  \u2717 {sub_name} — {e}")

        print(f"\nSummary: {healthy}/{total} feeds healthy, {recent_48h} articles in last 48h")
        return

    articles = fetch_all_substack_articles(lookback_hours=args.hours)

    if args.show:
        articles = [a for a in articles if a.get("_source_id") == args.show]

    if args.json:
        for a in articles:
            a.pop("_full_text", None)
        print(json.dumps(articles, indent=2))
    else:
        if not articles:
            print("No recent Substack articles found.")
            return

        print(f"\n{'='*70}")
        print(f" Substack Pipeline — {len(articles)} articles")
        print(f"{'='*70}\n")

        for i, a in enumerate(articles, 1):
            has_text = f"{a.get('_word_count', 0)} words" if a.get("_has_full_text") else "NO FULL TEXT"
            print(f"## {i}. {a['title']}")
            print(f"   Source: {a.get('_source_name')} | Topic: {a.get('_topic')}")
            print(f"   Published: {a['updated']}")
            print(f"   Content: {has_text}")
            if a.get("_article_path"):
                print(f"   Saved: {a['_article_path']}")
            print()
            snippet = a["content"][:500]
            if len(a["content"]) > 500:
                snippet += "..."
            print(f"   {snippet}")
            print(f"\n{'─'*70}\n")


if __name__ == "__main__":
    main()
