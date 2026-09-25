#!/usr/bin/env python3
"""dedup_guard.py — deterministic "did this already air in the last 7 days?" check.

Why this exists (2026-09-25): the two-pass writer re-aired stories from 09-18/21/22 and
nothing in the pipeline compared the draft against what had actually aired. The
.covered-*.json files were the only memory, and they (a) are missing for some days
(09-16, 09-23 never wrote one) and (b) were written from drafts, not from what aired.
This module reads the broadcast scripts themselves, so it needs no ledger.

Two uses, both stdlib-only:
  digest   — a compact "AIRED IN THE LAST 7 DAYS" list (segment openers per episode)
             that goes into the writer prompts, so the writer avoids the stories.
  check    — flag speaker blocks of a draft whose 5-word phrases overlap a prior
             episode heavily (a re-air), so the writer/QC see hard evidence.

    python3 dedup_guard.py digest [--today YYYY-MM-DD] [--days 7]
    python3 dedup_guard.py check SCRIPT [--today YYYY-MM-DD] [--days 7]   (exit 3 if repeats found)
"""
import argparse
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = ROOT / "scripts"

SHINGLE = 5             # words per phrase
MIN_BLOCK_WORDS = 40    # ignore short banter
REPEAT_THRESHOLD = 0.15 # share of a block's phrases found in a prior episode
DIGEST_OPENER_CHARS = 170
DIGEST_MAX_CHARS = 9000

_NAME_RE = re.compile(r"^killen-time-(\d{4}-\d{2}-\d{2})(?:-\d+)?\.txt$")
_TAG_RE = re.compile(r"^\[(BASIL|BROOKE|TRANSITION)\]\s*", re.MULTILINE)


def prior_scripts(today: str, days: int = 7, scripts_dir: Path | None = None) -> list[Path]:
    """Episode scripts dated within `days` days BEFORE `today` (never today's own)."""
    scripts_dir = scripts_dir or SCRIPTS_DIR
    t = datetime.strptime(today, "%Y-%m-%d").date()
    lo = t - timedelta(days=days)
    out = []
    for p in sorted(scripts_dir.glob("killen-time-*.txt")):
        m = _NAME_RE.match(p.name)
        if not m:
            continue
        d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        if lo <= d < t:
            out.append(p)
    return out


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", s.lower())


def _shingles(words: list[str]) -> set[tuple]:
    return {tuple(words[i:i + SHINGLE]) for i in range(len(words) - SHINGLE + 1)}


def blocks(script_text: str) -> list[str]:
    """Speaker blocks (tag stripped); [TRANSITION] lines are separators, not blocks."""
    out = []
    for chunk in re.split(r"\n\s*\n", script_text):
        chunk = chunk.strip()
        if not chunk or chunk == "[TRANSITION]":
            continue
        out.append(_TAG_RE.sub("", chunk, count=1).strip())
    return out


def find_repeats(script_text: str, prior: list[Path]) -> list[dict]:
    """Blocks of `script_text` that largely repeat an earlier episode's wording.
    Returns [{"block_no", "overlap", "episode", "excerpt"}] sorted by block order."""
    prior_sh = {}
    for p in prior:
        try:
            prior_sh[p.name] = _shingles(_words(p.read_text(errors="replace")))
        except OSError:
            continue
    flags = []
    for i, blk in enumerate(blocks(script_text), 1):
        w = _words(blk)
        if len(w) < MIN_BLOCK_WORDS:
            continue
        sh = _shingles(w)
        if not sh:
            continue
        best_name, best = None, 0.0
        for name, psh in prior_sh.items():
            frac = len(sh & psh) / len(sh)
            if frac > best:
                best_name, best = name, frac
        if best >= REPEAT_THRESHOLD:
            flags.append({"block_no": i, "overlap": round(best, 2), "episode": best_name,
                          "excerpt": " ".join(blk.split()[:24])})
    return flags


def format_flags(flags: list[dict]) -> str:
    if not flags:
        return ""
    lines = [f"- block {f['block_no']}: {int(f['overlap'] * 100)}% of its phrases already aired in "
             f"{f['episode']} — \"{f['excerpt']}...\"" for f in flags]
    return "\n".join(lines)


def digest(today: str, days: int = 7, scripts_dir: Path | None = None) -> str:
    """One line per segment opener of every episode in the window, newest last."""
    parts = []
    for p in prior_scripts(today, days, scripts_dir):
        text = p.read_text(errors="replace")
        segs = [s for s in re.split(r"\n\s*\[TRANSITION\]\s*\n", text) if s.strip()]
        openers = []
        for s in segs:
            first = blocks(s)[:1]
            if first:
                openers.append("  · " + " ".join(first[0].split())[:DIGEST_OPENER_CHARS])
        parts.append(f"{p.name}:\n" + "\n".join(openers))
    out = "\n".join(parts)
    if len(out) > DIGEST_MAX_CHARS:  # keep the NEWEST episodes when trimming
        out = "[... older episodes trimmed ...]\n" + out[-DIGEST_MAX_CHARS:]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["digest", "check"])
    ap.add_argument("script", nargs="?")
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--days", type=int, default=7)
    a = ap.parse_args(argv)
    if a.cmd == "digest":
        print(digest(a.today, a.days))
        return 0
    if not a.script:
        ap.error("check needs SCRIPT")
    flags = find_repeats(Path(a.script).read_text(errors="replace"), prior_scripts(a.today, a.days))
    if flags:
        print(format_flags(flags))
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
