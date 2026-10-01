#!/usr/bin/env python3
"""episode_topup.py — the render-floor TOP-UP loop for the external/claude engines.

NOT to be confused with topup_writer.py, which landed on main at 11:07Z on 2026-10-01
as the manual rescue for the lost 10-01 episode. That one is a hand-run tool
(`--script … --out …`) that tops an ALREADY-SHORT script up after the fact, is what
rescue_publish.sh drives, and is load-bearing — this file does not touch it. This file is
the other half: the loop that runs INSIDE the daily pipeline, so the show never has to be
rescued at all.

The gap this closes (logged four times since 2026-09-25 and built on 2026-10-01): the
Gemini engine has had a goal-seeking verify → repair → re-verify loop since 06-18
(gemini_finalize.py), and the external/claude engines did not. They wrote once, QC'd
once, rendered — and if the script came out under voice.py's word floor the run aborted
and the day was lost. On 2026-10-01 that cost three consecutive episodes: the free lane
wrote 1,920 + 2,204 words = 4,084 speech words against a 6,000 floor.

THE GOAL is the same one the Gemini loop targets: a script voice.py will actually render.

    for attempt in 1..MAX_ATTEMPTS:
        if speech_words(script) >= MIN_WORD_COUNT: return 0      # GOAL MET
        dispatch an EXPANSION pass, told exactly how many words it is short,
        fed sources today's earlier passes did NOT use
    still short → flag file + loud log + non-zero exit (fail as today, but now LOUDER
    about having actually tried to repair it)

Three rules that are the difference between this working and not:

1. MEASURE WITH voice.py's parse_script(), NEVER `wc -w`. wc -w counts every
   [BASIL]/[BROOKE]/[TRANSITION] tag as a word and overstates the real render count by
   ~70-100 — which is exactly how a "6,040 words, safely over" script was really 5,968
   and died at the floor (status.d/2026-09-27/121042).

2. REUSE, DON'T REINVENT. Sources come from or_writer._gather_sources() (same brief,
   evidence rules, evidence ledger and 7-day aired digest the write passes saw);
   the free dispatch is external_writer._dispatch_with_retry (external_summon, $0) —
   the same primitive the external engine's own write passes use, so the external
   engine stays $0 and the Claude engine stays on its flat-rate pool.

3. NEVER SHRINK, NEVER SHIP PADDING, NEVER KILL THE SIGN-OFF. A candidate that comes
   back shorter is discarded (the 06-21 Gemini outage was a repair that deleted below
   the floor); a candidate too small to be real material is discarded too; and new
   segments are inserted BEFORE the episode's final block, so the show still ends on
   its own outro rather than trailing off into a top-up.

Do NOT be tempted to raise external_writer.MIN_WORDS as the fix. Per-pass length does not
predict the combined total, because pass 2 supplies the rest — runs with pass 1 under
3,000 that produced aired episodes: 09-26 (2,047 → 8,877), 09-09 (2,732), 09-27 (2,328
and 2,874). The repair loop is the fix; the per-pass floor is not.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import dedup_guard
import or_writer

try:
    from config import MIN_WORD_COUNT
except Exception:  # noqa: BLE001
    MIN_WORD_COUNT = 6000

ROOT = Path(__file__).resolve().parent
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "/Users/kylekillen/.local/bin/claude")

# The free/external lane produced ~1/4 of the words it was asked for on 2026-10-01
# (1,920 for a 7,000-9,000 ask). Asking for exactly the shortfall would therefore
# still leave the script short, so ask for a multiple and keep the margin bounded.
TARGET_MARGIN = 2.0
TARGET_EXTRA = 400
MAX_TARGET_WORDS = 9000
MAX_TOPUP_TRANSCRIPTS = 10
MAX_TOPUP_ARTICLES = 5
CLAUDE_TIMEOUT_SEC = 1500
# A reply this short is not material, it is a stub. Accepting it would let the loop "succeed"
# a few words at a time and burn its whole budget on padding — so it is discarded, same as
# the rescue tool's MIN_SEGMENT_WORDS (see topup_writer.py, which shipped the 10-01
# recovery and set this precedent).
MIN_USEFUL_ADDITION = 400


def speech_words(script_path) -> int:
    """voice.py's OWN render word count: speech segments only, speaker tags stripped.

    This is the single number voice.py gates on (voice.py:213-218), so it is the only
    number the loop may verify against. `wc -w` is wrong here on purpose — see the
    module docstring.
    """
    from voice import parse_script

    segments = parse_script(str(script_path))
    return sum(len(text.split()) for speaker, text in segments if speaker != "TRANSITION")


def speech_words_inline(text: str) -> int:
    """The same count over raw text, without touching the file on disk."""
    from voice import parse_script

    fd, name = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        segments = parse_script(name)
    finally:
        Path(name).unlink(missing_ok=True)
    return sum(len(t.split()) for s, t in segments if s != "TRANSITION")


def _write_pass_sources() -> dict:
    """or_writer's gathered sources — brief, evidence rules/ledger, aired digest."""
    return or_writer._gather_sources()


def _unused_sources(already_offered: set) -> tuple:
    """Sources in .tmp/ that today's write passes never inlined.

    `already_offered` starts as the exact files or_writer._gather_sources() handed the
    two write passes (the first MAX_TRANSCRIPTS/MAX_ARTICLES by sort order) and grows
    with each top-up attempt, so attempt 2 gets material attempt 1 did not see. These
    files are never archived until the episode airs (generate-episode.sh Step 5), which
    is what keeps unused material available to repair with.
    """
    tmp = or_writer.TMP
    transcripts = []
    if (tmp / "transcripts").exists():
        transcripts = [t for t in sorted((tmp / "transcripts").glob("*.txt"))
                       if t.stat().st_size >= or_writer.MIN_TRANSCRIPT_BYTES]
    articles = []
    if (tmp / "articles").exists():
        articles = sorted((tmp / "articles").glob("*.txt"))

    fresh_t = [t for t in transcripts if t.name not in already_offered]
    fresh_a = [a for a in articles if a.name not in already_offered]
    return fresh_t[:MAX_TOPUP_TRANSCRIPTS], fresh_a[:MAX_TOPUP_ARTICLES], len(fresh_t) + len(fresh_a)


def _segment_openers(script_text: str, limit: int = 40) -> str:
    """What the episode already covers, one line per block — so a top-up pass adds
    material instead of re-writing segments that are already on air."""
    out = []
    for block in dedup_guard.blocks(script_text):
        opener = " ".join(block.split()[:12])
        if opener:
            out.append(f"  · {opener}")
        if len(out) >= limit:
            break
    return "\n".join(out) if out else "  (script is empty)"


def build_prompt(src: dict, current: int, shortfall: int, target: int,
                 openers: str, for_claude: bool, script_path: Path) -> str:
    """The expansion pass. Reuses or_writer's sources block + format rules verbatim."""
    instruction = (
        f"=== YOUR TASK: TOP UP TODAY'S EPISODE — YOU ARE {shortfall:,} WORDS SHORT ===\n"
        f"voice.py's own parser counts {current:,} spoken words in the script so far "
        f"(speaker tags and [TRANSITION] lines are NOT words). The show refuses to render "
        f"anything under {MIN_WORD_COUNT:,} words, so today's episode is currently "
        f"UNRENDERABLE.\n\n"
        f"Write AT LEAST {target:,} words of NEW spoken material to close that gap.\n\n"
        "The sources inlined above are ones today's earlier passes did NOT use — unused "
        "material, deliberately held back for you. Work the items they support that the "
        "episode has not already covered.\n\n"
        "WHAT THE EPISODE ALREADY COVERS — do not repeat any of it:\n" + openers + "\n\n"
        "HARD RULES\n"
        "- APPEND ONLY. Never rewrite, summarise, shorten or delete existing text.\n"
        "- No intro, no outro, no sign-off: those already exist in the script.\n"
        "- Do not repeat any story, fact, quote or number already in the script, or "
        "anything that aired in the last 7 days (the digest above).\n"
        "- EVIDENCE RULES: an item labelled '(no transcript)' is blurb-only — two or "
        "three sentences from the blurb itself, never elaborated. Never state a number, "
        "quote, name or score you cannot point to in the provided text. If a source does "
        "not support more words, move to the NEXT source; never pad with invented detail.\n"
        "- Format (strict — TTS depends on it):\n" + or_writer.SYSTEM
    )

    if for_claude:
        delivery = (
            f"APPEND your new blocks to the existing script file {script_path} using the "
            "Edit tool. Do not overwrite, reformat or delete anything that is already "
            "there — the file must only ever grow."
        )
    else:
        delivery = (
            "Output ONLY the new script blocks: no markdown fences, no preamble, no "
            "commentary before or after, no explanation of what you did."
        )

    return f"""{or_writer._sources_block(src, include_recent_scripts=False)}

{instruction}

{delivery}"""


def _dispatch(prompt: str, mode: str, script_path: Path) -> str:
    """One expansion dispatch. Returns the model's text (claude writes the file itself,
    so its return value is only used for logging). Raises on failure."""
    if mode == "external":
        import external_writer

        reply = external_writer._dispatch_with_retry(prompt, "topup")
        if reply is None:
            raise RuntimeError("external_summon dispatch failed after its own retry")
        return reply

    proc = subprocess.run(
        [CLAUDE_BIN, "--dangerously-skip-permissions", "--model", "sonnet", "-p", prompt],
        cwd=str(ROOT), capture_output=True, text=True, timeout=CLAUDE_TIMEOUT_SEC,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude top-up step exited {proc.returncode}")
    return proc.stdout or ""


def insert_expansion(script_path: Path, body: str) -> int:
    """Insert an expansion block and return the words added.

    Inserted BEFORE the episode's final block, not appended after it: the last block is
    the outro/sign-off, and a top-up appended after it would leave the show ending on a
    repair instead of on its own close. (Same call as the manual rescue tool, which is
    what actually shipped the 10-01 recovery.) Joins on exactly one [TRANSITION] — the
    recurring two-pass seam defect.
    """
    body = or_writer._clean_script(body).strip()
    if not body:
        return 0
    lines = body.split("\n")
    while lines and lines[0].strip() == "[TRANSITION]":
        lines.pop(0)
    body = "\n".join(lines).strip()
    if not body:
        return 0
    added = speech_words_inline(body)
    if added < MIN_USEFUL_ADDITION:
        return 0

    original = script_path.read_text(errors="replace").rstrip("\n")
    src_lines = original.split("\n")
    last_t = max((i for i, l in enumerate(src_lines) if l.strip() == "[TRANSITION]"),
                 default=None)
    if last_t is None:
        merged = original + "\n\n[TRANSITION]\n\n" + body + "\n"
    else:
        merged = ("\n".join(src_lines[: last_t + 1]).rstrip()
                  + "\n\n" + body + "\n\n"
                  + "\n".join(src_lines[last_t + 1:]).lstrip("\n"))
    with open(script_path, "w") as f:
        f.write(merged.rstrip("\n") + "\n")
    return added


def top_up(script_path: Path, mode: str, phase: str, max_attempts: int,
           min_words: int) -> int:
    """The loop. Returns 0 when the render floor is met, 1 when the budget ran out."""
    src = _write_pass_sources()
    # Seed with what the two write passes already inlined: "unused" means never reached
    # a writer, not merely still on disk.
    already_offered = {name for name, _ in src["transcripts"]}
    already_offered |= {name for name, _ in src["articles"]}

    words_before = speech_words(script_path)
    print(f"topup: {phase} — script is {words_before:,} speech words "
          f"(floor {min_words:,})", file=sys.stderr)
    if words_before >= min_words:
        print(f"TOPUP met phase={phase} added=0 attempts=0 "
              f"words={words_before} floor={min_words}", file=sys.stdout)
        return 0

    added = 0
    for attempt in range(1, max_attempts + 1):
        shortfall = min_words - words_before
        target = min(int(shortfall * TARGET_MARGIN) + TARGET_EXTRA, MAX_TARGET_WORDS)
        topup_src = dict(src)
        fresh_t, fresh_a, pool = _unused_sources(already_offered)
        if pool == 0:
            # Everything in .tmp/ has been offered once. Re-offer rather than give up —
            # a second angle on today's material beats no episode — but say so loudly.
            already_offered = set()
            fresh_t, fresh_a, pool = _unused_sources(already_offered)
            print(f"topup: no unused sources left; re-offering today's sources "
                  f"({pool} files)", file=sys.stderr)
        topup_src["transcripts"] = [
            (t.name, or_writer._read(t, or_writer.TRANSCRIPT_CAP)) for t in fresh_t]
        topup_src["articles"] = [
            (a.name, or_writer._read(a, or_writer.ARTICLE_CAP)) for a in fresh_a]
        already_offered |= {t.name for t in fresh_t} | {a.name for a in fresh_a}

        print(f"topup: attempt {attempt}/{max_attempts} — {shortfall:,} words short, "
              f"asking for {target:,}, offering {len(fresh_t)} transcripts + "
              f"{len(fresh_a)} articles (mode={mode})", file=sys.stderr)

        before_text = script_path.read_text(errors="replace")
        prompt = build_prompt(topup_src, words_before, shortfall, target,
                              _segment_openers(before_text),
                              for_claude=(mode == "claude"), script_path=script_path)
        try:
            reply = _dispatch(prompt, mode, script_path)
        except Exception as e:  # noqa: BLE001
            print(f"topup: attempt {attempt} dispatch failed: {e}", file=sys.stderr)
            time.sleep(10)
            continue

        if mode != "claude":
            appended = insert_expansion(script_path, reply)
            if appended == 0:
                print(f"topup: attempt {attempt} returned nothing usable", file=sys.stderr)
        else:
            appended = 0

        # Anti-shrink: a repair must never make the script shorter (the 06-21 outage).
        after_text = script_path.read_text(errors="replace")
        if len(after_text.split()) < len(before_text.split()):
            print(f"topup: attempt {attempt} SHRANK the script — discarding it",
                  file=sys.stderr)
            script_path.write_text(before_text)
            continue

        words_now = speech_words(script_path)
        gained = words_now - words_before
        added += max(gained, 0)
        print(f"topup: attempt {attempt} took the script {words_before:,} → {words_now:,} "
              f"(+{gained:,})", file=sys.stderr)
        words_before = words_now
        if words_now >= min_words:
            print(f"TOPUP met phase={phase} added={added} attempts={attempt} "
                  f"words={words_now} floor={min_words}", file=sys.stdout)
            return 0

    words_final = speech_words(script_path)
    flag = ROOT / "logs" / f"topup-FAIL-{os.environ.get('RUN_ID', 'manual')}.flag"
    try:
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text(
            f"Render floor NOT reached after {max_attempts} top-up attempt(s).\n"
            f"  phase: {phase}   mode: {mode}\n"
            f"  speech words: {words_final:,} (floor {min_words:,}) "
            f"— still short {min_words - words_final:,}\n"
            f"  script: {script_path}\n"
            "  NOT publishing a short stub. The writer lane is producing far less than\n"
            "  the prompt asks for; see the run log for per-attempt word counts.\n"
        )
    except OSError:
        pass
    print(f"TOPUP exhausted phase={phase} added={added} attempts={max_attempts} "
          f"words={words_final} floor={min_words} flag={flag}", file=sys.stdout)
    print(f"topup: FAILED to reach the render floor ({words_final:,} < {min_words:,}) "
          f"after {max_attempts} attempt(s) — flag: {flag}", file=sys.stderr)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--script", required=True, help="path to the episode script")
    ap.add_argument("--mode", choices=["external", "claude"], default="external",
                    help="which lane writes the expansion (external = $0 external_summon)")
    ap.add_argument("--phase", default="topup", help="label for logs/state (e.g. writes, QC)")
    ap.add_argument("--max-attempts", type=int,
                    default=int(os.environ.get("TOPUP_MAX_ATTEMPTS", "2")))
    ap.add_argument("--min-words", type=int,
                    default=int(os.environ.get("TOPUP_MIN_WORDS", MIN_WORD_COUNT)))
    args = ap.parse_args()

    script_path = Path(args.script)
    if not script_path.is_absolute():
        script_path = ROOT / script_path
    if not script_path.exists():
        sys.stderr.write(f"topup_writer: no script at {script_path}\n")
        return 1

    return top_up(script_path, args.mode, args.phase, args.max_attempts, args.min_words)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"topup_writer error: {e}", file=sys.stderr)
        sys.exit(1)