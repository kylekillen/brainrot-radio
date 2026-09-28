#!/usr/bin/env python3
"""X PULSE — what X is talking about, as a source for the day's episode.

Kyle, 2026-09-27: the X feed reports "would be very useful content and
pointers for you for the podcast… you have full browser access so you can
also look at x and see what's trending so that you're able to get a handle
on the major stories and dig deeper when needed."

Two inputs, both optional, and neither can fail the run:

  1. TRENDING: x.com/explore tabs (trending, news, sports, entertainment),
     read through Kyle's signed-in Chrome with the same raw-CDP reader the
     X-feed desk uses (~/model-router/bin/cdp_read.py). No login, no API.
  2. FEED READS: the X-feed dispatches the fleet already writes to
     ~/.observer/reads/*-x-feed-dispatch-*.md every ~4h, which are digests of
     Kyle's Following timeline with quotes, handles and view counts.

Output is a markdown section appended to .tmp/topic-brief.txt, so every
writer engine (claude, external, gemini, router) sees it without prompt
plumbing per engine.

The dispatches are written for Kyle, not for air: they talk about "this desk",
harvest mechanics and internal story arcs. The header tells the writer to
treat them as leads only and attribute to the original posters; the scrub
below removes the lines that are purely about how the report was produced.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

READS_DIR = Path.home() / ".observer" / "reads"
CDP_DIR = Path.home() / "model-router" / "bin"
TABS = ("trending", "news", "sports", "entertainment")
PER_TAB = 20
PER_DISPATCH_CHARS = 9000
TOTAL_DISPATCH_CHARS = 36000

HEADER = """
═══════════════════════════════════════════════════════════════
X PULSE — what X is talking about (gathered {when})
═══════════════════════════════════════════════════════════════
HOW TO USE THIS SECTION (writer instructions, not source material):
- TRENDING shows what is big on X right now. Use it to judge which of today's
  stories are the MAJOR ones, and to catch big stories the other sources miss
  (NFL results, entertainment news, AI launches). A trend label alone is not a
  story: confirm it and get the substance — search the web, and open the post's
  reply thread on x.com to read the whole conversation — before putting it on
  air. This section is handed to external models as well as local ones, so it
  names no internal tool, path or file.
- FEED READS are digests of posts from accounts the listener follows, with
  quotes, handles and view counts. They are LEADS and quotable material.
  Attribute every quote to the person who posted it ("Bill Simmons posted…").
- NEVER mention dispatches, reports, a "desk", numbered issues, harvests, or
  how these leads were gathered. Say "on X" or name the poster. Drop any
  internal story-arc labels (e.g. "E17/E18") entirely.
- Posting times in the feed reads are approximate and in Mountain Time.
"""

# Whole lines that are pure production bookkeeping: the collection window and
# the provenance/colophon notes. The corpus writes them as "Window:",
# "*Window:*" and "**Window:**", so the label is matched after markdown
# emphasis, quoting and bullet markers are skipped.
PROVENANCE = re.compile(
    r"^[*_> \t]*(?:Window|Colophon|Provenance|Sources|Feed|Gap note|Method|"
    r"Methodology|Burn flag|Verification|Not carried forward|Not forwarded|"
    r"Not opened|Model-landscape)\b",
    re.IGNORECASE,
)

# Sentences in a dispatch that talk about how the report was produced (or
# about the listener's private system) rather than the news itself. Removed at
# sentence level: the same line often carries real news after a meta clause.
META = re.compile(
    r"dispatch|\bdesk\b|harvest|house (?:rule|memory)|KYLE[-_ ]QUEUE|\bKyle\b|"
    r"killen[- ]time|model-router|model-landscape|x-feed-read|workspace pin|"
    r"this reading|this read\b|not pulled|not chased|not opened|unopened|"
    r"follow list|follow next|our own miss|in[- ]window|this window|pre-window|"
    r"E1\d(?:/E1\d)?\b|tickler|fleet|"
    # the collection tool's own vocabulary: "five thread pulls, four web
    # searches, three page fetches", "35 scrolls", "Forwarded to model-router",
    # "Forwarded whole". Plain "carries it forward" / "move forward" stay.
    r"(?:thread|web|page)\s*(?:pull|search|fetch)(?:s|es|ed)?\b|scrolls?\b|"
    r"forward(?:ed|ing)\b|colophon|provenance|partial[- ]load|retry",
    re.IGNORECASE,
)
# Splits on sentence enders, then optionally a closing quote/bracket: real
# dispatches quote a post and then trail a note onto it ("…injury." Forwarded
# to model-router."), and without the closer the note takes the quote with it.
SENTENCE = re.compile(r"(?<=[.!?:;\"'\u201d)\]])\s+(?=[A-Z*\"\u201c(\[@_-])")

# Belt and braces on top of META (GUARDRAILS 2026-09-24: no internal
# repo/role/launchd names or file paths in anything a writer, or an external
# model, can read): a private marker META has never seen costs its own
# sentence, and a line that is nothing but one is dropped whole. AGENTS.md is
# deliberately absent — "Claude Code adopts AGENTS.md" is real news in 09-19.
PRIVATE = re.compile(
    r"model-router|observer-system|killen[- ]time|x-feed-read|cdp_read|"
    r"HANDOFF\.md|INBOX\.md|STATUS\.md|calibration\.md|"
    r"launchd|LaunchAgent|\.observer/|~/?[A-Za-z0-9._-]+/|/Users/|/home/",
    re.IGNORECASE,
)

# A parenthetical or a dash clause: where the view counts and "…this window"
# notes sit inside a line whose news is worth keeping.
CLAUSE = re.compile(r"\s*(?:\([^()]*\)|[—–-][^—–.]*)")


def _keep(chunk: str) -> str | None:
    """The chunk if it is clean, the chunk minus its meta clause if that is
    what makes it dirty, else None. Never returns text that still trips META
    or PRIVATE, so trimming cannot become a leak."""
    if not (META.search(chunk) or PRIVATE.search(chunk)):
        return chunk
    trimmed = re.sub(r"\s{2,}", " ", CLAUSE.sub(" ", chunk)).strip(" \t:;,—-")
    if trimmed and not (META.search(trimmed) or PRIVATE.search(trimmed)):
        return trimmed
    return None


def read_trends(tabs=TABS, per_tab=PER_TAB) -> dict[str, list[str]]:
    sys.path.insert(0, str(CDP_DIR))
    from cdp_read import CDP  # noqa: E402  (lives in model-router)

    js = (
        "Array.from(document.querySelectorAll('[data-testid=\"cellInnerDiv\"]'))"
        ".map(e=>e.innerText.replace(/\\n+/g,' | ').trim()).filter(t=>t.length>3)"
    )
    out: dict[str, list[str]] = {}
    c = CDP()
    try:
        c.open_tab()
        for tab in tabs:
            c.goto(f"https://x.com/explore/tabs/{tab}", settle=8)
            rows = c.eval_js(js) or []
            out[tab] = clean_trend_rows(rows)[:per_tab]
    finally:
        c.close()
    return out


def clean_trend_rows(rows: list[str]) -> list[str]:
    seen, keep = set(), []
    for r in rows:
        r = re.sub(r"^\d+\s*\|\s*·\s*\|\s*", "", r.strip())  # rank prefix "12 | · | "
        r = re.sub(r"\s*\|\s*Show more.*$", "", r)
        if not r or r in seen or r.lower().startswith(("what's happening", "show more")):
            continue
        if "Promoted" in r or r.startswith("Ad |"):
            continue
        seen.add(r)
        keep.append(r)
    return keep


def recent_dispatches(hours: float, now: float | None = None,
                      reads_dir: Path = READS_DIR) -> list[Path]:
    now = now or time.time()
    files = [p for p in reads_dir.glob("*-x-feed-dispatch-*.md")
             if now - p.stat().st_mtime <= hours * 3600]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def scrub_dispatch(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    kept = []
    for line in text.splitlines():
        if line.startswith("# "):  # title: "X Feed Dispatch No. 81 — Sunday…" -> "Sunday…"
            line = re.sub(r"^# .*?Dispatch No\. \d+\s*[—-]\s*", "# ", line)
            kept.append(line)
            continue
        if PROVENANCE.match(line):  # "Window:", "*Window:*", "**Sources:**", "*Colophon…*"
            continue
        if not (META.search(line) or PRIVATE.search(line)):
            kept.append(line)
            continue
        prefix = re.match(r"^(\s*(?:>|[-*]|\d+\.)?\s*)", line).group(1)
        # Sentence-level on both patterns, so a private marker META does not
        # know about costs only its own sentence, not the news beside it.
        sentences = [c for c in (_keep(x) for x in SENTENCE.split(line[len(prefix):])) if c]
        if sentences:
            kept.append(prefix + " ".join(sentences))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def build(hours: float, trends: dict[str, list[str]] | None, trend_error: str | None,
          files: list[Path]) -> str:
    parts = [HEADER.format(when=time.strftime("%Y-%m-%d %H:%M %Z"))]
    parts.append("── TRENDING ON X ──")
    if trends:
        for tab, rows in trends.items():
            parts.append(f"[{tab}]")
            parts.extend(f"- {r}" for r in rows)
    else:
        parts.append(f"(unavailable this run: {trend_error or 'no rows'})")
    parts.append(f"\n── FEED READS (last {hours:g}h, newest first) ──")
    budget = TOTAL_DISPATCH_CHARS
    used = 0
    for p in files:
        if budget <= 0:
            break
        body = scrub_dispatch(p.read_text(errors="replace"))[:min(PER_DISPATCH_CHARS, budget)]
        parts.append(body + "\n")
        budget -= len(body)
        used += 1
    if not used:
        parts.append("(none in window)")
    text = "\n".join(parts) + "\n"
    leak = PRIVATE.search(text)  # should be unreachable; say so loudly if it is
    if leak:
        print(f"x_pulse: WARNING private-system marker survived the scrub: "
              f"{leak.group(0)!r}", file=sys.stderr)
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("-o", "--out", default=".tmp/x-pulse.md")
    ap.add_argument("--hours", type=float, default=30, help="dispatch look-back window")
    ap.add_argument("--no-trends", action="store_true")
    a = ap.parse_args()

    trends, err = None, None
    if not a.no_trends:
        try:
            trends = read_trends()
        except Exception as e:  # browser down, X markup change: degrade, don't fail
            # Type only in the brief: the message carries local paths, and the
            # brief is read by router-picked external models. Full text to log.
            err = type(e).__name__
            print(f"x_pulse: trending read failed: {type(e).__name__}: {e}", file=sys.stderr)
    files = recent_dispatches(a.hours)
    text = build(a.hours, trends, err, files)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(text)
    n_trends = sum(len(v) for v in (trends or {}).values())
    print(f"x_pulse: {n_trends} trend rows, {len(files)} feed reads -> {a.out} ({len(text)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
