#!/usr/bin/env python3
"""Publish a report episode to Kyle's PRIVATE podcast feed (here.now-hosted).

Why this exists
---------------
`publish.py` ships to `kylekillen/killen-time-podcast` — a fully PUBLIC GitHub
repo + RSS feed listed in podcast directories. That is correct for the daily
Killen Time *news show*, but catastrophic for dispatched family/finance reports
(it would broadcast Kyle's net worth to the world, irreversibly cached).

This module is the private counterpart. It hosts a self-contained podcast on an
unguessable `*.here.now` URL:
  - a persistent store dir holds every episode mp3 + a regenerated feed.xml
  - the here.now slug is minted once and reused forever (stable feed URL)
  - the feed is marked `itunes:block = yes` so it cannot be indexed by Apple /
    podcast crawlers even if the unguessable URL ever leaked
Kyle subscribes his podcast app to the feed URL ONCE; every future report drops
a new episode into the same feed.

Drop-in compatible with publish.publish(): same signature, returns a urls dict
with at least urls["mp3"]. So `render_report.py` can swap the import and nothing
else changes.

CLI (manual publish / bootstrap):
  publish_private.py <mp3> --title "..." [--description "..."] [--artwork path]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from feedgen.feed import FeedGenerator

# ── Config ────────────────────────────────────────────────────────
PRIVATE_FEED_DIR = os.path.expanduser("~/.observer/private-feed")
SLUG_FILE = os.path.join(PRIVATE_FEED_DIR, ".slug")
EPISODES_FILE = os.path.join(PRIVATE_FEED_DIR, "episodes.json")
HERENOW = "/opt/homebrew/bin/herenow"
FFPROBE = "/opt/homebrew/bin/ffprobe"

FEED_TITLE = "Killen Time — Private Briefings"
FEED_DESC = (
    "Private audio delivery of dispatched briefings and reports for Kyle Killen. "
    "Unlisted and not for public distribution — do not share this feed URL."
)
OWNER_NAME = "Kyle Killen"
OWNER_EMAIL = "kyle.killen@gmail.com"

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
URL_RE = re.compile(r"https://([a-z0-9]+(?:-[a-z0-9]+)+)\.here\.now")


def log(m):
    print(f"[private-feed] {m}", file=sys.stderr, flush=True)


def _ensure_dir():
    os.makedirs(PRIVATE_FEED_DIR, exist_ok=True)


def _load_episodes() -> list:
    if os.path.exists(EPISODES_FILE):
        with open(EPISODES_FILE) as f:
            return json.load(f)
    return []


def _save_episodes(eps: list):
    with open(EPISODES_FILE, "w") as f:
        json.dump(eps, f, indent=2)


def _get_slug():
    if os.path.exists(SLUG_FILE):
        s = open(SLUG_FILE).read().strip()
        return s or None
    return None


def _save_slug(slug: str):
    with open(SLUG_FILE, "w") as f:
        f.write(slug + "\n")


def _mp3_meta(mp3_path: str) -> dict:
    size = os.path.getsize(mp3_path)
    try:
        r = subprocess.run(
            [FFPROBE, "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", mp3_path],
            capture_output=True, text=True, timeout=15,
        )
        dur = float(r.stdout.strip() or 0)
    except Exception:
        dur = 0
    return {"size": size, "duration_secs": dur}


def _fmt_duration(secs: float) -> str:
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = int(secs % 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _unique_mp3_name(title: str) -> str:
    """Stable, collision-free filename for an episode mp3."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    slugpart = re.sub(r"[^a-z0-9]+", "-", (title or "report").lower()).strip("-")[:48] or "report"
    base = f"{date_str}-{slugpart}.mp3"
    # de-dupe within the dir
    n, name = 1, base
    while os.path.exists(os.path.join(PRIVATE_FEED_DIR, name)):
        name = base.replace(".mp3", f"-{n:02d}.mp3")
        n += 1
    return name


def _herenow_publish_or_update(slug: str | None) -> str:
    """Publish PRIVATE_FEED_DIR to here.now. If slug given -> update in place
    (stable URL). Else -> fresh publish, mint + return new slug. Fail loud."""
    if slug:
        cmd = [HERENOW, "update", slug, PRIVATE_FEED_DIR]
    else:
        cmd = [HERENOW, "publish", PRIVATE_FEED_DIR,
               "-t", FEED_TITLE, "-d", FEED_DESC]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    out = ANSI_RE.sub("", (r.stdout or "") + "\n" + (r.stderr or ""))
    if r.returncode != 0:
        raise RuntimeError(f"herenow failed (exit {r.returncode}):\n{out}")
    if slug:
        return slug
    m = URL_RE.search(out)
    if not m:
        raise RuntimeError(f"could not parse here.now slug from output:\n{out}")
    return m.group(1)


def _build_feed(base_url: str, episodes: list, has_artwork: bool) -> str:
    fg = FeedGenerator()
    fg.load_extension("podcast")
    page = base_url + "/"
    fg.title(FEED_TITLE)
    fg.link(href=page, rel="alternate")
    fg.description(FEED_DESC)
    fg.language("en-us")
    fg.podcast.itunes_author(OWNER_NAME)
    fg.podcast.itunes_owner(name=OWNER_NAME, email=OWNER_EMAIL)
    fg.podcast.itunes_explicit("no")
    # CRITICAL: block listing/indexing of this feed in podcast directories.
    fg.podcast.itunes_block(True)
    fg.podcast.itunes_category("News")
    art_url = f"{base_url}/artwork.jpg" if has_artwork else None
    if art_url:
        fg.podcast.itunes_image(art_url)
        fg.image(url=art_url, title=FEED_TITLE, link=page)

    for ep in sorted(episodes, key=lambda e: e["published"], reverse=True):
        mp3_url = f"{base_url}/{ep['mp3_name']}"
        fe = fg.add_entry()
        fe.id(mp3_url)
        fe.title(ep["title"])
        fe.description(ep.get("description") or ep["title"])
        fe.published(ep["published"])
        fe.enclosure(mp3_url, str(ep["size"]), "audio/mpeg")
        if ep.get("duration"):
            fe.podcast.itunes_duration(ep["duration"])
        fe.podcast.itunes_explicit("no")
        fe.podcast.itunes_block(True)
        if art_url:
            fe.podcast.itunes_image(art_url)
    return fg.rss_str(pretty=True).decode("utf-8")


def _build_index(base_url: str, episodes: list) -> str:
    rows = []
    for ep in sorted(episodes, key=lambda e: e["published"], reverse=True):
        mp3_url = f"{base_url}/{ep['mp3_name']}"
        when = ep["published"][:10]
        rows.append(
            f'<li><div class="t">{ep["title"]}</div>'
            f'<div class="m">{when} · {ep.get("duration","")}</div>'
            f'<audio controls preload="none" src="{mp3_url}"></audio>'
            f'<p class="d">{ep.get("description","")}</p></li>'
        )
    feed_url = f"{base_url}/feed.xml"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="robots" content="noindex,nofollow">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{FEED_TITLE}</title>
<style>
body{{font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
max-width:680px;margin:0 auto;padding:24px;background:#0e0e10;color:#e8e8ea}}
h1{{font-size:20px;margin:.2em 0}} .sub{{color:#9a9aa2;font-size:14px;margin-bottom:20px}}
.feedbox{{background:#1a1a1f;border:1px solid #2a2a31;border-radius:10px;padding:14px;margin-bottom:24px}}
.feedbox code{{word-break:break-all;color:#9ecbff}}
ul{{list-style:none;padding:0}} li{{background:#1a1a1f;border:1px solid #2a2a31;
border-radius:10px;padding:16px;margin-bottom:16px}}
.t{{font-weight:600}} .m{{color:#9a9aa2;font-size:13px;margin:2px 0 10px}}
audio{{width:100%}} .d{{color:#c2c2c8;font-size:14px;margin:10px 0 0}}
</style></head><body>
<h1>{FEED_TITLE}</h1>
<div class="sub">Private &amp; unlisted. Don't share this URL.</div>
<div class="feedbox">📡 <b>Subscribe in your podcast app</b> — add this feed URL:<br>
<code>{feed_url}</code></div>
<ul>{''.join(rows)}</ul>
</body></html>"""


def publish(mp3_path: str, title: str = None, description: str = None,
            artwork_path: str = None):
    """Add an episode to Kyle's private here.now-hosted podcast feed.

    Drop-in compatible with publish.publish(). Returns:
      {"mp3": <episode mp3 url>, "feed": <rss url>, "page": <landing url>}
    Raises on any failure (fail loud — never silently no-op).
    """
    mp3_path = os.path.abspath(mp3_path)
    if not (os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 500):
        raise RuntimeError(f"mp3 missing/empty: {mp3_path}")
    _ensure_dir()

    if not title:
        title = f"Briefing — {datetime.now().strftime('%Y-%m-%d')}"
    if not description:
        description = title

    # Copy artwork into the store (once).
    art_dest = os.path.join(PRIVATE_FEED_DIR, "artwork.jpg")
    if artwork_path and os.path.exists(artwork_path) and not os.path.exists(art_dest):
        shutil.copy2(artwork_path, art_dest)
    has_artwork = os.path.exists(art_dest)

    # Copy the mp3 into the persistent store.
    mp3_name = _unique_mp3_name(title)
    shutil.copy2(mp3_path, os.path.join(PRIVATE_FEED_DIR, mp3_name))
    meta = _mp3_meta(mp3_path)

    episodes = _load_episodes()
    episodes.append({
        "title": title,
        "description": description,
        "mp3_name": mp3_name,
        "size": meta["size"],
        "duration": _fmt_duration(meta["duration_secs"]),
        "published": datetime.now(timezone.utc).isoformat(),
    })
    _save_episodes(episodes)

    # Mint the slug on first ever publish (need it to build absolute URLs).
    slug = _get_slug()
    if not slug:
        log("no slug yet — bootstrapping here.now publish to mint stable URL")
        slug = _herenow_publish_or_update(None)
        _save_slug(slug)
        log(f"minted slug: {slug}")

    base_url = f"https://{slug}.here.now"
    # Write feed.xml + index.html with absolute URLs, then push.
    with open(os.path.join(PRIVATE_FEED_DIR, "feed.xml"), "w") as f:
        f.write(_build_feed(base_url, episodes, has_artwork))
    with open(os.path.join(PRIVATE_FEED_DIR, "index.html"), "w") as f:
        f.write(_build_index(base_url, episodes))

    log(f"pushing {len(episodes)} episode(s) to {base_url}")
    _herenow_publish_or_update(slug)  # update in place — stable URL

    urls = {
        "mp3": f"{base_url}/{mp3_name}",
        "feed": f"{base_url}/feed.xml",
        "page": f"{base_url}/",
    }
    log(f"done. feed={urls['feed']}")
    return urls


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Publish to Kyle's PRIVATE podcast feed")
    ap.add_argument("mp3", help="Path to MP3 file")
    ap.add_argument("--title")
    ap.add_argument("--description")
    ap.add_argument("--artwork")
    a = ap.parse_args()
    out = publish(a.mp3, a.title, a.description, a.artwork)
    print(json.dumps(out, indent=2))
