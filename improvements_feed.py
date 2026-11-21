#!/usr/bin/env python3
"""improvements_feed.py — "What we improved" for the top of the show (Kyle, 2026-11-21).

The fleet improves itself; the show reports improvements already MADE, never asks Kyle to approve
anything. Source: ~/.observer/data/podcast-improvements.md, appended by the Fleet Optimizer as it
ships each upgrade. Entry format (one per block, blank-line separated):

    ## 2026-11-21 | one-line headline in plain, general words
    2-4 sentences: what changed, why it is better, the measured result. No repo/job/file names.

Each entry airs ONCE: aired headlines are recorded in .improvements-aired.json. Writes .tmp/improvements.md
(or removes it when nothing new). Never raises; always exits 0.
"""
import json
import re
import sys
from pathlib import Path

SRC = Path.home() / ".observer/data/podcast-improvements.md"
ROOT = Path(__file__).resolve().parent
AIRED = ROOT / ".improvements-aired.json"
OUT = ROOT / ".tmp/improvements.md"
MAX_ENTRIES = 4


def entries(text):
    out = []
    for blk in re.split(r"\n(?=## )", text.strip()):
        m = re.match(r"## (\d{4}-\d{2}-\d{2}) \| (.+)\n(.*)", blk.strip(), re.S)
        if m:
            out.append((m.group(1), m.group(2).strip(), " ".join(m.group(3).split())))
    return out


def main():
    try:
        OUT.parent.mkdir(exist_ok=True)
        OUT.unlink(missing_ok=True)
        if not SRC.exists():
            return 0
        aired = set(json.loads(AIRED.read_text())) if AIRED.exists() else set()
        new = [e for e in entries(SRC.read_text()) if e[1] not in aired][-MAX_ENTRIES:]
        if not new:
            return 0
        OUT.write_text("# WHAT WE IMPROVED (already done; report as done, never as a request)\n\n" +
                       "\n\n".join(f"- {h} ({d}): {b}" for d, h, b in new) + "\n")
        AIRED.write_text(json.dumps(sorted(aired | {h for _, h, _ in new})))
        print(f"improvements_feed: {len(new)} new")
    except Exception as e:  # noqa: BLE001
        print(f"improvements_feed: skipped ({e})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
