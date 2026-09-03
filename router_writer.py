#!/usr/bin/env python3
"""router_writer.py — Killen Time writer dispatched through the fleet's model
router (``observer.router.choose``) instead of a hardcoded model.

Part of model-router brief 07 (pilot: podcast writer). ``generate-episode.sh``
gates all of this behind ``ROUTER_MODE`` (env or
``~/.observer/data/podcast-router-mode``, default "shadow"):
  off    — this script is never invoked; today's hardcoded-Claude write path
           runs exactly as before. Kill-switch.
  shadow — generate-episode.sh calls ``--choose`` only: log what the router
           WOULD have picked + its estimated cost, then write the episode
           with the incumbent (Claude) path unchanged.
  on     — generate-episode.sh calls ``--pass 1``/``--pass 2`` to actually
           write the episode with the router's pick. On ANY failure the
           caller falls back to the incumbent Claude path (this script never
           partially writes a script file it can't finish — see main()).

Two subcommands:
  --choose
      Resolve a Choice for the "podcast_segment" task class (sensitive=False
      — this is public daily-news content, see _assert_public_safe below) and
      print it as JSON (choice + a cost estimate read from the router table)
      to stdout. Every call also appends one line to the router's own
      decisions log (observer.router.choose's side effect) — this is the
      router "learning from itself" per the lead's directive.
  --pass N --script PATH --greeting "..." [--choice-file PATH]
      Reuses or_writer.py's source-gathering, prompt templates, and
      output-parsing (same shape as external_writer.py's reuse of it) — only
      the completion backend differs: instead of a hardcoded OpenRouter/
      external_summon call, the prompt is dispatched through
      ``observer.router.backends.get(choice.backend).run(prompt, choice.model)``.
      If --choice-file is given (generate-episode.sh always passes the file
      written by an earlier --choose so pass 1 and pass 2 use the SAME pick
      and choose() is logged exactly once per episode), that choice is reused
      instead of calling choose() again.

Why subprocess into observer-system's own venv rather than importing
observer.router directly: this repo's venv doesn't carry the router's deps
(litellm etc., pulled in lazily inside ExternalBackend.run), and
external_writer.py already established this pattern for the same reason
(OBSERVER_PY, see its module docstring) — reuse it rather than open a second
way to reach across repos.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import or_writer  # reuse _gather_sources / _pass1_prompt / _pass2_prompt / parsing / SYSTEM

ROOT = Path(__file__).resolve().parent
OBSERVER_PY = Path.home() / "observer-system" / ".venv" / "bin" / "python"
TABLE_PATH = Path.home() / ".observer" / "data" / "model-router.json"
TASK_CLASS = "podcast_segment"
DISPATCH_TIMEOUT_SEC = 1800

# GUARDRAILS.md row 1: never let internal fleet state reach a public artifact.
# The router's "external" backend can land on a trains_on_data provider (Kyle
# ruled 2026-09-02 that's fine for PUBLIC content) — so before any dispatch,
# assert the assembled prompt is built only from or_writer._gather_sources'
# allowlist (topic brief, transcripts, articles, build-pitches, recent
# scripts/covered-json — all public feed content) and carries no fleet
# internals. Structural (the gatherer never reads these files) AND asserted
# here so a future prompt-building change can't silently regress it.
FORBIDDEN_MARKERS = (
    "STATUS.md", "HANDOFF.md", "calibration.md", "INBOX.md",
    "router-decisions.jsonl", "TELEGRAM_BOT_TOKEN", "_API_KEY", "_TOKEN=",
)


def _assert_public_safe(prompt: str) -> None:
    hits = [m for m in FORBIDDEN_MARKERS if m in prompt]
    if hits:
        raise RuntimeError(
            f"router_writer: prompt contains forbidden internal-state marker(s) "
            f"{hits} — refusing to dispatch off-repo (episode content must stay "
            f"public-feed-only; see GUARDRAILS.md)"
        )


def _table_row(model: str, task_class: str = TASK_CLASS) -> dict | None:
    try:
        table = json.loads(TABLE_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    for row in table.get("classes", {}).get(task_class, []):
        if row.get("model") == model:
            return row
    return None


def resolve_choice() -> dict | None:
    """Ask the router for a pick. Returns
    {"model", "backend", "reason", "alternatives", "cost_usd_per_task",
    "max_plan_points", "trains_on_data"} or None on any failure — callers
    treat None as "router unavailable this episode" and proceed without it
    (shadow: nothing to log; on: falls back to incumbent)."""
    if not OBSERVER_PY.exists():
        sys.stderr.write(f"router_writer: observer-system venv python not found at {OBSERVER_PY}\n")
        return None
    code = (
        "from observer.router import choose; import json, dataclasses; "
        f"c = choose({TASK_CLASS!r}, sensitive=False); "
        "print(json.dumps(dataclasses.asdict(c)))"
    )
    try:
        proc = subprocess.run([str(OBSERVER_PY), "-c", code],
                              capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, OSError) as e:
        sys.stderr.write(f"router_writer: choose() subprocess failed: {e}\n")
        return None
    if proc.returncode != 0:
        sys.stderr.write(f"router_writer: choose() failed: {proc.stderr.strip()[-800:]}\n")
        return None
    try:
        choice = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as e:
        sys.stderr.write(f"router_writer: choose() produced unparsable output: {e}\n")
        return None

    row = _table_row(choice["model"]) or {}
    choice["cost_usd_per_task"] = row.get("cost_usd_per_task", 0.0)
    choice["max_plan_points"] = row.get("max_plan_points", 0.0)
    choice["trains_on_data"] = row.get("trains_on_data", False)
    return choice


def _dispatch(prompt: str, model: str, backend: str) -> dict:
    """Run backends.get(backend).run(prompt, model) inside observer-system's
    venv. Returns the RunResult as a dict; ok=False + an 'error' key on any
    failure (never raises for a backend-side failure — only a bug here would)."""
    _assert_public_safe(prompt)
    if not OBSERVER_PY.exists():
        return {"ok": False, "error": f"observer-system venv python not found at {OBSERVER_PY}"}

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as pf:
        pf.write(prompt)
        prompt_path = pf.name
    code = (
        "import json, dataclasses\n"
        "from observer.router import backends\n"
        f"p = open({prompt_path!r}).read()\n"
        f"r = backends.get({backend!r}).run(p, {model!r})\n"
        "print(json.dumps(dataclasses.asdict(r)))\n"
    )
    try:
        proc = subprocess.run([str(OBSERVER_PY), "-c", code],
                              capture_output=True, text=True,
                              timeout=DISPATCH_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"dispatch timed out after {DISPATCH_TIMEOUT_SEC}s"}
    except OSError as e:
        return {"ok": False, "error": f"failed to spawn observer-system python: {e}"}
    finally:
        Path(prompt_path).unlink(missing_ok=True)

    if proc.returncode != 0:
        return {"ok": False, "error": f"dispatch subprocess exited {proc.returncode}: {proc.stderr.strip()[-800:]}"}
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as e:
        return {"ok": False, "error": f"unparsable dispatch output: {e}; stderr tail: {proc.stderr.strip()[-500:]}"}


def _write_pass(pass_no: int, script_path: Path, greeting: str, choice: dict) -> dict:
    """One write pass via the router's pick. Returns the dispatch RunResult
    dict (ok True/False). Never partially writes script_path — writes/appends
    only after a successful, long-enough completion, same discipline as
    or_writer.py / external_writer.py so a failed router pass never corrupts
    the file the Claude fallback would otherwise complete."""
    src = or_writer._gather_sources()
    if not src["topic_brief"]:
        return {"ok": False, "error": "no .tmp/topic-brief.txt — cannot write episode"}

    if pass_no == 1:
        prompt = or_writer._pass1_prompt(src, greeting)
    else:
        if not script_path.exists():
            return {"ok": False, "error": f"pass 2 needs an existing {script_path} (pass 1 output)"}
        existing = script_path.read_text(errors="replace")
        prompt = or_writer._pass2_prompt(src, greeting, existing)
    prompt = or_writer.SYSTEM + "\n\n" + prompt

    sys.stderr.write(
        f"router_writer: pass {pass_no} via router pick model={choice['model']} "
        f"backend={choice['backend']} ({choice.get('reason', '')})\n"
    )
    result = _dispatch(prompt, choice["model"], choice["backend"])
    if not result.get("ok"):
        sys.stderr.write(f"router_writer: pass {pass_no} dispatch FAILED: {result.get('error')}\n")
        return result

    completion = result.get("output", "")
    covered = None
    if pass_no == 2:
        completion, covered = or_writer._extract_covered(completion)
    body = or_writer._clean_script(completion)
    if len(body.split()) < 500:
        result["ok"] = False
        result["error"] = f"completion too short ({len(body.split())} words)"
        sys.stderr.write(f"router_writer: pass {pass_no} {result['error']} — treating as failure\n")
        return result

    if pass_no == 1:
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(body + "\n")
    else:
        existing_tail = script_path.read_text(errors="replace").rstrip()
        ends_with_transition = existing_tail.endswith("[TRANSITION]")
        lines = body.split("\n")
        while lines and lines[0].strip() == "[TRANSITION]":
            lines.pop(0)
        body = "\n".join(lines).lstrip()
        join = "\n" if ends_with_transition else "\n[TRANSITION]\n"
        with open(script_path, "a") as f:
            f.write(join + body + "\n")
        try:
            from ingest import save_covered_stories
            if covered and covered.get("stories"):
                save_covered_stories(
                    covered.get("stories", []),
                    covered.get("segments") or {},
                    podcast_guids=covered.get("podcast_guids") or [],
                )
                sys.stderr.write(f"router_writer: saved {len(covered['stories'])} covered stories\n")
            else:
                sys.stderr.write(
                    "router_writer: no parseable covered-stories trailer; relying on "
                    "source archiving (Step 5 safety net) for dedup\n"
                )
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"router_writer: save_covered_stories failed (non-fatal): {e}\n")

    words = len(body.split())
    sys.stderr.write(f"router_writer: pass {pass_no} wrote {words} words to {script_path}\n")
    return result


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_mutually_exclusive_group(required=True)
    sub.add_argument("--choose", action="store_true", help="resolve + print the router's pick, do not write anything")
    sub.add_argument("--pass", dest="pass_no", type=int, choices=[1, 2], help="write this pass via the router's pick")
    ap.add_argument("--script", help="path to the episode script file (required with --pass)")
    ap.add_argument("--greeting", default="", help="time-of-day greeting hint")
    ap.add_argument("--choice-file", help="reuse a --choose JSON file instead of calling choose() again")
    ap.add_argument("--result-file", help="append this pass's dispatch RunResult (JSON line) here, for the caller's cost/measurement log")
    args = ap.parse_args()

    if args.choose:
        choice = resolve_choice()
        if choice is None:
            print(json.dumps({"error": "router unavailable"}))
            sys.exit(1)
        print(json.dumps({"task_class": TASK_CLASS, "choice": choice}))
        sys.exit(0)

    if not args.script:
        sys.stderr.write("router_writer: --pass requires --script\n")
        sys.exit(2)
    script_path = Path(args.script)
    if not script_path.is_absolute():
        script_path = ROOT / script_path

    choice = None
    if args.choice_file:
        try:
            choice = json.loads(Path(args.choice_file).read_text())["choice"]
        except (OSError, json.JSONDecodeError, KeyError) as e:
            sys.stderr.write(f"router_writer: bad --choice-file: {e}\n")
    if choice is None:
        choice = resolve_choice()
    if choice is None:
        sys.stderr.write("router_writer: no router pick available, cannot write via router\n")
        sys.exit(1)

    result = _write_pass(args.pass_no, script_path, args.greeting, choice)
    if args.result_file:
        record = {"pass": args.pass_no, "model": choice["model"], "backend": choice["backend"], **result}
        record.pop("output", None)  # the script text itself; not measurement data
        with open(args.result_file, "a") as f:
            f.write(json.dumps(record) + "\n")
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
