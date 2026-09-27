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
