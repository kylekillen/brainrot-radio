#!/usr/bin/env python3
"""gemini_qc.py — Independent Outcome Grader for the all-Gemini episode.

The all-Gemini engine previously SKIPPED QC entirely: the writer applied its own
deterministic join-fixes and was otherwise trusted with no separate verification.
That is the exact failure the "Independent Outcome Grader" build pitch (2026-06-20)
and Matthew Berman's loop taxonomy warn about — a generator grading its own work
inherits its own blind spots. This restores QC for the Gemini show while keeping
it 100% Claude-free and $0 (free Gemini Flash).

Two layers, embracing both of Berman's loop principles:

  1. VERIFIABLE exit conditions (no model — a command returning a boolean):
     word-count floor, no consecutive same-speaker tags, no doubled [TRANSITION],
     no empty segments. Auto-fixes the seam defects via _fix_joins, then hard-FAILs
     on anything left.

  2. SEPARATE-CONTEXT grader (a FRESH Gemini context that sees ONLY the finished
     script + a compact dedup digest + the rubric — never the generation prompts).
     It cannot inherit the writer's blind spots because it never saw the writer's
     context. Emits MUST-FIX items + a greppable `QC VERDICT: PASS`/`FAIL`.

DETECTION + FLAG ONLY — this NEVER rewrites long-form content. An earlier version
auto-revised on FAIL, and the reviser DELETED content (reading "fix the MUST-FIX
items" as "cut them"), shrinking a renderable 6575-word script to 3856 and tripping
voice.py's hard 6000-word render floor — the episode failed to produce (2026-06-21).
QC must never hand voice.py a script shorter than the writer produced. So we apply
only the non-shrinking deterministic seam fix, grade for the flag/signal, and ship
the FULL script; the pipeline's QC_FAIL_ACTION gate decides what to do with a FAIL.

Usage:  GEMINI_OUT=scripts/killen-time-<date>.txt python3 gemini_qc.py
        python3 gemini_qc.py scripts/killen-time-<date>.txt
Exit 0 = PASS, 2 = FAIL (flagged, full script still shipped), 1 = error.
The final line on stdout is always `QC VERDICT: PASS` or `QC VERDICT: FAIL`.
"""
import os
import re
import sys
import pathlib

import or_complete
import or_writer as ow

WORD_FLOOR = int(os.getenv("QC_WORD_FLOOR", "5500"))


def _fix_joins(s: str) -> str:
    """Deterministic seam QC (copied from gemini_episode to avoid importing that
    module — it has no __main__ guard and generating an episode on import is a
    side effect). Collapse doubled [TRANSITION]; break consecutive same-speaker
    blocks at seams by flipping to the other host."""
    out, last_speaker = [], None
    for ln in s.split("\n"):
        t = ln.strip()
        if t == "[TRANSITION]":
            if out and out[-1].strip() == "[TRANSITION]":
                continue
            last_speaker = None
            out.append(ln)
            continue
        m = re.match(r"\[(BASIL|BROOKE)\]", t)
        if m:
            sp = m.group(1)
            if sp == last_speaker:
                other = "BROOKE" if sp == "BASIL" else "BASIL"
                ln = ln.replace(f"[{sp}]", f"[{other}]", 1)
                sp = other
            last_speaker = sp
        out.append(ln)
    return "\n".join(out)


def _target() -> pathlib.Path:
    if len(sys.argv) > 1:
        return pathlib.Path(sys.argv[1])
    env = os.getenv("GEMINI_OUT")
    if env:
        return pathlib.Path(env)
    raise SystemExit("gemini_qc: pass a script path or set GEMINI_OUT")


def deterministic_checks(script: str) -> list[str]:
    """Verifiable, model-free. Returns a list of hard violations (empty = clean)."""
    issues = []
    words = len(script.split())
    if words < WORD_FLOOR:
        issues.append(f"word count {words} below floor {WORD_FLOOR}")
    # consecutive same-speaker (after _fix_joins these should be gone; residual = real)
    last = None
    for ln in script.split("\n"):
        m = re.match(r"\[(BASIL|BROOKE)\]", ln.strip())
        if m:
            if m.group(1) == last:
                issues.append(f"consecutive same speaker [{m.group(1)}]: {ln.strip()[:60]}")
            last = m.group(1)
    if re.search(r"\[TRANSITION\]\s*\n\s*\[TRANSITION\]", script):
        issues.append("doubled [TRANSITION] tag")
    # empty/stub segment: a [SPEAKER] line followed immediately by another tag
    if re.search(r"\[(BASIL|BROOKE)\]\s*\n\s*\[(BASIL|BROOKE|TRANSITION)\]", script):
        issues.append("empty speaker turn (tag with no content)")
    return issues


def _dedup_digest() -> str:
    """Compact recent-episode context for the freshness check — the ONLY context
    the grader gets besides the script itself and the rubric."""
    src = ow._gather_sources()
    recent = ow._sources_block(src, include_recent_scripts=True)
    return recent[:12000]


GRADER_SYSTEM = (
    "You are an ADVERSARIAL quality reviewer for a daily two-host news podcast "
    "(hosts BASIL and BROOKE). You did NOT write this script and have no stake in "
    "it. Your job is to REFUTE it — find every place it repeats a prior episode, "
    "makes an unsupported claim, invents a quote or statistic, or breaks the "
    "two-host conversational flow. Be specific and cite the offending line. Default "
    "to skepticism: if a factual claim has no named source, flag it."
)


def grade(script: str, digest: str) -> tuple[str, str]:
    """Fresh-context grade. Returns (verdict, must_fix_text)."""
    prompt = (
        "Review the SCRIPT below against this rubric. For each failing item give the "
        "specific line and the fix.\n\n"
        "RUBRIC:\n"
        "1. FRESHNESS/DEDUP — no story, argument, quote, or fact that already appeared "
        "in the recent episodes / covered-facts digest. A new take on old facts is NOT "
        "fresh.\n"
        "2. SOURCING — every factual/numeric claim is attributed to a named source. No "
        "invented quotes, no fabricated numbers.\n"
        "3. COHERENCE — segments connect logically; no abrupt non-sequiturs at seams.\n"
        "4. VOICE — BASIL and BROOKE genuinely alternate; it reads like a conversation, "
        "not a monologue split in two.\n\n"
        "List MUST-FIX items (rubric-violating) first, then ADVISORY items. End with "
        "EXACTLY one line: `QC VERDICT: PASS` if there are zero MUST-FIX items, else "
        "`QC VERDICT: FAIL`.\n\n"
        f"=== RECENT EPISODES / COVERED FACTS (for the freshness check) ===\n{digest}\n\n"
        f"=== SCRIPT TO REVIEW ===\n{script}"
    )
    out = or_complete.complete(prompt, system=GRADER_SYSTEM, max_tokens=4000)
    m = re.search(r"QC VERDICT:\s*(PASS|FAIL)", out)
    verdict = m.group(1) if m else "FAIL"  # no parseable verdict → treat as FAIL
    return verdict, out


def main() -> int:
    # DETECTION + FLAG ONLY — never rewrite long-form content. An earlier version
    # auto-revised on FAIL; the reviser DELETED content (it reads "fix the MUST-FIX
    # items" as "cut them"), shrinking a renderable 6575-word script to 3856 and
    # tripping voice.py's hard 6000-word render floor — the episode failed to
    # produce (2026-06-21). QC must NEVER hand voice.py a script shorter than the
    # writer produced. So: apply only the non-shrinking deterministic seam fix,
    # grade for the flag/signal, and ship the FULL script. The pipeline's
    # publish/abort gate (QC_FAIL_ACTION) decides what to do with a FAIL verdict.
    path = _target()
    before = path.read_text()
    script = _fix_joins(before)  # non-destructive: only flips seam tags / collapses dupes
    path.write_text(script)
    # Hard guarantee: we never reduced the renderable length.
    if len(script.split()) < len(before.split()):
        path.write_text(before)
        script = before

    digest = _dedup_digest()
    det = deterministic_checks(script)
    verdict, report = grade(script, digest)
    det_block = ("\nDeterministic violations:\n- " + "\n- ".join(det)) if det else ""
    print(f"--- Gemini QC (detection-only) ---\n{report}{det_block}", file=sys.stderr)
    if verdict == "PASS" and not det:
        print("QC VERDICT: PASS")
        return 0
    print("QC VERDICT: FAIL")
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"gemini_qc error: {e}", file=sys.stderr)
        print("QC VERDICT: FAIL")
        sys.exit(1)
