#!/usr/bin/env python3
"""story_research.py — research headline-only stories before the writer sees them.

Kyle, 2026-10-22: "No more headlines only stories. If a headline is interesting
research the story. Don't just say you saw a headline and that's all you have."

Until this step the brief handed writers ~40 Techmeme/HN/trade-press items whose
only text was the headline restated, and the evidence rules (correctly) forbade
elaborating on them — so the show aired "that's all the headline gives us" a
dozen times an episode. The fix is upstream: get the story, or cut it.

For every numbered item in .tmp/topic-brief.txt (above the X PULSE block) that
has no full text and no transcript:
  * fetch the item's own article URL if it has one (HN "Article URL:"), then
    web-search the headline and fetch the top non-paywalled results;
  * keep prose that actually matches the headline; if enough survives, replace
    the blurb with it and relabel the item `Type: researched (full text from N
    web sources)` — every writer engine reads the brief, so they all get it;
  * otherwise DROP the item from the brief. A story we could not research does
    not go on air.
Podcast items labelled "(no transcript)" are dropped too: web coverage of a topic
is not evidence of what was said on an episode.

Search/fetch reuse the fleet's web tools (observer-system observer/mcp/web_tools.py:
DDG/Octen search, httpx fetch, on-disk cache) rather than a second scraper. Run it
with the observer-system venv python. Never aborts the pipeline: on any failure
the brief is left untouched and the run continues (exit 0 with a loud log line).

    story_research.py [--brief .tmp/topic-brief.txt] [--max-research 24] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OBSERVER = Path.home() / "observer-system"
sys.path.insert(0, str(OBSERVER))

ITEM_RE = re.compile(r"^## (\d+)\. (.+)$", re.M)
BANNER = "═══"
# Hosts whose pages are aggregators, social posts or hard paywalls: fetching
# them yields chrome, a login wall, or the same headline again.
SKIP_HOSTS = (
    "techmeme.com", "news.ycombinator.com", "x.com", "twitter.com", "youtube.com",
    "reddit.com", "facebook.com", "instagram.com", "linkedin.com", "tiktok.com",
    "bloomberg.com", "wsj.com", "ft.com", "nytimes.com", "theinformation.com",
    "economist.com", "barrons.com", "msn.com",
)
STOP = set("""a an the and or of to in on for with by at from as is are was were be been
it its this that these those into over after before about up out new says said say
will would could can may might has have had not no but than then so via per more
most how why what who when where which amid just also report reports""".split())
PROSE_MIN_WORDS = 12        # a line shorter than this is nav chrome, captions, bylines
ITEM_MIN_WORDS = 180        # researched prose needed before an item may air
PER_SOURCE_CHARS = 1600     # per-item budget ~3.5KB: 30 researched items add ~25k tokens,
MAX_SOURCES = 2             # not 100k — free-lane writers have small contexts
SNIPPET_CHARS = 220
FETCH_CHARS = 40000


def _title_terms(title: str) -> set[str]:
    t = re.sub(r"\(([^()]*/[^()]*)\)\s*$", "", title)      # "(Name/Outlet)" byline
    t = re.sub(r"^\[[^\]]+\]\s*", "", t)                     # "[AINews]" prefix
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9.'-]*", t.lower())
    return {w.strip(".'-") for w in words if len(w) > 2 and w not in STOP}


def search_query(title: str) -> str:
    t = re.sub(r"\(([^()]*/[^()]*)\)\s*$", "", title)
    t = re.sub(r"^\[[^\]]+\]\s*", "", t)
    return re.sub(r"\s+", " ", t).strip()[:220]


def prose(text: str) -> str:
    keep = [ln.strip() for ln in text.splitlines() if len(ln.split()) >= PROSE_MIN_WORDS]
    out, seen = [], set()
    for ln in keep:
        k = ln[:80]
        if k not in seen:
            seen.add(k)
            out.append(ln)
    return "\n".join(out)


def relevant(text: str, terms: set[str]) -> bool:
    if not terms:
        return False
    low = text.lower()
    hit = sum(1 for w in terms if w in low)
    return hit / len(terms) >= 0.5


def _host_ok(url: str) -> bool:
    return url.startswith("http") and not any(h in url for h in SKIP_HOSTS)


def parse_brief(text: str):
    """-> (head, [(num, title, body)], tail). tail starts at the first banner after item 1."""
    first = ITEM_RE.search(text)
    if not first:
        return text, [], ""
    bpos = text.find(BANNER, first.start())
    main, tail = (text[:bpos], text[bpos:]) if bpos != -1 else (text, "")
    head = main[: first.start()]
    ms = list(ITEM_RE.finditer(main))
    items = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(main)
        items.append((m.group(1), m.group(2), main[m.start():end]))
    return head, items, tail


def classify(body: str) -> str:
    t = re.search(r"^Type: (.+)$", body, re.M)
    kind = t.group(1) if t else ""
    if "Full article:" in body or "full text" in kind or "transcript available" in kind:
        return "has_text"
    if "no transcript" in kind:
        return "podcast_no_transcript"
    return "thin"


def research(title: str, body: str, search_fn, fetch_fn) -> dict:
    terms = _title_terms(title)
    urls: list[str] = []
    m = re.search(r"Article URL: (\S+)", body)
    if m and _host_ok(m.group(1)):
        urls.append(m.group(1))
    lk = re.search(r"^Link: (\S+)", body, re.M)
    if lk and _host_ok(lk.group(1)) and lk.group(1) not in urls:
        urls.append(lk.group(1))
    snippets: list[str] = []
    try:
        res = search_fn(search_query(title), 8)
        for r in res.get("results", []):
            u = r.get("url", "")
            if _host_ok(u) and u not in urls:
                urls.append(u)
            sn = (r.get("snippet") or "").strip()
            if sn and u:
                snippets.append(f"- {r.get('title','').strip()} ({u}): {sn[:SNIPPET_CHARS]}")
    except Exception as exc:  # noqa: BLE001
        snippets.append(f"[search failed: {exc}]")
    sources = []
    for u in urls[:6]:
        if len(sources) >= MAX_SOURCES:
            break
        try:
            page = fetch_fn(u, FETCH_CHARS)
        except Exception:  # noqa: BLE001 — paywall, 403, timeout: try the next one
            continue
        p = prose(page.get("text", ""))
        if len(p.split()) >= 80 and relevant(p, terms):
            sources.append((u, p[:PER_SOURCE_CHARS]))
    words = sum(len(p.split()) for _, p in sources)  # counted on what the writer gets
    return {"sources": sources, "snippets": snippets[:3], "words": words,
            "ok": words >= ITEM_MIN_WORDS}


def rewrite_item(body: str, r: dict) -> str:
    lines = body.split("\n")
    header = lines[0]
    meta = [ln for ln in lines[1:] if re.match(r"^(Source|Weights|Link|Type):", ln)]
    meta = [ln for ln in meta if not ln.startswith("Type:")]
    meta.append(f"Type: researched (full text from {len(r['sources'])} web sources)")
    out = [header, *meta, "",
           "RESEARCHED STORY — fetched from the web when this brief was built. This is your "
           "evidence for this item; report what these sources say and attribute it to them.", ""]
    for u, p in r["sources"]:
        out += [f"[source: {u}]", p, ""]
    if r["snippets"]:
        out += ["Other coverage (search-result summaries):", *r["snippets"], ""]
    return "\n".join(out) + "\n---\n\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brief", default=str(ROOT / ".tmp" / "topic-brief.txt"))
    ap.add_argument("--max-research", type=int, default=40,
                    help="research the top-N thin items by brief rank; thin items below are dropped")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    brief = Path(a.brief)
    try:
        from observer.mcp import web_tools  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        print(f"story_research: LOUD: cannot import fleet web_tools ({exc}); brief left as-is — "
              "headline-only items WILL reach the writer today", file=sys.stderr)
        return 0
    text = brief.read_text()
    head, items, tail = parse_brief(text)
    thin = [(n, t, b) for n, t, b in items if classify(b) == "thin"]
    to_research = thin[: a.max_research]
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        results = dict(zip(
            [n for n, _, _ in to_research],
            ex.map(lambda x: research(x[1], x[2], web_tools.web_search, web_tools.web_fetch), to_research),
        ))
    out_items, report = [], {"researched": [], "dropped": []}
    for n, t, b in items:
        kind = classify(b)
        if kind == "has_text":
            out_items.append(b)
        elif kind == "podcast_no_transcript":
            report["dropped"].append({"n": n, "title": t, "why": "podcast, no transcript"})
        elif n in results and results[n]["ok"]:
            out_items.append(rewrite_item(b, results[n]))
            report["researched"].append({"n": n, "title": t, "words": results[n]["words"],
                                         "sources": [u for u, _ in results[n]["sources"]]})
        else:
            why = (f"research found {results[n]['words']} usable words" if n in results
                   else f"below research cutoff (top {a.max_research} thin items)")
            report["dropped"].append({"n": n, "title": t, "why": why})
    new = head + "".join(out_items) + tail
    report["seconds"] = round(time.time() - t0, 1)
    (brief.parent / "research-report.json").write_text(json.dumps(report, indent=1))
    print(f"story_research: {len(report['researched'])} researched, {len(report['dropped'])} dropped, "
          f"{len(items) - len(thin) - sum(1 for d in report['dropped'] if d['why'].startswith('podcast'))} "
          f"already had text, {report['seconds']}s", file=sys.stderr)
    for d in report["dropped"]:
        print(f"  dropped #{d['n']}: {d['title'][:80]} — {d['why']}", file=sys.stderr)
    if not a.dry_run:
        brief.with_suffix(".pre-research.txt").write_text(text)
        brief.write_text(new)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 — never kill the episode run
        print(f"story_research: LOUD: crashed ({type(exc).__name__}: {exc}); brief left as-is", file=sys.stderr)
        sys.exit(0)
