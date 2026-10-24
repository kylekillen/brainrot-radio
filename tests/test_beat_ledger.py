#!/usr/bin/env python3
"""Tests for beat_ledger.py — the per-beat coverage ledger and its QC gate.

The contract: every beat reporter records ok|failed|empty in
.tmp/beats/<beat>.status.json, and a beat that is neither ok nor explicitly
named in an "[NOT COVERED: <beat>]" line fails coverage.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import beat_ledger  # noqa: E402

BEATS = ["ai_tech", "agentic_systems", "claude_lab", "nba_sports",
         "entertainment", "economics_culture", "prediction_markets"]
TODAY = "2026-10-24"


def test_write_read_roundtrip(tmp_path):
    beat_ledger.write("sports", "ok", "segment sports wrote 900 words",
                      run_date=TODAY, directory=tmp_path)
    ledger = beat_ledger.read_all(TODAY, tmp_path)
    assert ledger["sports"]["status"] == "ok"
    assert ledger["sports"]["reason"] == "segment sports wrote 900 words"
    assert ledger["sports"]["date"] == TODAY
    on_disk = json.loads((tmp_path / "sports.status.json").read_text())
    assert on_disk["status"] == "ok"


def test_stale_status_from_another_day_does_not_cover(tmp_path):
    beat_ledger.write("sports", "ok", "yesterday", run_date="2026-10-23", directory=tmp_path)
    result = beat_ledger.check("", beats=["sports"], run_date=TODAY, directory=tmp_path)
    assert result["ok"] is False
    assert "sports" in result["uncovered"][0]


def test_all_ok_passes(tmp_path):
    for beat in BEATS:
        beat_ledger.write(beat, "ok", "fine", run_date=TODAY, directory=tmp_path)
    result = beat_ledger.check("script", beats=BEATS, run_date=TODAY, directory=tmp_path)
    assert result["ok"] is True
    assert beat_ledger.format_report(result).startswith("BEAT COVERAGE: PASS")


def test_missing_beat_fails(tmp_path):
    for beat in BEATS[:-1]:
        beat_ledger.write(beat, "ok", "fine", run_date=TODAY, directory=tmp_path)
    result = beat_ledger.check("script", beats=BEATS, run_date=TODAY, directory=tmp_path)
    assert result["ok"] is False
    assert "prediction_markets (no status file)" in result["uncovered"]


def test_failed_beat_fails_and_reports_reason(tmp_path):
    beat_ledger.write("sports", "failed", "write-pass2 hit the 1800s wall-clock cap",
                      run_date=TODAY, directory=tmp_path)
    result = beat_ledger.check("", beats=["sports"], run_date=TODAY, directory=tmp_path)
    assert result["ok"] is False
    assert "wall-clock cap" in result["uncovered"][0]


def test_explicit_not_covered_line_excuses_a_beat(tmp_path):
    beat_ledger.write("sports", "failed", "timed out", run_date=TODAY, directory=tmp_path)
    script = (
        "[BROOKE] We're skipping the football today.\n"
        "[NOT COVERED: sports — no fresh material after the bye week]\n"
        "[BASIL] Here's what else is going on.\n"
    )
    result = beat_ledger.check(script, beats=["sports"], run_date=TODAY, directory=tmp_path)
    assert result["ok"] is True
    assert result["notes"]["not_covered"] == ["sports"]


def test_not_covered_for_a_different_beat_does_not_excuse(tmp_path):
    script = "[NOT COVERED: economics_culture — thin day]\n"
    result = beat_ledger.check(script, beats=["sports"], run_date=TODAY, directory=tmp_path)
    assert result["ok"] is False


def test_empty_status_is_not_ok(tmp_path):
    beat_ledger.write("sports", "empty", "segment returned 0 words",
                      run_date=TODAY, directory=tmp_path)
    result = beat_ledger.check("", beats=["sports"], run_date=TODAY, directory=tmp_path)
    assert result["ok"] is False
    assert "empty" in result["uncovered"][0]


def test_rejects_unknown_status(tmp_path):
    try:
        beat_ledger.write("sports", "good", "", run_date=TODAY, directory=tmp_path)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown status should raise")


def test_cli_check_exit_codes(tmp_path):
    env = dict(os.environ, BEAT_LEDGER_DIR=str(tmp_path))
    script = tmp_path / "killen-time-2026-10-24.txt"
    script.write_text("[BASIL] hello\n")

    fail = subprocess.run([sys.executable, os.path.join(ROOT, "beat_ledger.py"),
                           "check", str(script), "--today", TODAY],
                          capture_output=True, text=True, env=env)
    assert fail.returncode == 1, fail.stdout + fail.stderr
    assert "BEAT COVERAGE: FAIL" in fail.stdout

    script.write_text("".join(f"[NOT COVERED: {b} — thin day]\n" for b in BEATS))
    passed = subprocess.run([sys.executable, os.path.join(ROOT, "beat_ledger.py"),
                             "check", str(script), "--today", TODAY],
                            capture_output=True, text=True, env=env)
    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert "BEAT COVERAGE: PASS" in passed.stdout


def test_voice_parse_skips_not_covered_annotation(tmp_path):
    import voice

    script = tmp_path / "script.txt"
    script.write_text(
        "[NOT COVERED: sports — nothing fresh]\n"
        "[BASIL] Welcome back to Killen Time.\n"
        "[BROOKE] Here's the AI news.\n"
    )
    segments = voice.parse_script(str(script))
    assert [s for s, _ in segments] == ["BASIL", "BROOKE"]
    assert all("NOT COVERED" not in text for _, text in segments)
