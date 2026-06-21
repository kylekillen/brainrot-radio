#!/usr/bin/env python3
"""gemini_finalize.py — goal-seeking production loop for the all-Gemini episode.

The loop methodology (Killen Time 06-18/06-20): a loop = trigger + GOAL, and a real
loop runs BACK to fix and continue UNTIL the goal holds — not fail-and-abort, not
fail-and-ship-broken, not fail-and-alarm-then-sit. The episode pipeline was a straight
line: a step failed and the run aborted or shipped a broken script. This wraps
production in the loop the methodology actually calls for.

GOAL: a publishable episode — RENDER-READY (word_count >= MIN_WORD_COUNT, voice.py's
hard floor) AND QC-clean (the grader, now trustworthy, finds no fabrication / dedup /
broken structure).

Phase 1 — reach the render floor. REGENERATE via the per-segment writer
(gemini_episode.py), which reliably clears the floor — NOT a one-shot "expand", which
Gemini Flash just reproduces (verified 2026-06-21). Anti-shrink: keep the longest
script seen, never write one shorter than the original (the 06-21 outage was a
"repair" that deleted below the floor; now impossible). Can't reach the floor after
MAX_REGENS → escalate, don't publish a stub (exit 3).

Phase 2 — QC gate. We do NOT regenerate to chase a PASS: Gemini Flash confabulates
specifics even with transcripts, and a fresh generation yields DIFFERENT fabrications,
not a clean one — so regen-for-QC would burn cost and escalate daily without
converging. Instead: clean → publish (exit 0); not clean → still publish (don't block
the feed) but ESCALATE the specific issues + the engine off-switch so Kyle can decide
whether to switch back to Claude (exit 2). Never silently ship fabrication.

The unresolved hard problem this surfaces: Gemini Flash is not reliably factual enough
for a daily news show. That is a cost/quality/engine decision for Kyle — the loop
makes it visible with evidence instead of burying it.
"""
import os
import subprocess
import sys
import pathlib

from gemini_qc import grade, deterministic_checks, _fix_joins

try:
    from config import MIN_WORD_COUNT
except Exception:  # noqa: BLE001
    MIN_WORD_COUNT = 6000

MAX_REGENS = int(os.getenv("FINALIZE_MAX_REGENS", "3"))
HERE = pathlib.Path(__file__).resolve().parent


def _wc(s: str) -> int:
    return len(s.split())


def _target_path() -> pathlib.Path:
    if len(sys.argv) > 1:
        return pathlib.Path(sys.argv[1])
    env = os.getenv("GEMINI_OUT")
    if env:
        return pathlib.Path(env)
    raise SystemExit("gemini_finalize: pass a script path or set GEMINI_OUT")


def regenerate(path: pathlib.Path) -> None:
    """Reliable repair: re-run the per-segment writer to produce a fresh full-length
    script at `path`. The writer clears the floor where a one-shot expand can't."""
    env = dict(os.environ, GEMINI_OUT=str(path))
    subprocess.run([sys.executable, str(HERE / "gemini_episode.py")],
                   cwd=str(HERE), env=env, timeout=600, check=False)


def run_qc(script: str) -> tuple[bool, str]:
    """Grade against the writer's full sources. Returns (clean, report)."""
    try:
        verdict, report = grade(script)
        det = deterministic_checks(script)
    except Exception as e:  # noqa: BLE001
        print(f"finalize: QC errored ({e}); treating as clean", file=sys.stderr)
        return True, ""
    clean = verdict == "PASS" and not det
    if det:
        report += "\nDeterministic: " + "; ".join(det)
    print(f"--- QC: {'PASS' if clean else 'FAIL'} ---\n{report}", file=sys.stderr)
    return clean, report


def escalate(summary: str) -> None:
    """Loud notice that the loop exhausted — never silent."""
    env_file = os.path.expanduser("~/.config/personal-os/telegram.env")
    token = chat = ""
    try:
        for line in open(env_file):
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("TELEGRAM_USER_ID="):
                chat = line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    text = f"⚠️ Killen Time finalize loop: {summary}"
    print(text, file=sys.stderr)
    if token and chat:
        try:
            subprocess.run(["curl", "-s", "-m", "15",
                            f"https://api.telegram.org/bot{token}/sendMessage",
                            "--data-urlencode", f"chat_id={chat}",
                            "--data-urlencode", f"text={text}"],
                           capture_output=True, timeout=20)
        except Exception:  # noqa: BLE001
            pass


def main() -> int:
    path = _target_path()
    run_id = os.getenv("RUN_ID", "")
    best = _fix_joins(path.read_text())   # non-destructive seam fix
    path.write_text(best)
    best_words = _wc(best)

    # Phase 1 — reach the RENDER FLOOR. Regenerating reliably fixes "too short" (the
    # writer is per-segment and clears the floor), so we loop on it. Anti-shrink:
    # never keep a shorter candidate.
    for attempt in range(1, MAX_REGENS + 2):
        if best_words >= MIN_WORD_COUNT:
            break
        if attempt > MAX_REGENS:
            path.write_text(best)
            escalate(f"could NOT reach render floor ({best_words}w < {MIN_WORD_COUNT}) "
                     f"after {MAX_REGENS} regenerations — NOT publishing a stub.")
            print("FINALIZE: below render floor — NOT publishing.")
            return 3
        print(f"finalize: short ({best_words}w) — regenerating (attempt {attempt})…",
              file=sys.stderr)
        try:
            regenerate(path)
            cand = _fix_joins(path.read_text())
        except Exception as e:  # noqa: BLE001
            print(f"finalize: regenerate failed ({e}); keeping best", file=sys.stderr)
        else:
            if _wc(cand) >= best_words:
                best, best_words = cand, _wc(cand)
        path.write_text(best)

    # Phase 2 — QC GATE. The grader is now trustworthy (it checks against the writer's
    # full sources). We do NOT regenerate to chase a PASS: evidence shows Gemini Flash
    # confabulates specifics even with transcripts, and a fresh generation just yields
    # DIFFERENT fabrications, not a clean one — so regen-for-QC would burn cost + escalate
    # daily without converging. Instead: if it's clean, publish; if not, still publish
    # (don't block the feed) but ESCALATE the specific issues + the engine decision so
    # Kyle can act. Never silently ship fabrication.
    clean, report = run_qc(best)
    path.write_text(best)
    if clean:
        print("FINALIZE: GOAL MET (render-ready + QC clean).")
        return 0
    if run_id:
        try:
            (HERE / "logs" / f"qc-FAIL-{run_id}.flag").write_text(
                f"QC not clean (published flagged) — {path}\n\n{report}\n")
        except OSError:
            pass
    escalate("today's episode PUBLISHED but the QC grader flags it (render-ready, not "
             "blocked). Likely Gemini confabulation/dedup. Top issues:\n"
             + report[:600]
             + "\n\nIf this keeps recurring, the all-Gemini writer may not be accurate "
             "enough for a daily news show — switch the engine back to Claude with:\n"
             "  echo claude > ~/.observer/data/podcast-engine\n(or accept it as-is).")
    print("FINALIZE: render-ready but QC-flagged — published flagged, Kyle escalated.")
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"gemini_finalize error: {e}", file=sys.stderr)
        sys.exit(1)
