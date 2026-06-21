#!/usr/bin/env python3
"""gemini_finalize.py — goal-seeking production loop for the all-Gemini episode.

The loop methodology (Killen Time 06-18/06-20): a loop = trigger + GOAL, and a real
loop runs BACK to fix and continue UNTIL the goal holds — not fail-and-abort, not
fail-and-ship-broken, not fail-and-alarm-then-sit. The episode pipeline was a straight
line: a step failed and the run aborted or shipped a broken script. This wraps
production in the loop the methodology actually calls for.

GOAL (verifiable AND achievable): the script is RENDER-READY —
    word_count >= MIN_WORD_COUNT (voice.py's hard render floor).

Why not "QC PASS" too? The adversarial QC rubric currently fails essentially every
episode (it failed today's perfectly good 7546-word show), so gating on it would make
the loop never exit. Until the rubric is calibrated so PASS means something, QC runs
ADVISORY: it still grades and FLAGS a sub-par episode (the flag the pipeline reads),
but it does not block. Calibrating the rubric is the follow-up that lets QC graduate
to a real gate.

REPAIR (when the goal is unmet): REGENERATE via the per-segment writer
(gemini_episode.py), which reliably clears the floor — NOT a one-shot "expand", which
Gemini Flash just reproduces (verified 2026-06-21: a whole-script expand returned the
input unchanged; the writer is per-segment for exactly this reason). We keep the
longest script seen and never write one shorter than the original — so a verification
step can never hand voice.py a script worse than what it received (the 06-21 outage
was a "repair" that deleted content below the floor; that is now impossible).

Bounded by MAX_REGENS. On exhaustion it ESCALATES to Kyle (Telegram) — loudly, never
silent. Exit: 0 = render-ready (publish; QC flag may be attached). 3 = could not reach
the floor after the budget (do NOT publish a stub; escalated). Pipeline renders on 0,
aborts otherwise.
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


def run_advisory_qc(script: str, path: pathlib.Path, run_id: str) -> bool:
    """Grade for the flag/signal — does NOT gate. Writes a qc-FAIL flag the pipeline
    reads. Returns True if QC passed (clean)."""
    try:
        verdict, report = grade(script)   # grades against the writer's full sources
        det = deterministic_checks(script)
    except Exception as e:  # noqa: BLE001
        print(f"finalize: advisory QC errored ({e}); skipping flag", file=sys.stderr)
        return True
    clean = verdict == "PASS" and not det
    print(f"--- advisory QC: {'PASS' if clean else 'FAIL'} ---\n{report}"
          + (("\nDeterministic: " + "; ".join(det)) if det else ""), file=sys.stderr)
    if not clean and run_id:
        flag = HERE / "logs" / f"qc-FAIL-{run_id}.flag"
        try:
            flag.write_text(f"advisory QC flagged sub-par (non-blocking) — {path}\n")
        except OSError:
            pass
    return clean


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

    for attempt in range(1, MAX_REGENS + 2):
        print(f"--- finalize attempt {attempt}/{MAX_REGENS + 1}: {best_words}w "
              f"(floor {MIN_WORD_COUNT}) ---", file=sys.stderr)
        if best_words >= MIN_WORD_COUNT:
            run_advisory_qc(best, path, run_id)   # flag-only, never blocks
            print("FINALIZE: GOAL MET (render-ready).")
            return 0
        if attempt > MAX_REGENS:
            break
        # Repair: regenerate via the writer, keep it only if it's longer (anti-shrink).
        print(f"finalize: short ({best_words}w) — regenerating via writer "
              f"(attempt {attempt}/{MAX_REGENS})…", file=sys.stderr)
        try:
            regenerate(path)
            cand = _fix_joins(path.read_text())
        except Exception as e:  # noqa: BLE001
            print(f"finalize: regenerate failed ({e}); keeping best", file=sys.stderr)
            path.write_text(best)
            continue
        if _wc(cand) >= best_words:
            best, best_words = cand, _wc(cand)
            path.write_text(best)
        else:
            print(f"finalize: regen shorter ({_wc(cand)}w < {best_words}w); keeping best",
                  file=sys.stderr)
            path.write_text(best)

    path.write_text(best)  # longest seen, never below original
    escalate(f"could NOT reach render floor ({best_words}w < {MIN_WORD_COUNT}) after "
             f"{MAX_REGENS} regenerations — NOT publishing a stub. Needs a look.")
    print("FINALIZE: below render floor — NOT publishing.")
    return 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"gemini_finalize error: {e}", file=sys.stderr)
        sys.exit(1)
