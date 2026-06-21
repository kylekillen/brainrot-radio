#!/usr/bin/env python3
"""gemini_qc.py — verification primitive for the all-Gemini episode (grade + checks).

A SEPARATE-CONTEXT grader: a fresh Gemini context sees the finished script, the
writer's ACTUAL source material, and a rubric — never the generation prompts — so it
can't inherit the writer's blind spots. Two layers:

  1. DETERMINISTIC checks (no model, boolean): word floor, no consecutive same-speaker
     tags, no doubled [TRANSITION], no empty turns.
  2. SOURCED grader: judges FABRICATION against the full source material (brief +
     transcripts + articles — NOT a 12K truncation, which was the bug that made it
     flag real back-half content as fabricated and fail every episode), DEDUP against
     previously-covered facts, and STRUCTURE. Emits a greppable `QC VERDICT: PASS/FAIL`.

This is the verification PRIMITIVE. The pipeline's repair/produce LOOP lives in
gemini_finalize.py (verify → repair → until publishable). The CLI here is detection +
flag only — it never rewrites/shrinks a script.

Usage:  GEMINI_OUT=scripts/killen-time-<date>.txt python3 gemini_qc.py
        python3 gemini_qc.py scripts/killen-time-<date>.txt
Exit 0 = PASS, 2 = FAIL (flagged; script unchanged), 1 = error.
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
            # collapse doubled transition even across blank lines (compare to the
            # last NON-BLANK emitted line) — seams produce blank-separated pairs.
            prev = next((x.strip() for x in reversed(out) if x.strip()), "")
            if prev == "[TRANSITION]":
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
    # consecutive same-speaker (after _fix_joins these should be gone; residual = real).
    # A [TRANSITION] is a valid speaker boundary — reset, so [BASIL]…[TRANSITION]…[BASIL]
    # is NOT flagged (matches _fix_joins semantics; otherwise it false-flags every seam).
    last = None
    for ln in script.split("\n"):
        t = ln.strip()
        if t == "[TRANSITION]":
            last = None
            continue
        m = re.match(r"\[(BASIL|BROOKE)\]", t)
        if m:
            if m.group(1) == last:
                issues.append(f"consecutive same speaker [{m.group(1)}]: {t[:60]}")
            last = m.group(1)
    if re.search(r"\[TRANSITION\]\s*\n\s*\[TRANSITION\]", script):
        issues.append("doubled [TRANSITION] tag")
    # empty/stub segment: a [SPEAKER] line followed immediately by another tag
    if re.search(r"\[(BASIL|BROOKE)\]\s*\n\s*\[(BASIL|BROOKE|TRANSITION)\]", script):
        issues.append("empty speaker turn (tag with no content)")
    return issues


SOURCE_CAP = int(os.getenv("QC_SOURCE_CAP", "500000"))
FRESHNESS_CAP = int(os.getenv("QC_FRESHNESS_CAP", "200000"))


def _source_material() -> str:
    """The ACTUAL source material the writer used — topic brief + build-pitch +
    transcripts + articles — the reference for the SOURCING check. Full, NOT a 12K
    slice: feeding only the first 12K chars (the top of a 33K brief, before the
    transcripts) was THE bug that made the grader flag real, sourced back-half content
    (sports/entertainment/economics) as fabricated and fail every episode. Gemini
    Flash's context easily holds the whole thing."""
    src = ow._gather_sources()
    parts = ["=== TODAY'S TOPIC BRIEF (.tmp/topic-brief.txt) ===\n" + src.get("topic_brief", "")]
    if src.get("build_pitches"):
        parts.append("=== BUILD-PITCH SUMMARY ===\n" + src["build_pitches"])
    for name, body in src.get("transcripts", []):
        parts.append(f"=== PODCAST TRANSCRIPT ({name}) ===\n{body}")
    for name, body in src.get("articles", []):
        parts.append(f"=== ARTICLE ({name}) ===\n{body}")
    return "\n\n".join(parts)[:SOURCE_CAP]


def _freshness_material() -> str:
    """Previously-covered facts + recent episode scripts — the reference for the
    DEDUP/freshness check (a SEPARATE concern from sourcing; conflating the two into
    one truncated blob was the other half of the bug)."""
    src = ow._gather_sources()
    # Drop the NEWEST covered file and the newest recent script — those are the
    # CURRENT episode's own records (covered-stories are saved before QC runs), and
    # including them makes the grader flag this episode as "already covered" by itself.
    covered = (src.get("covered") or [])[:-1]
    recent = (src.get("recent_scripts") or [])[:-1]
    parts = []
    if covered:
        parts.append("=== FACTS ALREADY COVERED IN PREVIOUS EPISODES ===\n"
                     + "\n\n".join(f"-- {n} --\n{b}" for n, b in covered))
    if recent:
        parts.append("=== RECENT EPISODE SCRIPTS ===\n"
                     + "\n\n".join(f"-- {n} --\n{b}" for n, b in recent))
    return "\n\n".join(parts)[:FRESHNESS_CAP]


GRADER_SYSTEM = (
    "You are a quality reviewer for a daily two-host news podcast (hosts BASIL and "
    "BROOKE). You are given the EXACT source material the writer was allowed to use. "
    "Your job is to catch genuine defects — claims with NO basis in the source "
    "material (fabrications), stories repeated from previous episodes, and broken "
    "two-host structure. Be precise: cite the offending line. Critically — a claim "
    "that traces to the source material, even loosely or via a transcript excerpt, is "
    "NOT a violation. Do NOT flag a claim merely because the script doesn't name its "
    "source out loud; check whether the FACT appears in the source material provided. "
    "Only escalate to MUST-FIX what genuinely cannot be supported by the sources."
)


def grade(script: str, sources: "str | None" = None,
          freshness: "str | None" = None) -> tuple[str, str]:
    """Fresh-context grade against the writer's ACTUAL sources. Returns (verdict, report)."""
    if sources is None:
        sources = _source_material()
    if freshness is None:
        freshness = _freshness_material()
    prompt = (
        "Review the SCRIPT against this rubric, using the SOURCE MATERIAL and the "
        "PREVIOUSLY-COVERED material below. For each failing item cite the line.\n\n"
        "RUBRIC — a MUST-FIX is ONLY one of:\n"
        "1. FABRICATION — a factual/numeric claim, quote, name, or story in the script "
        "that has NO basis anywhere in the SOURCE MATERIAL. (If the fact appears in the "
        "brief or a transcript, it is SOURCED — not a violation, even if the script "
        "doesn't say the source's name aloud.)\n"
        "2. DEDUP — a story/fact already present in the PREVIOUSLY-COVERED material, "
        "repeated with no genuinely new development.\n"
        "3. STRUCTURE — broken two-host format: consecutive same-speaker blocks, doubled "
        "[TRANSITION] tags, or empty turns.\n"
        "Everything else (a transition that could be smoother, a claim that could name "
        "its source, stylistic nits) is ADVISORY, not MUST-FIX.\n\n"
        "List MUST-FIX items first (or 'None'), then ADVISORY. End with EXACTLY one line: "
        "`QC VERDICT: PASS` if there are ZERO MUST-FIX items, else `QC VERDICT: FAIL`.\n\n"
        f"=== SOURCE MATERIAL (what the writer was allowed to use) ===\n{sources}\n\n"
        f"=== PREVIOUSLY COVERED (for the dedup check) ===\n{freshness}\n\n"
        f"=== SCRIPT TO REVIEW ===\n{script}"
    )
    out = or_complete.complete(prompt, system=GRADER_SYSTEM, max_tokens=4000)
    m = re.search(r"QC VERDICT:\s*(PASS|FAIL)", out)
    verdict = m.group(1) if m else "FAIL"  # no parseable verdict → treat as FAIL
    return verdict, out


def main() -> int:
    # DETECTION + FLAG ONLY — never rewrites/shrinks (the pipeline's repair lives in
    # gemini_finalize.py's goal loop). Applies the non-shrinking seam fix, grades
    # against the writer's full sources, prints the greppable verdict.
    path = _target()
    before = path.read_text()
    script = _fix_joins(before)
    path.write_text(script)
    if len(script.split()) < len(before.split()):
        path.write_text(before)
        script = before
    det = deterministic_checks(script)
    verdict, report = grade(script)
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
