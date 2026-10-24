#!/usr/bin/env python3
"""Per-beat coverage ledger — the "no silent gaps" contract for the beat fan-out.

Every beat reporter records what it actually produced in
`.tmp/beats/<beat>.status.json`:

    {"beat": "nba_sports", "status": "ok", "reason": "write-pass2 complete",
     "date": "2026-10-24", "updated": "2026-10-24T05:12:03"}

status is one of ok | failed | empty. A beat whose status is missing, stale
(written on a different run date) or not `ok` is a GAP, unless the script itself
carries an explicit not-covered line:

    [NOT COVERED: nba_sports — no fresh material today]

`check` is the gate /qc-episode runs: it fails (exit 1) when any beat in
beats.json is neither ok nor explicitly not-covered. voice.py strips every
[NOT COVERED: ...] line before rendering, so the annotation never reaches audio.

CLI:
    python3 beat_ledger.py reset
    python3 beat_ledger.py mark --beats ai_tech agentic_systems --status ok \\
        --reason "write-pass1 complete"
    python3 beat_ledger.py check scripts/killen-time-2026-10-24.txt --today 2026-10-24
    python3 beat_ledger.py show --today 2026-10-24
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VALID_STATUSES = ("ok", "failed", "empty")
NOT_COVERED_RE = re.compile(r"^\[NOT COVERED:\s*([A-Za-z0-9_]+)", re.MULTILINE)


def ledger_dir() -> Path:
    """Ledger location. Overridable so tests never touch the live .tmp/beats."""
    return Path(os.getenv("BEAT_LEDGER_DIR") or (ROOT / ".tmp" / "beats"))


def required_beats(beats_json: Path | None = None) -> list[str]:
    """Every beat in beats.json must be accounted for (ok or not-covered).

    All of them, including the optional/back-half ones: marking a beat
    not-covered is one cheap line, and that is the whole point of the ledger.
    """
    path = beats_json or (ROOT / "beats.json")
    try:
        data = json.loads(path.read_text())
        beats = [b["id"] for b in data.get("beats", []) if b.get("id")]
        if beats:
            return beats
    except (OSError, ValueError, KeyError):
        pass
    # Hardcoded fallback so a broken beats.json cannot silently disable the gate.
    return ["ai_tech", "agentic_systems", "claude_lab", "nba_sports",
            "entertainment", "economics_culture", "prediction_markets"]


def status_path(beat: str, directory: Path | None = None) -> Path:
    return (directory or ledger_dir()) / f"{beat}.status.json"


def write(beat: str, status: str, reason: str = "", run_date: str | None = None,
          directory: Path | None = None) -> Path:
    """Atomically write one beat's status file."""
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {VALID_STATUSES}, got {status!r}")
    d = directory or ledger_dir()
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "beat": beat,
        "status": status,
        "reason": reason,
        "date": run_date or date.today().isoformat(),
        "updated": datetime.now().isoformat(timespec="seconds"),
    }
    target = status_path(beat, d)
    # Write-then-rename: a torn status file would read as a gap or a false ok.
    fd, tmp = tempfile.mkstemp(dir=str(d), prefix=f".{beat}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return target


def read_all(run_date: str | None = None, directory: Path | None = None) -> dict[str, dict]:
    """Read every status file. A file whose date != run_date is stale and withheld."""
    d = directory or ledger_dir()
    out: dict[str, dict] = {}
    if not d.is_dir():
        return out
    want = run_date or date.today().isoformat()
    for path in sorted(d.glob("*.status.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        beat = data.get("beat") or path.name[: -len(".status.json")]
        if data.get("date") != want:
            continue  # yesterday's ok must not cover today's missing beat
        data["beat"] = beat
        out[beat] = data
    return out


def not_covered(script_text: str) -> set[str]:
    return {m.group(1) for m in NOT_COVERED_RE.finditer(script_text)}


def check(script_text: str, beats: list[str] | None = None,
          run_date: str | None = None, directory: Path | None = None) -> dict:
    """Return {"ok": bool, "uncovered": [...], "notes": [...]} for one script."""
    want = run_date or date.today().isoformat()
    ledger = read_all(want, directory)
    excused = not_covered(script_text)
    required = beats if beats is not None else required_beats()
    uncovered, ok_beats, excused_beats = [], [], []
    for beat in required:
        entry = ledger.get(beat)
        if entry and entry.get("status") == "ok":
            ok_beats.append(beat)
            continue
        if beat in excused:
            excused_beats.append(beat)
            continue
        if entry is None:
            uncovered.append(f"{beat} (no status file)")
        else:
            uncovered.append(f"{beat} ({entry.get('status')}: {entry.get('reason') or 'no reason'})")
    return {
        "ok": not uncovered,
        "uncovered": uncovered,
        "notes": {
            "ok": ok_beats,
            "not_covered": sorted(excused_beats),
            "required": required,
            "date": want,
        },
    }


def format_report(result: dict) -> str:
    notes = result["notes"]
    if result["ok"]:
        return (f"BEAT COVERAGE: PASS — {len(notes['required'])} beats: "
                f"{len(notes['ok'])} ok, {len(notes['not_covered'])} explicitly not covered"
                + (f" ({', '.join(notes['not_covered'])})" if notes["not_covered"] else ""))
    return ("BEAT COVERAGE: FAIL — uncovered: " + "; ".join(result["uncovered"])
            + "\nA beat must write .tmp/beats/<beat>.status.json with status=ok, "
              "or the script must carry an explicit '[NOT COVERED: <beat> — reason]' line.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Per-beat status ledger")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_reset = sub.add_parser("reset", help="clear today's ledger before a run")
    p_reset.add_argument("--today", default=date.today().isoformat())

    p_mark = sub.add_parser("mark", help="record one or more beats' status")
    p_mark.add_argument("--beats", nargs="+", required=True)
    p_mark.add_argument("--status", required=True, choices=VALID_STATUSES)
    p_mark.add_argument("--reason", default="")
    p_mark.add_argument("--today", default=date.today().isoformat())

    p_check = sub.add_parser("check", help="gate: fail on any uncovered beat")
    p_check.add_argument("script")
    p_check.add_argument("--today", default=date.today().isoformat())

    p_show = sub.add_parser("show", help="print today's ledger")
    p_show.add_argument("--today", default=date.today().isoformat())

    args = parser.parse_args(argv)

    if args.cmd == "reset":
        d = ledger_dir()
        if d.is_dir():
            for path in d.glob("*.status.json"):
                path.unlink(missing_ok=True)
        print(f"beat ledger reset ({d})")
        return 0

    if args.cmd == "mark":
        for beat in args.beats:
            write(beat, args.status, args.reason, run_date=args.today)
        print(f"marked {', '.join(args.beats)} -> {args.status}")
        return 0

    if args.cmd == "show":
        ledger = read_all(args.today)
        if not ledger:
            print(f"beat ledger: EMPTY for {args.today}")
            return 0
        for beat, entry in ledger.items():
            print(f"{beat:22s} {entry.get('status'):7s} {entry.get('reason', '')}")
        gaps = [b for b in required_beats() if ledger.get(b, {}).get("status") != "ok"]
        if gaps:
            print(f"gaps: {', '.join(gaps)}")
        return 0

    try:
        text = Path(args.script).read_text()
    except OSError as exc:
        print(f"BEAT COVERAGE: FAIL — cannot read {args.script}: {exc}")
        return 1
    result = check(text, run_date=args.today)
    report = format_report(result)
    print(report)
    try:
        out = ledger_dir() / "coverage.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"script": str(args.script), **result}, indent=2) + "\n")
    except OSError:
        pass  # the verdict on stdout is the contract; the artifact is a convenience
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
