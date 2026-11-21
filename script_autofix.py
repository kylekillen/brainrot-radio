#!/usr/bin/env python3
"""script_autofix.py — deterministic repair of what script_guard.py finds, no model, no network.

Runs just before render so a QC that timed out (7 of 8 episodes, Nov 14-21) can no longer let
private names or same-speaker collisions reach the mic.

  * collision: two blocks in a row by the same host -> merged into ONE block (never flip the tag;
    flipping cascades). A [TRANSITION] between them is kept only if it is the run's only separator.
  * leak: any sentence containing a private-system marker (script_guard.LEAK_PATTERNS) is dropped.
    A block left empty is removed.

Fail-safe: never raises past main(); if the result would lose >5% of the words it writes nothing and
exits 3 so the guard flag still records the findings. Usage: script_autofix.py SCRIPT
"""
import re
import sys
from pathlib import Path

import script_guard as sg

_TAG = re.compile(r"^\[(BASIL|BROOKE|TRANSITION)\]\s*(.*)$")
_SENT = re.compile(r"(?<=[.!?])\s+")
_LEAK = re.compile("|".join(f"(?:{p})" for _, p in sg.LEAK_PATTERNS
                            if _ in ("internal_name", "private_system")), re.IGNORECASE)


def _blocks(text):
    """[(tag, body)] in order; text before the first tag is kept under tag None."""
    out = []
    for ln in text.split("\n"):
        m = _TAG.match(ln.strip())
        if m:
            out.append([m.group(1), m.group(2).strip()])
        elif out and ln.strip():
            out[-1][1] = (out[-1][1] + " " + ln.strip()).strip()
        elif not out and ln.strip():
            out.append([None, ln.strip()])
    return out


def drop_leaks(blocks):
    n = 0
    for b in blocks:
        if b[0] in ("BASIL", "BROOKE") and _LEAK.search(b[1]):
            keep = [s for s in _SENT.split(b[1]) if not _LEAK.search(s)]
            n += len(_SENT.split(b[1])) - len(keep)
            b[1] = " ".join(keep)
    return [b for b in blocks if not (b[0] in ("BASIL", "BROOKE") and not b[1])], n


def merge_collisions(blocks):
    out, merged = [], 0
    for b in blocks:
        if b[0] in ("BASIL", "BROOKE"):
            j = len(out) - 1
            while j >= 0 and out[j][0] == "TRANSITION":
                j -= 1
            if j >= 0 and out[j][0] == b[0]:
                out[j][1] = (out[j][1] + " " + b[1]).strip()
                del out[j + 1:]  # a transition inside a merged run is dropped
                merged += 1
                continue
        if b[0] == "TRANSITION" and out and out[-1][0] == "TRANSITION":
            continue
        out.append(list(b))
    return out, merged


def render(blocks):
    parts = []
    for tag, body in blocks:
        parts.append(f"[{tag}] {body}".rstrip() if tag else body)
    return "\n\n".join(parts) + "\n"


def fix(text):
    blocks = _blocks(text)
    blocks, leaks = drop_leaks(blocks)
    blocks, merged = merge_collisions(blocks)
    return render(blocks), leaks, merged


def main(argv=None):
    a = (argv or sys.argv)[1:]
    if len(a) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    p = Path(a[0])
    try:
        before = p.read_text()
        after, leaks, merged = fix(before)
        if not leaks and not merged:
            print("script_autofix: nothing to fix")
            return 0
        if len(after.split()) < 0.95 * len(before.split()):
            print("script_autofix: refused (would remove >5% of words)", file=sys.stderr)
            return 3
        p.write_text(after)
        print(f"script_autofix: dropped {leaks} leaking sentence(s), merged {merged} same-speaker block(s)")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"script_autofix: skipped ({e})", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
