#!/usr/bin/env python3
"""Publish a Killen Time episode to GitHub Releases + update podcast RSS feed."""

import argparse
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from feedgen.feed import FeedGenerator

from config import GITHUB_REPO, FEED_URL, ARTWORK_URL, SITE_URL, SCRIPTS_DIR

# ── Config ────────────────────────────────────────────────────────
FFPROBE = "/opt/homebrew/bin/ffprobe"
EPISODE_META_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "episode-metadata.json")


def load_episode_metadata() -> dict:
    """Load persistent episode metadata (duration, description, artwork per tag)."""
    if os.path.exists(EPISODE_META_FILE):
        with open(EPISODE_META_FILE) as f:
            return json.load(f)
    return {}


def save_episode_metadata(meta: dict):
    """Save persistent episode metadata."""
    with open(EPISODE_META_FILE, "w") as f:
        json.dump(meta, f, indent=2)


def get_mp3_metadata(mp3_path: str) -> dict:
    """Get duration and file size from MP3."""
    size = os.path.getsize(mp3_path)
    try:
        result = subprocess.run(
            [FFPROBE, "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", mp3_path],
            capture_output=True, text=True, timeout=10
        )
        duration_secs = float(result.stdout.strip())
    except Exception:
        duration_secs = 0
    return {"size": size, "duration_secs": duration_secs}


def format_duration(secs: float) -> str:
    """Format seconds as HH:MM:SS for iTunes duration tag."""
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = int(secs % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def parse_episode_tag(filename: str) -> dict:
    """Extract date and episode number from filename like killen-time-2026-03-02-03.mp3"""
    m = re.match(r"killen-time-(\d{4}-\d{2}-\d{2})(?:-(\d{2}))?\.mp3", filename)
    if not m:
        return None
    date_str = m.group(1)
    ep_num = int(m.group(2)) if m.group(2) else 1
    return {"date": date_str, "episode_num": ep_num}


def make_release_tag(date_str: str, ep_num: int) -> str:
    """Create release tag like ep-2026-03-02-03."""
    return f"ep-{date_str}-{ep_num:02d}"


def next_episode_number(date_str: str) -> int:
    """Query GitHub releases and return the next episode number for this date.

    Ensures auto-incrementing titles regardless of MP3 filename.
    """
    try:
        result = subprocess.run(
            ["gh", "release", "list", "-R", GITHUB_REPO, "--json",
             "tagName", "--limit", "50"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return 1

        releases = json.loads(result.stdout)
        prefix = f"ep-{date_str}-"
        existing_nums = []
        for rel in releases:
            tag = rel["tagName"]
            if tag.startswith(prefix):
                try:
                    num = int(tag[len(prefix):])
                    existing_nums.append(num)
                except ValueError:
                    pass
        return max(existing_nums) + 1 if existing_nums else 1
    except Exception:
        return 1


def upload_to_github(mp3_path: str, tag: str, title: str, notes: str, artwork_path: str = None) -> dict:
    """Upload MP3 (and optional artwork) as GitHub release assets. Returns download URLs."""
    filename = os.path.basename(mp3_path)
    assets_to_upload = [mp3_path]
    if artwork_path and os.path.exists(artwork_path):
        assets_to_upload.append(artwork_path)

    # Check if release already exists
    result = subprocess.run(
        ["gh", "release", "view", tag, "-R", GITHUB_REPO, "--json", "assets"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"  Release {tag} already exists, uploading assets...")
        subprocess.run(
            ["gh", "release", "upload", tag, *assets_to_upload, "-R", GITHUB_REPO, "--clobber"],
            check=True, capture_output=True, text=True
        )
    else:
        print(f"  Creating release {tag}...")
        subprocess.run(
            ["gh", "release", "create", tag, *assets_to_upload,
             "-R", GITHUB_REPO,
             "--title", title,
             "--notes", notes],
            check=True, capture_output=True, text=True
        )

    mp3_url = f"https://github.com/{GITHUB_REPO}/releases/download/{tag}/{filename}"
    urls = {"mp3": mp3_url}
    if artwork_path and os.path.exists(artwork_path):
        art_filename = os.path.basename(artwork_path)
        urls["artwork"] = f"https://github.com/{GITHUB_REPO}/releases/download/{tag}/{art_filename}"
    return urls


def list_all_episodes() -> list:
    """List all published episodes from GitHub releases."""
    # Get release list (assets not available here)
    result = subprocess.run(
        ["gh", "release", "list", "-R", GITHUB_REPO, "--json",
         "tagName,name,publishedAt", "--limit", "100"],
        capture_output=True, text=True, check=True
    )
    releases = json.loads(result.stdout)
    episodes = []
    for rel in releases:
        tag = rel["tagName"]
        if not tag.startswith("ep-"):
            continue
        # Fetch individual release for asset details
        r2 = subprocess.run(
            ["gh", "release", "view", tag, "-R", GITHUB_REPO, "--json", "assets"],
            capture_output=True, text=True
        )
        mp3_url = None
        mp3_size = 0
        mp3_name = ""
        artwork_url = None
        if r2.returncode == 0:
            assets = json.loads(r2.stdout).get("assets", [])
            for asset in assets:
                if asset["name"].endswith(".mp3"):
                    mp3_url = asset["url"]
                    mp3_size = asset.get("size", 0)
                    mp3_name = asset["name"]
                if asset["name"].endswith(".jpg") and "artwork" in asset["name"]:
                    artwork_url = asset["url"]
        if not mp3_url:
            # Construct URL from convention
            mp3_name = f"killen-time-{tag[3:]}.mp3"
            mp3_url = f"https://github.com/{GITHUB_REPO}/releases/download/{tag}/{mp3_name}"
        episodes.append({
            "tag": tag,
            "title": rel["name"],
            "published": rel["publishedAt"],
            "mp3_url": mp3_url,
            "mp3_size": mp3_size,
            "mp3_name": mp3_name,
            "artwork_url": artwork_url,
        })
    return sorted(episodes, key=lambda e: e["published"], reverse=True)


def generate_feed(episodes: list) -> str:
    """Generate podcast RSS feed XML."""
    fg = FeedGenerator()
    fg.load_extension("podcast")

    # Channel metadata
    fg.title("Killen Time Update")
    fg.link(href=SITE_URL, rel="alternate")
    fg.description(
        "Daily briefing on AI, prediction markets, NBA, and entertainment. "
        "Hosted by Basil and Brooke. New episodes every 6 hours."
    )
    fg.language("en-us")
    fg.podcast.itunes_author("Kyle Killen")
    fg.podcast.itunes_category("Technology", "Tech News")
    fg.podcast.itunes_image(ARTWORK_URL)
    fg.podcast.itunes_explicit("no")
    fg.podcast.itunes_owner(name="Kyle Killen", email="kyle.killen@gmail.com")
    fg.image(url=ARTWORK_URL, title="Killen Time Update", link=SITE_URL)

    # Episodes — newest first for podcast apps
    sorted_eps = sorted(episodes, key=lambda e: e.get("published", ""), reverse=True)
    for ep in sorted_eps:
        fe = fg.add_entry()
        fe.id(ep["mp3_url"])
        fe.title(ep["title"])
        fe.description(ep.get("description", ep["title"]))
        fe.published(ep["published"])
        fe.enclosure(ep["mp3_url"], str(ep["mp3_size"]), "audio/mpeg")
        if ep.get("duration"):
            fe.podcast.itunes_duration(ep["duration"])
        if ep.get("artwork_url"):
            fe.podcast.itunes_image(ep["artwork_url"])
        fe.podcast.itunes_explicit("no")

    return fg.rss_str(pretty=True).decode("utf-8")


def push_feed(feed_xml: str, artwork_path: str = None):
    """Clone repo, update feed.xml, push."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = os.path.join(tmpdir, "repo")
        subprocess.run(
            ["gh", "repo", "clone", GITHUB_REPO, repo_dir, "--", "--depth", "1"],
            check=True, capture_output=True, text=True
        )

        # Write feed.xml
        feed_path = os.path.join(repo_dir, "feed.xml")
        with open(feed_path, "w") as f:
            f.write(feed_xml)

        # Copy artwork if provided and not already there
        if artwork_path and os.path.exists(artwork_path):
            art_dest = os.path.join(repo_dir, "artwork.jpg")
            if not os.path.exists(art_dest):
                import shutil
                shutil.copy2(artwork_path, art_dest)

        # Git commit and push
        env = {**os.environ, "GIT_AUTHOR_NAME": "Mojo", "GIT_AUTHOR_EMAIL": "mojo@killentime.fm"}
        subprocess.run(["git", "add", "-A"], cwd=repo_dir, check=True, capture_output=True)

        # Check if there are changes
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=repo_dir, capture_output=True
        )
        if result.returncode == 0:
            print("  No changes to feed.xml")
            return

        subprocess.run(
            ["git", "commit", "-m", f"Update feed.xml — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"],
            cwd=repo_dir, check=True, capture_output=True, text=True, env=env
        )
        subprocess.run(
            ["git", "push"], cwd=repo_dir, check=True, capture_output=True, text=True
        )
        print("  Pushed updated feed.xml to GitHub Pages")


def extract_covered_stories(script_path: str) -> list:
    """Extract story slugs from a script file by finding key topics discussed."""
    if not os.path.exists(script_path):
        return []
    with open(script_path) as f:
        text = f.read()

    # Extract slugs from substantial topics mentioned in the script
    # Look for proper nouns, company names, people, events that form story identities
    slugs = []
    # Key patterns: "Dean Ball" → dean-ball, "Anthropic" → anthropic, etc.
    import collections
    # Find all capitalized multi-word phrases (story subjects)
    phrases = re.findall(r'(?:(?:[A-Z][a-z]+|[A-Z]+)\s+){1,4}(?:[A-Z][a-z]+|[A-Z]+)', text)
    phrase_counts = collections.Counter(phrases)
    # Stories mentioned 3+ times are likely covered topics
    for phrase, count in phrase_counts.most_common(50):
        if count >= 3 and len(phrase) > 5:
            slug = re.sub(r'[^\w]', '-', phrase.lower()).strip('-')
            if slug and slug not in slugs and len(slug) > 3:
                slugs.append(slug)
    return slugs[:30]  # Cap at 30 slugs


def update_covered_stories(script_path: str):
    """Read script, extract story slugs, write to .covered-*.json."""
    slugs = extract_covered_stories(script_path)
    if not slugs:
        return

    today = datetime.now().strftime("%Y-%m-%d")
    covered_file = os.path.join(str(SCRIPTS_DIR), f".covered-{today}.json")

    existing = {"stories": [], "segments": {}, "last_episode": None}
    if os.path.exists(covered_file):
        with open(covered_file) as f:
            existing = json.load(f)

    all_stories = list(set(existing.get("stories", []) + slugs))
    existing["stories"] = all_stories
    existing["last_episode"] = datetime.now(timezone.utc).isoformat()

    with open(covered_file, "w") as f:
        json.dump(existing, f, indent=2)
    print(f"  Updated covered stories: {len(slugs)} new slugs, {len(all_stories)} total")


def _notify_published(title: str, mp3_url: str = ""):
    """Ping Kyle's Telegram that something landed in the podcast feed. Covers
    BOTH daily episodes and Fleet Optimizer briefs (everything routes through
    publish()). Non-fatal — never breaks a publish. Suppress with
    PUBLISH_NO_TELEGRAM=1. Creds: ~/.config/personal-os/telegram.env (same file
    the alarm responder uses): TELEGRAM_BOT_TOKEN + TELEGRAM_USER_ID."""
    if os.getenv("PUBLISH_NO_TELEGRAM") == "1":
        return
    env_file = os.path.expanduser("~/.config/personal-os/telegram.env")
    token = chat = ""
    try:
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("TELEGRAM_USER_ID="):
                    chat = line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return
    if not token or not chat:
        return
    text = f"📻 Published to your podcast feed:\n{title}"
    if mp3_url:
        text += f"\n{mp3_url}"
    try:
        subprocess.run(
            ["curl", "-s", "-m", "15",
             f"https://api.telegram.org/bot{token}/sendMessage",
             "--data-urlencode", f"chat_id={chat}",
             "--data-urlencode", f"text={text}"],
            capture_output=True, timeout=20,
        )
    except Exception:
        pass


def publish(mp3_path: str, title: str = None, description: str = None, artwork_path: str = None):
    """Full publish pipeline: upload MP3 + artwork → update RSS feed → push."""
    mp3_path = os.path.abspath(mp3_path)
    filename = os.path.basename(mp3_path)
    ep_info = parse_episode_tag(filename)

    if not ep_info:
        print(f"Error: filename '{filename}' doesn't match killen-time-YYYY-MM-DD[-NN].mp3")
        return

    # Auto-increment episode number based on existing releases, not filename
    ep_num = next_episode_number(ep_info["date"])
    tag = make_release_tag(ep_info["date"], ep_num)
    if not title:
        title = f"Killen Time — {ep_info['date']} #{ep_num}"
    if not description:
        description = f"Killen Time Update for {ep_info['date']}, episode {ep_num}."

    print(f"Publishing: {filename}")
    print(f"  Tag: {tag}")

    # Get metadata
    meta = get_mp3_metadata(mp3_path)
    duration = format_duration(meta["duration_secs"])
    print(f"  Duration: {duration}, Size: {meta['size'] / 1024 / 1024:.1f} MB")

    # Upload to GitHub (MP3 + optional artwork)
    urls = upload_to_github(mp3_path, tag, title, description, artwork_path)
    print(f"  MP3 URL: {urls['mp3']}")
    if urls.get("artwork"):
        print(f"  Artwork URL: {urls['artwork']}")

    # Persist metadata for this episode
    ep_meta = load_episode_metadata()
    ep_meta[tag] = {
        "duration": duration,
        "description": description,
        "mp3_size": meta["size"],
        "artwork_url": urls.get("artwork"),
    }
    save_episode_metadata(ep_meta)

    # List all episodes and regenerate feed
    print("  Regenerating feed...")
    episodes = list_all_episodes()

    # Enrich ALL episodes with persisted metadata
    for ep in episodes:
        stored = ep_meta.get(ep["tag"], {})
        if stored.get("duration"):
            ep["duration"] = stored["duration"]
        if stored.get("description"):
            ep["description"] = stored["description"]
        if stored.get("mp3_size") and stored["mp3_size"] > 0:
            ep["mp3_size"] = stored["mp3_size"]
        if stored.get("artwork_url"):
            ep["artwork_url"] = stored["artwork_url"]

    feed_xml = generate_feed(episodes)

    # Push feed
    static_artwork = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "artwork.jpg")
    push_feed(feed_xml, static_artwork)

    # Update covered-story tracking from the script
    script_name = f"killen-time-{ep_info['date']}-{ep_info['episode_num']:02d}.txt"
    script_path = os.path.join(str(SCRIPTS_DIR), script_name)
    if not os.path.exists(script_path):
        # Try without episode number suffix
        script_path = os.path.join(str(SCRIPTS_DIR), f"killen-time-{ep_info['date']}.txt")
    update_covered_stories(script_path)

    print(f"Done! Episode published.")
    print(f"  Feed: {FEED_URL}")
    print(f"  MP3:  {urls['mp3']}")

    # Tell Kyle it landed in the feed (episodes + Fleet briefs both reach here).
    _notify_published(title, urls.get("mp3", ""))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Publish Killen Time episode")
    parser.add_argument("mp3", help="Path to MP3 file")
    parser.add_argument("--title", help="Episode title")
    parser.add_argument("--description", help="Episode description")
    parser.add_argument("--artwork", help="Path to episode artwork JPG (uploaded alongside MP3)")
    args = parser.parse_args()
    publish(args.mp3, args.title, args.description, args.artwork)
