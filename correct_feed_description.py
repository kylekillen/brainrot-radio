#!/usr/bin/env python3
"""Correct (or annotate) a published episode's feed description without re-uploading audio.

`publish.py` stores each release's description in `episode-metadata.json` keyed by
tag, and `list_all_episodes()` copies that stored text into the RSS item, so a
correction to an aired episode is: update the stored description, regenerate the
feed from the existing releases, push feed.xml. The MP3 is never re-uploaded and
the release is never retagged.

    ./correct_feed_description.py ep-2026-09-24-01 "Correction: ..."

`--dry-run` prints the new item description without touching the store or the
network. Any other external effects (gh, git push) are exercised only by tests.
"""
import argparse
import os
import sys

import publish

DEFAULT_ARTWORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "artwork.jpg")


def update_description(meta: dict, tag: str, description: str) -> dict:
    """Return a copy of `meta` with `tag`'s description replaced. Raises if unknown.

    Stored fields (duration, artwork_url, published) on an existing entry are
    preserved; a new entry is created for a tag that is not yet in the store
    (e.g. one published before the store existed).
    """
    episodes = meta.get("episodes", {}) if isinstance(meta, dict) else {}
    new = dict(meta)
    new["episodes"] = dict(episodes)
    if tag in episodes and not description.strip():
        raise ValueError("description is empty; refusing to blank an existing item")
    new["episodes"][tag] = {**episodes.get(tag, {}), "description": description}
    return new


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tag", help="release tag, e.g. ep-2026-09-24-01")
    ap.add_argument("description", help="new description text (plain text; blank is refused for an existing tag)")
    ap.add_argument("--dry-run", action="store_true", help="print the new description; change nothing")
    ap.add_argument("--artwork", default=DEFAULT_ARTWORK, help="channel artwork (pushed only if the feed repo lacks it)")
    args = ap.parse_args(argv)

    meta = publish.load_episode_metadata()
    new_meta = update_description(meta, args.tag, args.description)

    if args.dry_run:
        print(new_meta["episodes"][args.tag]["description"])
        return 0

    publish.save_episode_metadata(new_meta)
    episodes = publish.list_all_episodes()
    if not any(e.get("tag") == args.tag for e in episodes):
        print(f"ERROR: release {args.tag} not found on GitHub; nothing pushed", file=sys.stderr)
        return 1
    feed_xml = publish.generate_feed(episodes)
    publish.push_feed(feed_xml, args.artwork)
    print(f"Updated feed.xml with the new description for {args.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
