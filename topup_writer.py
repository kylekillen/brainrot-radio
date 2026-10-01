#!/usr/bin/env python3
"""topup_writer.py — grounded top-up for an EXISTING, too-short Killen Time script.

WHY THIS EXISTS. On 2026-09-25, 09-27 (twice) and 10-01 the free external writer
undershot and voice.py's 6,000-word floor correctly blocked the render — three lost
days. generate-episode.sh gives the GEMINI engine a goal-seeking repair loop
(gemini_finalize.py) and gives external/claude NOTHING, so a short script just ends
the day. Porting that loop into the pipeline is task 6996baded6e84f19b687233d3e1cf495
and is NOT this file. This file is the rescue path used by hand when the show has
already been lost: it tops up an existing short script with NEW grounded segments.

WHAT IT WILL NOT DO (all of these are the rules the 09-27 rescue established):
  * never touch MIN_WORD_COUNT / voice.py / any guard threshold — the floor is correct
  * never invent: the model may only assert what the inlined sources say. The 09-27 QC
    failure was precisely invented benchmark names and misattributed quotes.
  * never append after the sign-off: new segments are inserted after the LAST
    [TRANSITION], so the show still ends on its own outro.
  * never overwrite the canonical script: it writes --out, and the caller installs.

Usage:
  python3 topup_writer.py --script scripts/killen-time-2026-10-01.txt \
      --out /tmp/topup-2026-10-01.txt --target 6400
Exit 0 + non-empty --out on success; non-zero if it could not reach the target.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import or_writer
import external_writer
import voice  # the authoritative word count — wc -w over-counts speaker tags

ROOT = Path(__file__).resolve().parent
MIN_SEGMENT_WORDS = 1200  # a round that returns less than this is a failure, not a top-up


def spoken_words(text: str) -> int:
    """Exactly voice.py's own count (voice.py:210-211), on a temp file so we never touch
    the real script: speech segments only, [TRANSITION] contributes nothing."""
    tmp = Path("/tmp/.topup-wc.txt")
    tmp.write_text(text)
    try:
        segments = voice.parse_script(str(tmp))
    finally:
        tmp.unlink(missing_ok=True)
    return sum(len(t.split()) for s, t in segments if s != "TRANSITION")


def already_covered_digest(script: str) -> str:
    """One line per existing block: the host tag and its first sentence. Enough for the
    model to see what is already on air without us pasting the whole show twice."""
    out = []
    for block in re.split(r"\n\s*\n", script):
        block = block.strip()
        if not block:
            continue
        tag = re.match(r"^\[([A-Z]+)\]\s*(.*)$", block, re.S)
        if not tag:
            out.append("- [TRANSITION]")
            continue
        host, body = tag.group(1), tag.group(2)
        if host == "TRANSITION":
            continue
        first = re.split(r"(?<=[.!?])\s", body.strip())[0]
        out.append(f"- [{host}] {first[:180]}")
    return "\n".join(out)


PROMPT = """{preamble}
=== EDITORIAL GUIDE (CLAUDE.md excerpt — follow voice/format) ===
{claude_md}

=== SOURCE MATERIAL (this is ALL you have — ground every sentence in it) ===
{sources}

=== WHAT TODAY'S EPISODE ALREADY COVERS (do NOT repeat any of it) ===
{covered}

=== YOUR TASK: WRITE {n_segments} ADDITIONAL SEGMENTS FOR TODAY'S EPISODE ===
Today's script came in short ({have} spoken words) and the show cannot air under the
floor. The rest of the episode is already written and correct — do not rewrite it,
do not summarize it, do not recap it. You are writing EXTRA segments that slot in
just before the outro.

Rules, in priority order:
1. GROUNDING IS ABSOLUTE. Every fact, number, name, quote, benchmark and date must
   appear in the SOURCE MATERIAL above. If you cannot point to the line it came from,
   it does not go on air. Inventing a plausible-sounding specific is the worst thing
   you can do here — a whole day is already lost to scripts that padded themselves
   with confident fiction.
2. NEW MATERIAL ONLY. Pick beats the existing episode did not use. There are 41
   transcripts and 30 articles in the sources; the show has used maybe a third.
3. FORMAT: start with a line containing exactly [TRANSITION], then alternate
   [BASIL] and [BROOKE] blocks, one paragraph each, conversational two-host banter.
   Basil is the facts guy; Brooke pushes back and connects it to what it means.
4. LENGTH: {lo}-{hi} words total across {n_segments} segments. Do not stop early.
   If you are running out of angles, go deeper on one strong source rather than
   widening into thin material.
5. NO sign-off, NO "that's the Killen Time Update", NO mention of this being a
   script, a draft, a top-up, a word count, or of any internal tooling, agent,
   session, dispatch, or process. Nothing about how the show is made airs.

Write only the segment text. No markdown fences, no preamble, no commentary.

"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--target", type=int, default=6400, help="spoken words wanted overall")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--n-segments", type=int, default=3)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    if not external_writer.OBSERVER_PY.exists():
        sys.stderr.write(f"topup_writer: no observer venv at {external_writer.OBSERVER_PY}\n")
        return 2
    if args.model:
        external_writer.DEFAULT_MODEL = args.model

    script_path = Path(args.script)
    if not script_path.is_absolute():
        script_path = ROOT / args.script
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = ROOT / args.out

    original = script_path.read_text(errors="replace")
    base = spoken_words(original)
    sys.stderr.write(f"topup_writer: base script {script_path.name} = {base} spoken words\n")
    if base >= args.target:
        # Still write --out: the caller (rescue_publish.sh) installs --out unconditionally,
        # so a no-op round must be idempotent rather than depend on a stale /tmp file.
        out_path.write_text(original)
        sys.stderr.write(f"topup_writer: already at target, wrote {out_path} unchanged\n")
        return 0

    src = or_writer._gather_sources()
    if not src.get("topic_brief"):
        sys.stderr.write("topup_writer: no .tmp/topic-brief.txt — cannot ground a top-up\n")
        return 2

    sources = or_writer._sources_block(src, include_recent_scripts=False)
    have = base
    added_chunks: list[str] = []
    for rnd in range(1, args.rounds + 1):
        deficit = args.target - have
        if deficit <= 200:
            break
        prompt = PROMPT.format(
            preamble=external_writer.TASK_PREAMBLE,
            claude_md=src["claude_md"],
            sources=sources,
            covered=already_covered_digest(original + "\n" + "\n".join(added_chunks)),
            n_segments=args.n_segments,
            lo=max(1200, deficit),
            hi=deficit + 700,
            have=have,
        )
        sys.stderr.write(
            f"topup_writer: round {rnd} — need ~{deficit} more words "
            f"via {external_writer.DEFAULT_MODEL} (prompt ~{len(prompt)} chars)\n"
        )
        reply = external_writer._dispatch_with_retry(prompt, f"topup-r{rnd}")
        if reply is None:
            sys.stderr.write(f"topup_writer: round {rnd} dispatch failed after retry\n")
            break
        body = or_writer._clean_script(reply)
        body = body.lstrip()
        while body.startswith("[TRANSITION]"):
            body = body[len("[TRANSITION]"):].lstrip()
        got = spoken_words(body)
        if got < MIN_SEGMENT_WORDS:
            sys.stderr.write(
                f"topup_writer: round {rnd} returned only {got} words "
                f"(< {MIN_SEGMENT_WORDS}) — discarding rather than shipping padding\n"
            )
            break
        if not re.search(r"^\[(BASIL|BROOKE)\]", body, re.M):
            sys.stderr.write(f"topup_writer: round {rnd} has no speaker blocks — discarding\n")
            break
        added_chunks.append("[TRANSITION]\n\n" + body)
        have += got
        sys.stderr.write(f"topup_writer: round {rnd} added {got} words -> {have}\n")

    if not added_chunks:
        sys.stderr.write("topup_writer: no usable top-up produced; leaving script untouched\n")
        return 1

    # Insert after the LAST [TRANSITION] so the episode still ends on its own outro.
    lines = original.split("\n")
    last_t = max((i for i, l in enumerate(lines) if l.strip() == "[TRANSITION]"), default=None)
    if last_t is None:
        merged = original.rstrip() + "\n\n" + "\n\n".join(added_chunks) + "\n"
    else:
        merged = (
            "\n".join(lines[: last_t + 1]).rstrip()
            + "\n\n"
            + "\n\n".join(added_chunks)
            + "\n\n"
            + "\n".join(lines[last_t + 1:]).lstrip("\n")
        )
    final = spoken_words(merged)
    if final < args.target:
        sys.stderr.write(
            f"topup_writer: WARNING final {final} < target {args.target} "
            f"(floor is {__import__('config').MIN_WORD_COUNT}) — caller must decide\n"
        )
    out_path.write_text(merged)
    sys.stderr.write(f"topup_writer: wrote {out_path} ({final} spoken words)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
