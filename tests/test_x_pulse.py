"""X pulse (Kyle 2026-09-27): X trends + X-feed reads as a podcast source.

The feed reads are written for Kyle, not for air. These tests pin that the
scrub removes production-meta sentences while keeping the news in the same
line, and that a dead browser degrades instead of failing the run.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import x_pulse  # noqa: E402

SAMPLE = """# X Feed Dispatch No. 81 — Sunday afternoon, Week 1 close-out

<!--from: killen-time-->

Window: about 10:30am–2:30pm MT. First harvest pull returned only 27 posts.

This is new ground for this dispatch, caught here because a reaction thread pulled it back. OpenAI disclosed on Sept 26 that agents touched government sites.
- **Claude limits, printed as a Dispatch 78-window miss.** Peter Yang posted "limits went from barely usable to basically unlimited".
- jun_song: a deflation of the Muse reaction from the 09-25 KYLE-QUEUE note.
> DRAKE MAYE PANIC TWEET
Trump will host Amodei at the White House.
"""


def test_scrub_removes_meta_keeps_news():
    out = x_pulse.scrub_dispatch(SAMPLE)
    for banned in ("Dispatch", "dispatch", "harvest", "KYLE-QUEUE", "killen-time", "Window:"):
        assert banned not in out, banned
    assert out.startswith("# Sunday afternoon")
    assert "OpenAI disclosed on Sept 26" in out
    assert "DRAKE MAYE PANIC TWEET" in out
    assert "White House" in out


def test_trend_rows_deduped_and_rank_stripped():
    rows = ["12 | · | Sports · Trending | Dolphins", "12 | · | Sports · Trending | Dolphins",
            "Promoted | Buy stuff", "Jaguars Crush Patriots 35-6 | 4 hours ago · Sports · 39K posts"]
    assert x_pulse.clean_trend_rows(rows) == [
        "Sports · Trending | Dolphins", "Jaguars Crush Patriots 35-6 | 4 hours ago · Sports · 39K posts"]


def test_window_and_build_degrade(tmp_path):
    old = tmp_path / "2026-09-01-x-feed-dispatch-1.md"
    new = tmp_path / "2026-09-27-x-feed-dispatch-81.md"
    old.write_text("# old"); new.write_text(SAMPLE)
    os.utime(old, (time.time() - 5 * 86400,) * 2)
    files = x_pulse.recent_dispatches(30, reads_dir=tmp_path)
    assert files == [new]
    text = x_pulse.build(30, None, "ConnectionRefusedError", files)
    assert "unavailable this run: ConnectionRefusedError" in text
    assert "OpenAI disclosed" in text
    assert "NEVER mention dispatches" in text


def test_pipeline_appends_pulse_non_fatally():
    sh = open(os.path.join(os.path.dirname(x_pulse.__file__), "generate-episode.sh")).read()
    assert "python3 x_pulse.py -o .tmp/x-pulse.md" in sh
    assert "cat .tmp/x-pulse.md >> .tmp/topic-brief.txt" in sh
    assert "X pulse unavailable (non-fatal)" in sh


# The shapes below are lifted from the live dispatch corpus (No. 81 on 09-27,
# the italic Window/Colophon/Sources lines of 09-17 and 09-20). They are the
# ones the earlier fixture missed: the italic/bold Window block, the colophon
# and sources notes, and the "Forwarded to model-router" tails.
LIVE = """# X Feed Dispatch No. 81 — Sunday afternoon, Week 1 close-out

<!--from: killen-time-->

*Window: about 10:30am–2:30pm MT, Sunday 09-27. First harvest pull returned only 27 posts (known partial-load bug, see house memory); retry gave 223. Two beats dominate this window: NFL Sunday.*

*Colophon: written by the Killen Time editor on claude-sonnet-5 (workspace pin), verified at session start. Two thread pulls, three web searches, one page fetch, all quotes from the harvest.*

**Sources:** x-feed-read.py following --scrolls 35 (195 posts); x-feed-read.py thread on tszzl's status/209882069; one web search to verify Zvi's Substack piece's actual subject.

## Bill Simmons panics about Drake Maye, again

Bill Simmons (@BillSimmons, 391k views) posted the two words that are apparently a running bit:

> DRAKE MAYE PANIC TWEET

Greenblatt hadn't replied to any of the pushback as of this harvest. Forwarded to model-router.

- **Adam Schefter** (@AdamSchefter, 450.5k views — top by views this window): "Jets RB Breece Hall has been ruled out with a thigh injury." No argument attached, just the wire alert — covered per house rule since it's the window's most-viewed post.
- Kevin O'Connor (@KevinOConnor, 32k, this window) posted the Jokic side in numbers: Denver has been "+10.8 net rating with Nikola Jokic."
- **teo** (@teodorio, 21k views): a viral thread on dining alone at Michelin-starred restaurants. Thread unopened this window.
- **Joey Politano**: new data thread — "Over the last four years, America has lost more than 200k jobs in creative fields". Continues the AI-labor-market beat.

Nothing forwarded to model-router beyond the Greenblatt/METR item.
"""

BANNED = ("model-router", "killen-time", "Killen Time", "x-feed-read", "Colophon",
          "harvest", "house memory", "thread pull", "web search", "page fetch",
          "scrolls", "workspace pin", "session start", "forwarded", "unopened",
          "partial-load", "Window:")


def test_live_shaped_production_meta_is_scrubbed():
    out = x_pulse.scrub_dispatch(LIVE)
    for banned in BANNED:
        assert banned not in out, banned
    assert out.startswith("# Sunday afternoon")
    # the news — and the attribution the header tells the writer to keep —
    # survives the scrub, even from a line whose lead-in was all meta
    for kept in ("DRAKE MAYE PANIC TWEET", "Jets RB Breece Hall", "Adam Schefter",
                 "Kevin O'Connor", "+10.8 net rating", "Michelin-starred",
                 "200k jobs in creative fields"):
        assert kept in out, kept


def test_generated_pulse_carries_no_private_system(tmp_path):
    d = tmp_path / "2026-09-27-x-feed-dispatch-81.md"
    d.write_text(LIVE)
    text = x_pulse.build(30, {"news": ["Trump will host Amodei"]}, None, [d])
    # the header tells the writer to ignore "harvests"/"desk" on purpose, so
    # the whole-pulse check is for private markers only.
    for banned in ("model-router", "killen-time", "Killen Time", "x-feed-read",
                   "~/", "/bin/", "/Users/", "observer-system", ".observer/",
                   "Window:", "Colophon", "workspace pin"):
        assert banned not in text, banned
    assert x_pulse.PRIVATE.search(text) is None


def test_header_names_no_internal_tool_or_path():
    # the header itself goes into the writer brief, which router-picked
    # external models read (GUARDRAILS 2026-09-24).
    for banned in ("model-router", "~/", "/bin/", ".py", "x-feed-read"):
        assert banned not in x_pulse.HEADER, banned
