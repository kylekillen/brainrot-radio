#!/usr/bin/env python3
"""Brainrot Radio v0.1 — RSS Ingestion & Topic Ranking.

Reads feeds from feeds.json (profile-driven feed list with per-feed weights
and topic weights). Scores articles by recency × feed weight × topic weight
× keyword boost. Deduplicates and outputs a topic brief.

Usage:
    python3 ingest.py              # Print top stories as formatted brief
    python3 ingest.py --report     # Same as above
    python3 ingest.py --json       # Output raw JSON
    python3 ingest.py -o brief.txt # Save brief to file
"""

import argparse
import json
import math
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path

from config import (
    FEEDS_JSON,
    KEYWORD_BOOSTS,
    RECENCY_HALF_LIFE_HOURS,
    SCRIPTS_DIR,
    TEMP_DIR,
    TOP_STORIES,
)
from youtube import fetch_youtube_articles


def fetch_feed_raw(feed_url):
    """Minimal feed fetch using urllib — no feedparser dependency.

    Adapted from ~/.claude/scripts/daily-upgrade-check.py.
    """
    try:
        req = urllib.request.Request(feed_url, headers={"User-Agent": "BrainrotRadio/0.1"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode("utf-8")

        root = ET.fromstring(data)
        entries = []

        # Handle Atom feeds
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            title = entry.findtext("atom:title", "", ns).strip()
            updated = entry.findtext("atom:updated", "", ns).strip()
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            content = entry.findtext("atom:content", "", ns).strip()
            if not content:
                content = entry.findtext("atom:summary", "", ns).strip()
            entries.append({
                "title": title,
                "updated": updated,
                "link": link,
                "content": strip_html(content[:1000]),
            })

        # Handle RSS feeds
        if not entries:
            for item in root.iter("item"):
                title = (item.findtext("title") or "").strip()
                pubdate = (item.findtext("pubDate") or "").strip()
                link = (item.findtext("link") or "").strip()
                desc = (item.findtext("description") or "").strip()
                content_encoded = (item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded") or "").strip()
                body = content_encoded if content_encoded else desc
                entries.append({
                    "title": title,
                    "updated": pubdate,
                    "link": link,
                    "content": strip_html(body[:1000]),
                })

        return entries
    except Exception as e:
        print(f"  [WARN] Fetch failed for {feed_url}: {e}", file=sys.stderr)
        return []


def strip_html(text):
    """Remove HTML tags, srcset noise, and decode entities."""
    # Remove <source> and <img> tags with their attributes (srcset is verbose)
    text = re.sub(r"<(?:source|img)[^>]*>", "", text, flags=re.IGNORECASE)
    # Remove remaining HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_date(date_str):
    """Parse various date formats into a timezone-aware datetime."""
    if not date_str:
        return None
    # ISO 8601 (Atom)
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        pass
    # RFC 2822 (RSS pubDate)
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        pass
    return None


def age_label(dt):
    """Return human-readable age label for an article."""
    if dt is None:
        return "unknown"
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age_hours = (now - dt).total_seconds() / 3600
    if age_hours < 0:
        return "today"
    if age_hours < 24:
        return "today"
    if age_hours < 48:
        return "yesterday"
    if age_hours < 168:
        return "this week"
    return "older"


def recency_score(dt):
    """Exponential decay score based on article age."""
    if dt is None:
        return 0.3  # Unknown date gets low default
    now = datetime.now(timezone.utc)
    # Ensure both datetimes are timezone-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age_hours = (now - dt).total_seconds() / 3600
    if age_hours < 0:
        age_hours = 0
    return math.exp(-0.693 * age_hours / RECENCY_HALF_LIFE_HOURS)


def keyword_score(title, content):
    """Boost score based on keyword matches."""
    text = f"{title} {content}".lower()
    boost = 1.0
    for keyword, weight in KEYWORD_BOOSTS.items():
        if keyword.lower() in text:
            boost = max(boost, weight)
    return boost


def word_overlap(a, b):
    """Fraction of shared words between two titles."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0
    overlap = words_a & words_b
    return len(overlap) / min(len(words_a), len(words_b))


def deduplicate(articles, threshold=0.4):
    """Remove articles with >threshold title word overlap."""
    result = []
    for article in articles:
        is_dup = False
        for existing in result:
            if word_overlap(article["title"], existing["title"]) > threshold:
                # Keep the higher-scored one
                if article["score"] > existing["score"]:
                    result.remove(existing)
                    result.append(article)
                is_dup = True
                break
        if not is_dup:
            result.append(article)
    return result


def load_covered_stories():
    """Load covered-story list to avoid repeating content.

    Checks today AND yesterday — podcast episodes from yesterday's late runs
    should still be considered 'covered'.
    """
    result = {"stories": [], "segments": {}, "podcast_guids": [], "last_episode": None}

    for delta in [0, 1]:  # today and yesterday
        day = (datetime.now() - timedelta(days=delta)).strftime("%Y-%m-%d")
        covered_file = SCRIPTS_DIR / f".covered-{day}.json"
        if covered_file.exists():
            with open(covered_file) as f:
                data = json.load(f)
            result["stories"] = list(set(result["stories"] + data.get("stories", [])))
            result["segments"].update(data.get("segments", {}))
            result["podcast_guids"] = list(set(result["podcast_guids"] + data.get("podcast_guids", [])))
            if not result["last_episode"]:
                result["last_episode"] = data.get("last_episode")

    return result


def save_covered_stories(stories, segments=None, podcast_guids=None):
    """Save covered stories after generating an episode."""
    today = datetime.now().strftime("%Y-%m-%d")
    covered_file = SCRIPTS_DIR / f".covered-{today}.json"

    # Only load today's file for saving (not yesterday's)
    existing = {"stories": [], "segments": {}, "podcast_guids": [], "last_episode": None}
    if covered_file.exists():
        with open(covered_file) as f:
            existing = json.load(f)

    all_stories = list(set(existing.get("stories", []) + stories))
    all_segments = existing.get("segments", {})
    if segments:
        all_segments.update(segments)
    all_guids = list(set(existing.get("podcast_guids", []) + (podcast_guids or [])))

    data = {
        "stories": all_stories,
        "segments": all_segments,
        "podcast_guids": all_guids,
        "last_episode": datetime.now(timezone.utc).isoformat(),
    }

    covered_file.parent.mkdir(parents=True, exist_ok=True)
    with open(covered_file, "w") as f:
        json.dump(data, f, indent=2)


def archive_used_sources(used_transcript_guids=None, used_article_paths=None):
    """Move used transcripts and articles to .tmp/used/ so they aren't re-read.

    Called after script writing to prevent the next episode from seeing
    the same source files in .tmp/transcripts/ and .tmp/articles/.
    """
    import shutil

    used_dir = TEMP_DIR / "used"
    used_dir.mkdir(parents=True, exist_ok=True)

    moved = 0

    # Move used podcast transcripts by GUID
    if used_transcript_guids:
        transcripts_dir = TEMP_DIR / "transcripts"
        if transcripts_dir.exists():
            for tf in transcripts_dir.glob("*.txt"):
                # Transcript filenames contain the GUID: podcast_GUID.txt
                for guid in used_transcript_guids:
                    if guid in tf.name:
                        dest = used_dir / tf.name
                        shutil.move(str(tf), str(dest))
                        moved += 1
                        break

    # Move used Substack articles by path
    if used_article_paths:
        for path_str in used_article_paths:
            p = Path(path_str)
            if p.exists() and p.parent == (TEMP_DIR / "articles"):
                dest = used_dir / p.name
                shutil.move(str(p), str(dest))
                moved += 1

    if moved:
        print(f"  → Archived {moved} used source files to .tmp/used/", file=sys.stderr)
    return moved


def archive_all_sources():
    """Move ALL transcripts and articles to .tmp/used/.

    Called after successful rendering to ensure no source can feed
    the next episode — regardless of how the pipeline was invoked
    (generate-episode.sh, manual Claude session, or direct script).
    """
    import shutil

    used_dir = TEMP_DIR / "used"
    used_dir.mkdir(parents=True, exist_ok=True)

    moved = 0
    for subdir in ("transcripts", "articles"):
        src_dir = TEMP_DIR / subdir
        if src_dir.exists():
            for f in src_dir.glob("*.txt"):
                shutil.move(str(f), str(used_dir / f.name))
                moved += 1

    if moved:
        print(f"  → Archived {moved} source files to .tmp/used/ (post-render cleanup)", file=sys.stderr)
    return moved


def load_feeds_config():
    """Load feeds.json and return feeds list + topic weights."""
    with open(FEEDS_JSON) as f:
        config = json.load(f)
    return config["feeds"], config.get("topic_weights", {})


def fetch_all_feeds():
    """Fetch all feeds from feeds.json and score articles."""
    feeds, topic_weights = load_feeds_config()

    all_articles = []
    for feed in feeds:
        # Skip Substack feeds — substack.py handles these with full article content
        if feed.get("type") == "substack":
            continue

        feed_id = feed["id"]
        feed_name = feed["name"]
        url = feed["url"]
        feed_weight = feed.get("weight", 1.0)
        topic = feed.get("topic", "general")
        topic_weight = topic_weights.get(topic, 1.0)

        print(f"  Fetching {feed_name} [{topic}]...", file=sys.stderr)
        entries = fetch_feed_raw(url)
        if not entries:
            continue

        # Cap entries per feed — podcast backlogs can be huge
        if len(entries) > 30:
            entries = entries[:30]
        print(f"    → {len(entries)} entries", file=sys.stderr)

        for entry in entries:
            dt = parse_date(entry["updated"])
            r_score = recency_score(dt)
            content_text = entry.get("content", "")
            k_score = keyword_score(entry["title"], content_text)
            total_score = r_score * feed_weight * topic_weight * k_score

            a_label = age_label(dt)

            all_articles.append({
                "title": entry["title"],
                "source": feed_name,
                "source_id": feed_id,
                "topic": topic,
                "link": entry["link"],
                "content": entry["content"],
                "date": entry["updated"],
                "parsed_date": dt.isoformat() if dt else None,
                "age_label": a_label,
                "recency": round(r_score, 3),
                "feed_weight": feed_weight,
                "topic_weight": topic_weight,
                "keyword_boost": round(k_score, 2),
                "score": round(total_score, 3),
            })

    # ── YouTube channels ────────────────────────────────────────────
    with open(FEEDS_JSON) as f:
        config = json.load(f)
    topic_weights_full = config.get("topic_weights", {})

    print("Fetching YouTube channels...", file=sys.stderr)
    try:
        yt_articles = fetch_youtube_articles()
    except Exception as e:
        print(f"  [WARN] YouTube pipeline failed: {e}", file=sys.stderr)
        yt_articles = []

    for entry in yt_articles:
        dt = parse_date(entry["updated"])
        r_score = recency_score(dt)
        k_score = keyword_score(entry["title"], entry["content"])
        feed_weight = entry.get("_weight", 1.0)
        topic = entry.get("_topic", "general")
        t_weight = topic_weights_full.get(topic, 1.0)
        total_score = r_score * feed_weight * t_weight * k_score
        a_label = age_label(dt)

        all_articles.append({
            "title": entry["title"],
            "source": entry.get("_source_name", "YouTube"),
            "source_id": entry.get("_source_id", "youtube"),
            "topic": topic,
            "link": entry["link"],
            "content": entry["content"],
            "date": entry["updated"],
            "parsed_date": dt.isoformat() if dt else None,
            "age_label": a_label,
            "recency": round(r_score, 3),
            "feed_weight": feed_weight,
            "topic_weight": t_weight,
            "keyword_boost": round(k_score, 2),
            "score": round(total_score, 3),
        })

    print(f"  → {len(yt_articles)} YouTube articles added", file=sys.stderr)

    # ── Podcasts ────────────────────────────────────────────────────
    print("Fetching podcasts...", file=sys.stderr)
    try:
        from podcast import fetch_podcast_articles
        pod_articles = fetch_podcast_articles()
    except Exception as e:
        print(f"  [WARN] Podcast pipeline failed: {e}", file=sys.stderr)
        pod_articles = []

    for entry in pod_articles:
        dt = parse_date(entry["updated"])
        r_score = recency_score(dt)
        k_score = keyword_score(entry["title"], entry["content"])
        feed_weight = entry.get("_weight", 1.0)
        topic = entry.get("_topic", "general")
        t_weight = topic_weights_full.get(topic, 1.0)
        # Podcast transcript boost: transcribed episodes are the richest material
        transcript_boost = 1.5 if entry.get("_has_transcript") else 1.2
        total_score = r_score * feed_weight * t_weight * k_score * transcript_boost
        a_label = age_label(dt)

        all_articles.append({
            "title": entry["title"],
            "source": entry.get("_source_name", "Podcast"),
            "source_id": entry.get("_source_id", "podcast"),
            "topic": topic,
            "link": entry["link"],
            "content": entry["content"],
            "date": entry["updated"],
            "parsed_date": dt.isoformat() if dt else None,
            "age_label": a_label,
            "recency": round(r_score, 3),
            "feed_weight": feed_weight,
            "topic_weight": t_weight,
            "keyword_boost": round(k_score, 2),
            "score": round(total_score, 3),
            "_type": "podcast",
            "_has_transcript": entry.get("_has_transcript", False),
        })

    print(f"  → {len(pod_articles)} podcast articles added", file=sys.stderr)

    # ── Substack Full Articles ───────────────────────────────────────
    print("Fetching Substack full articles...", file=sys.stderr)
    try:
        from substack import fetch_all_substack_articles
        sub_articles = fetch_all_substack_articles()
    except Exception as e:
        print(f"  [WARN] Substack pipeline failed: {e}", file=sys.stderr)
        sub_articles = []

    for entry in sub_articles:
        dt = parse_date(entry["updated"])
        r_score = recency_score(dt)
        k_score = keyword_score(entry["title"], entry["content"])
        feed_weight = entry.get("_weight", 1.0)
        topic = entry.get("_topic", "general")
        t_weight = topic_weights_full.get(topic, 1.0)
        # Substack depth boost: full-text articles are among the richest material.
        # Podcasts and Substacks should get more coverage than generic news feeds.
        # 1000+ words = 1.3x, 3000+ words = 1.5x, 8000+ words = 1.7x
        wc = entry.get("_word_count", 0)
        depth_boost = 1.2  # base boost for any Substack (even short posts)
        if wc >= 8000:
            depth_boost = 1.7
        elif wc >= 3000:
            depth_boost = 1.5
        elif wc >= 1000:
            depth_boost = 1.3
        # Substack uses the SAME 6h half-life as everything else.
        # Fresh content always wins. Depth/weight are tiebreakers among recent items.
        total_score = r_score * feed_weight * t_weight * k_score * depth_boost
        a_label = age_label(dt)

        all_articles.append({
            "title": entry["title"],
            "source": entry.get("_source_name", "Substack"),
            "source_id": entry.get("_source_id", "substack"),
            "topic": topic,
            "link": entry["link"],
            "content": entry["content"],
            "date": entry["updated"],
            "parsed_date": dt.isoformat() if dt else None,
            "age_label": a_label,
            "recency": round(r_score, 3),
            "feed_weight": feed_weight,
            "topic_weight": t_weight,
            "keyword_boost": round(k_score, 2),
            "score": round(total_score, 3),
            "_type": "substack",
            "_has_full_text": entry.get("_has_full_text", False),
            "_word_count": entry.get("_word_count", 0),
            "_article_path": entry.get("_article_path"),
        })

    print(f"  → {len(sub_articles)} Substack articles added", file=sys.stderr)

    # ── Twitch VODs ─────────────────────────────────────────────────
    print("Fetching Twitch VODs...", file=sys.stderr)
    try:
        from twitch import fetch_twitch_articles
        twitch_articles = fetch_twitch_articles()
    except Exception as e:
        print(f"  [WARN] Twitch pipeline failed: {e}", file=sys.stderr)
        twitch_articles = []

    for entry in twitch_articles:
        dt = parse_date(entry["updated"])
        r_score = recency_score(dt)
        k_score = keyword_score(entry["title"], entry["content"])
        feed_weight = entry.get("_weight", 1.0)
        topic = entry.get("_topic", "general")
        t_weight = topic_weights_full.get(topic, 1.0)
        total_score = r_score * feed_weight * t_weight * k_score
        a_label = age_label(dt)

        all_articles.append({
            "title": entry["title"],
            "source": entry.get("_source_name", "Twitch"),
            "source_id": entry.get("_source_id", "twitch"),
            "topic": topic,
            "link": entry["link"],
            "content": entry["content"],
            "date": entry["updated"],
            "parsed_date": dt.isoformat() if dt else None,
            "age_label": a_label,
            "recency": round(r_score, 3),
            "feed_weight": feed_weight,
            "topic_weight": t_weight,
            "keyword_boost": round(k_score, 2),
            "score": round(total_score, 3),
            "_type": "twitch",
            "_has_transcript": entry.get("_has_transcript", False),
        })

    print(f"  → {len(twitch_articles)} Twitch articles added", file=sys.stderr)

    # ── Recency-first sorting ────────────────────────────────────────
    # Kyle's rule: "GO with RECENCY first, then when there's a lot of recent
    # material, prioritize by the weights."
    #
    # Implementation: bucket articles into recency tiers, sort by tier first,
    # then by weighted score within each tier. This ensures today's fresh
    # podcasts always beat yesterday's deep Substack essays.
    def recency_tier(article):
        """Return sort tier (lower = more recent = higher priority)."""
        r = article.get("recency", 0)
        if r >= 0.5:    # last ~6 hours (within one half-life)
            return 0
        elif r >= 0.25:  # ~6-12 hours
            return 1
        elif r >= 0.125: # ~12-18 hours
            return 2
        elif r >= 0.06:  # ~18-24 hours
            return 3
        else:            # older than 24 hours
            return 4

    all_articles.sort(key=lambda a: (recency_tier(a), -a["score"]))

    # Deduplicate
    all_articles = deduplicate(all_articles)

    # HARD EXCLUDE previously covered sources — a source used once is gone.
    # Topics can recur via NEW sources; we just never pull from the same
    # article/podcast episode twice.
    covered = load_covered_stories()
    covered_slugs = covered.get("stories", [])
    covered_guids = set(covered.get("podcast_guids", []))

    pre_count = len(all_articles)
    filtered = []
    for a in all_articles:
        exclude = False

        # Check by title slug (articles, substacks)
        if covered_slugs:
            title_slug = re.sub(r"[^\w]", "-", a["title"].lower())[:60]
            if any(s in title_slug or title_slug in s for s in covered_slugs):
                exclude = True

        # Check by podcast episode GUID
        if a.get("_type") == "podcast" and a.get("_guid") in covered_guids:
            exclude = True

        # Also exclude if the source file has already been archived
        if a.get("_article_path"):
            p = Path(a["_article_path"])
            if not p.exists():
                exclude = True  # File was archived to .tmp/used/

        if not exclude:
            filtered.append(a)

    all_articles = filtered
    excluded = pre_count - len(all_articles)
    if excluded:
        print(f"  → {excluded} previously covered sources EXCLUDED (not demoted)", file=sys.stderr)

    all_articles.sort(key=lambda a: (recency_tier(a), -a["score"]))

    return all_articles[:TOP_STORIES * 10]  # Return plenty for topic diversity


def ensure_topic_diversity(articles, top_n):
    """Ensure at least 1 story per active topic in the selection.

    Takes the top_n by recency-tier sort, then swaps in the best story
    from any topic that got shut out — but only replaces the weakest
    article from the SAME or lower recency tier (never bumps a fresh
    story for an old one from a missing topic).
    """
    def _tier(a):
        r = a.get("recency", 0)
        if r >= 0.5:
            return 0
        elif r >= 0.25:
            return 1
        elif r >= 0.125:
            return 2
        elif r >= 0.06:
            return 3
        return 4

    selected = articles[:top_n]
    # Scan ALL articles for available topics — podcasts/nba/etc may rank low
    all_topics = {a["topic"] for a in articles}
    selected_topics = {a["topic"] for a in selected}
    missing = all_topics - selected_topics

    # Track which indices are "protected" (swapped-in for diversity)
    protected = set()
    for topic in missing:
        # Find best article from this topic
        best = next((a for a in articles if a["topic"] == topic and a not in selected), None)
        if best and selected:
            best_tier = _tier(best)
            if best_tier <= 3:
                # Replace the lowest-scoring UNPROTECTED article
                candidates = [i for i in range(len(selected)) if i not in protected]
                if candidates:
                    worst_idx = min(candidates, key=lambda i: selected[i]["score"])
                    selected[worst_idx] = best
                    protected.add(worst_idx)

    # Re-sort by tier then score
    selected.sort(key=lambda a: (_tier(a), -a["score"]))
    return selected


def format_report(articles, top_n=None):
    """Format a topic brief for script writing."""
    top_n = top_n or TOP_STORIES
    selected = ensure_topic_diversity(articles, top_n)

    lines = []
    lines.append("# Brainrot Radio — Topic Brief")
    lines.append(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"# Top {len(selected)} stories — sorted by RECENCY FIRST, then weighted score as tiebreaker")
    lines.append("")

    # Show topic distribution
    topic_counts = {}
    for a in selected:
        t = a.get("topic", "unknown")
        topic_counts[t] = topic_counts.get(t, 0) + 1
    lines.append(f"# Topic mix: {', '.join(f'{t}={c}' for t, c in sorted(topic_counts.items(), key=lambda x: -x[1]))}")
    lines.append("")

    # Load covered stories for dedup warnings
    covered = load_covered_stories()
    covered_stories = covered.get("stories", [])

    for i, a in enumerate(selected, 1):
        # Age and freshness indicators
        a_label = a.get("age_label", "unknown")
        freshness = ""
        if a_label == "older":
            freshness = " ⚠️ NOT BREAKING (>48h old)"
        elif a_label == "this week":
            freshness = " (this week)"
        elif a_label == "yesterday":
            freshness = " (yesterday)"

        # Covered-story warning
        covered_warn = ""
        title_slug = re.sub(r"[^\w]", "-", a["title"].lower())[:40]
        if any(s in title_slug or title_slug in s for s in covered_stories):
            covered_warn = " 🔁 PREVIOUSLY COVERED"

        lines.append(f"## {i}. {a['title']}{freshness}{covered_warn}")
        lines.append(f"Source: {a['source']} | Topic: {a.get('topic', '?')} | Age: {a_label} | Score: {a['score']}")
        lines.append(f"Weights: feed={a['feed_weight']} × topic={a['topic_weight']} × recency={a['recency']} × keyword={a['keyword_boost']}")
        if a.get("_type") in ("podcast", "twitch"):
            tx = "transcript available" if a.get("_has_transcript") else "no transcript"
            lines.append(f"Type: {a['_type']} ({tx})")
            if a.get("_guid"):
                lines.append(f"GUID: {a['_guid']}")
        if a.get("_type") == "substack":
            wc = a.get("_word_count", 0)
            art_path = a.get("_article_path", "")
            ft = f"full text ({wc} words)" if a.get("_has_full_text") else "summary only"
            lines.append(f"Type: substack ({ft})")
            if art_path:
                lines.append(f"Full article: {art_path}")
        lines.append(f"Link: {a['link']}")
        lines.append("")
        if a["content"]:
            lines.append(a["content"])
        lines.append("")
        lines.append("---")
        lines.append("")

    # Add remaining honorable mentions
    remaining = articles[top_n:top_n + 5]
    if remaining:
        lines.append("## Honorable Mentions (lower-ranked but available)")
        for a in remaining:
            lines.append(f"- [{a['score']}] {a['title']} ({a['source']}, {a.get('topic', '?')})")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Brainrot Radio RSS Ingestion")
    parser.add_argument("--report", action="store_true", help="Output formatted topic brief")
    parser.add_argument("-o", "--output", help="Save output to file")
    parser.add_argument("-n", "--top", type=int, default=TOP_STORIES, help="Number of top stories")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    print("Fetching feeds...", file=sys.stderr)
    articles = fetch_all_feeds()
    print(f"Ranked {len(articles)} articles after dedup.", file=sys.stderr)

    if args.json:
        output = json.dumps(articles[:args.top], indent=2)
    else:
        output = format_report(articles, args.top)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Saved to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
