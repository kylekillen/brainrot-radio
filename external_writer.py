#!/usr/bin/env python3
"""external_writer.py — FREE external writer (ox-alpha via observer-system's
external_summon) for Killen Time episodes.

Kyle's ask (2026-08-22): a full episode that costs $0 Claude window. ox-alpha
is free through ~08-27 (see ~/observer-system/observer/dream/external_models.py).
This is the "external" PODCAST_ENGINE, alongside the existing claude/gemini
engines (see generate-episode.sh Step 2).

Why this can't just reuse the Claude write path's approach (an agentic `claude
-p` run that reads its own source files): external_summon's `--role` turns are
bound server-side to that role's REGISTERED workspace (observer-system resolves
it from the role registry, ignoring any cwd/--workspace argument — see
external_summon.py's module docstring). The `killen-time` role (display name
"Assay", the NOW/Substack editor) is registered against a DIFFERENT workspace
than this one, so its file tools can't see brainrot-radio's .tmp/ sources or
write brainrot-radio's scripts/ files. So, same as or_writer.py's OpenRouter
fallback, this script gathers the source material itself and inlines it into
ONE prompt, then treats the model as pure text-completion: no tool use for the
actual content, just "here is everything, produce the script text as your
final reply." Reuses or_writer.py's source-gathering, prompt templates, and
output-parsing wholesale — only the completion backend differs.

Dispatch primitive (verified live 2026-08-22, $0.0000/dispatch): observer-
system's OWN venv python (system python3 lacks the `mcp` module and crashes),
shelled out to as a subprocess so this script can keep running under
brainrot-radio's own venv (which has ingest.py's deps that observer-system's
venv lacks) for the source-gathering / save_covered_stories side.

Fail-loud discipline: never falls back to a provider that could silently bill
real money. On failure (after one retry, matching the Claude write path's own
retry-then-fallback shape) this exits non-zero and generate-episode.sh falls
back to the full Claude write path — which is $0 too (Max plan), just not the
free-week external win. If ox-alpha itself disappears (free window ends, or
gets renamed/removed from external_models.py), --list-models / dispatch will
fail cleanly and loudly here rather than quietly routing to a paid model.

Usage:
  python3 external_writer.py --pass 1 --script scripts/killen-time-2026-08-22.txt \
      --greeting "This is a morning episode ..."
  python3 external_writer.py --pass 2 --script scripts/killen-time-2026-08-22.txt \
      --greeting "..."

Exit 0 on a written/appended script; non-zero + stderr message on failure (the
caller — generate-episode.sh — falls back to the Claude write path).
"""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import or_writer  # reuse _gather_sources / _pass1_prompt / _pass2_prompt / parsing

ROOT = Path(__file__).resolve().parent
OBSERVER_PY = Path.home() / "observer-system" / ".venv" / "bin" / "python"
EXTERNAL_ROLE = "killen-time"
DEFAULT_MODEL = "ox-alpha"
DISPATCH_TIMEOUT_SEC = 1800
MIN_WORDS = 1500  # floor well below the 7000-9000 target — catches a truncated/short reply

TASK_PREAMBLE = """IMPORTANT — for THIS turn only, ignore whatever other persona or workspace this role usually carries. You are acting as a scriptwriter for a completely different show, Killen Time (a two-host news podcast). You have NO file tools relevant to this task — every source you need is inlined below in full. Do not attempt fs_read/fs_write/run_command for this task.

Protocol: first call turn_finalize with a one-sentence summary (required). THEN, in a separate subsequent message with NO further tool calls, output ONLY the requested script text below — no markdown fences, no "Here's the script:" preamble, no commentary before or after it. That final message's content becomes the episode script verbatim, so anything else in it airs on the show.

"""


def _dispatch(prompt: str, label: str) -> dict | None:
    """One external_summon dispatch. Returns the parsed JSON result dict, or
    None on any failure (subprocess crash, timeout, unparsable output, ok=false)."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as pf:
        pf.write(prompt)
        prompt_path = pf.name
    out_path = prompt_path + ".out"
    cmd = [
        str(OBSERVER_PY), "-m", "observer.dream.external_summon",
        "--role", EXTERNAL_ROLE, "--model", DEFAULT_MODEL,
        "--message-file", prompt_path, "--out", out_path,
        "--timeout-sec", str(DISPATCH_TIMEOUT_SEC), "--json",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(ROOT),
            timeout=DISPATCH_TIMEOUT_SEC + 120,
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write(f"external_writer: {label} subprocess wall-clock timeout\n")
        return None
    except OSError as e:
        sys.stderr.write(f"external_writer: {label} failed to spawn observer-system python: {e}\n")
        return None
    finally:
        Path(prompt_path).unlink(missing_ok=True)
        Path(out_path).unlink(missing_ok=True)
        Path(out_path + ".partial").unlink(missing_ok=True)

    data = None
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            break
    if data is None:
        sys.stderr.write(
            f"external_writer: {label} could not parse JSON from external_summon "
            f"(exit={proc.returncode}); stderr tail: {proc.stderr.strip()[-2000:]}\n"
        )
        return None
    if not data.get("ok"):
        sys.stderr.write(
            f"external_writer: {label} dispatch FAILED: {data.get('error')} "
            f"(footer: {data.get('footer')})\n"
        )
        return None
    sys.stderr.write(f"external_writer: {label} dispatch OK. {data.get('footer', '')}\n")
    return data


def _dispatch_with_retry(prompt: str, label: str) -> str | None:
    result = _dispatch(prompt, label)
    if result is None:
        sys.stderr.write(f"external_writer: {label} attempt 1 failed, retrying once...\n")
        time.sleep(15)
        result = _dispatch(prompt, f"{label}-retry")
    return result.get("reply") if result else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pass", dest="pass_no", type=int, choices=[1, 2], required=True)
    ap.add_argument("--script", required=True, help="path to the episode script file")
    ap.add_argument("--greeting", default="", help="time-of-day greeting hint")
    args = ap.parse_args()

    if not OBSERVER_PY.exists():
        sys.stderr.write(f"external_writer: observer-system venv python not found at {OBSERVER_PY}\n")
        sys.exit(1)

    script_path = Path(args.script)
    if not script_path.is_absolute():
        script_path = ROOT / script_path

    src = or_writer._gather_sources()
    if not src["topic_brief"]:
        sys.stderr.write("external_writer: no .tmp/topic-brief.txt — cannot write episode\n")
        sys.exit(1)

    if args.pass_no == 1:
        prompt = TASK_PREAMBLE + or_writer._pass1_prompt(src, args.greeting)
    else:
        if not script_path.exists():
            sys.stderr.write(f"external_writer: pass 2 needs an existing {script_path} (pass 1 output)\n")
            sys.exit(1)
        existing = script_path.read_text(errors="replace")
        prompt = TASK_PREAMBLE + or_writer._pass2_prompt(src, args.greeting, existing)

    sys.stderr.write(
        f"external_writer: pass {args.pass_no} via {EXTERNAL_ROLE}/{DEFAULT_MODEL} "
        f"(prompt ~{len(prompt)} chars)\n"
    )

    completion = _dispatch_with_retry(prompt, f"write-pass{args.pass_no}")
    if completion is None:
        sys.stderr.write(f"external_writer: pass {args.pass_no} failed after retry\n")
        sys.exit(1)

    covered = None
    if args.pass_no == 2:
        completion, covered = or_writer._extract_covered(completion)
    body = or_writer._clean_script(completion)
    if len(body.split()) < MIN_WORDS:
        sys.stderr.write(
            f"external_writer: pass {args.pass_no} reply too short "
            f"({len(body.split())} words, floor {MIN_WORDS}) — treating as failure\n"
        )
        sys.exit(1)

    if args.pass_no == 1:
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
                sys.stderr.write(f"external_writer: saved {len(covered['stories'])} covered stories\n")
            else:
                sys.stderr.write(
                    "external_writer: no parseable covered-stories trailer; relying on "
                    "source archiving (Step 5 safety net) for dedup\n"
                )
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"external_writer: save_covered_stories failed (non-fatal): {e}\n")

    words = len(body.split())
    sys.stderr.write(f"external_writer: pass {args.pass_no} wrote {words} words to {script_path}\n")


if __name__ == "__main__":
    main()
