#!/usr/bin/env python3
"""Tests for the audio-truth gate (audio_truth.py) and the three surfaces that
consume it.

The defect (2026-10-01): every health surface asked "does the MP3 exist", never
"does the MP3 have audio in it". A silent or truncated mix therefore read as a
shipped episode on check-episode.sh, watch-episode.sh and generate-episode.sh,
and the only signal available was the pipeline exit code — which the
launchd-exit alarm dedupes as "already reported".

These tests run the REAL shell files against a sandboxed brainrot dir, with a
stub audio_truth.py they can steer, so they fail if a surface stops calling the
gate (the mutation that matters), not merely if an assertion is reworded.
CI is ubuntu-latest with no ffmpeg, so no test here may invoke one.
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import audio_truth  # noqa: E402

TODAY = "2026-09-25"

# A real episode (the 2026-10-01 rescue) measured 41.8 MB / 2539 s / -16.8 dB.
REAL = dict(size_bytes=41_848_873, duration_secs=2539.97, mean_db=-16.8)


# ── assess(): the pure decision. These are the load-bearing ones. ────────────

def test_a_real_episode_passes():
    ok, reason, _ = audio_truth.assess(**REAL)
    assert ok and reason == "OK"


def test_silence_is_caught_not_a_length_problem():
    """Digital silence: correct duration, correct size, no sound.

    This is the exact case that read healthy before — nothing about the file's
    size or length says "broken", so existence-based checks called it fine.
    """
    ok, reason, detail = audio_truth.assess(
        size_bytes=41_848_873, duration_secs=2539.97, mean_db=-91.0)
    assert not ok
    assert reason == "SILENT"
    assert "inaudible" in detail


def test_truncation_is_caught_and_named_as_such():
    """Real audio, but the mix cut off — distinct from silence, distinct fix."""
    ok, reason, _ = audio_truth.assess(
        size_bytes=1_200_000, duration_secs=95.0, mean_db=-18.0)
    assert not ok and reason == "TRUNCATED"


def test_empty_file_is_caught():
    ok, reason, _ = audio_truth.assess(
        size_bytes=0, duration_secs=0.0, mean_db=-91.0)
    assert not ok and reason == "EMPTY"


def test_unmeasurable_is_its_own_verdict_not_a_silent_episode():
    """ffprobe missing must NOT be reported as 'the episode is silent'.

    Those are different facts with different remedies, and conflating them is how
    a tooling outage turns into a lost episode.
    """
    ok, reason, _ = audio_truth.assess(size_bytes=None, duration_secs=None, mean_db=None)
    assert not ok and reason == "UNPROBEABLE"


def test_thresholds_sit_far_below_any_real_episode():
    """Guards against someone tuning the floors up to something that bites.

    A false block here costs Kyle an episode — the repo already lost one to an
    over-eager leak gate on 2026-10-01. Every floor must have a wide margin.
    """
    assert audio_truth.MIN_BYTES * 10 < REAL["size_bytes"]
    assert audio_truth.MIN_SECONDS * 3 < REAL["duration_secs"]
    # And a wide margin ABOVE silence, so quiet-but-real speech still passes.
    assert audio_truth.SILENCE_DB + 20 < REAL["mean_db"]


def test_probe_reports_missing_rather_than_raising(tmp_path):
    ok, reason, _ = audio_truth.probe(str(tmp_path / "nope.mp3"))
    assert not ok and reason == "MISSING"


def test_kill_switch_lets_a_box_without_ffmpeg_through(monkeypatch):
    monkeypatch.setenv("AUDIO_TRUTH_CHECK", "0")
    assert audio_truth.probe_ok("/definitely/not/here.mp3") is True


# ── The surfaces: run the real shell files. ────────────────────────────────

def _sandbox(tmp_path, stub_verdict, stub_rc):
    """A brainrot dir with the real scripts and a steerable audio_truth.py."""
    bdir = tmp_path / "brainrot"
    for d in (".tmp", "output", "logs", "scripts", "bin"):
        (bdir / d).mkdir(parents=True, exist_ok=True)
    for f in ("run_guard.sh", "watch-episode.sh", "check-episode.sh", "audio_truth.py"):
        (bdir / f).write_text(open(os.path.join(ROOT, f)).read())
    (bdir / "bin" / "verify-pitches.py").write_text("import sys\n")
    (bdir / "scripts" / f"killen-time-{TODAY}.txt").write_text(
        "[BASIL] hello\n[TRANSITION]\n[BROOKE] world\n")
    # The stub is what the surfaces actually invoke. Recording the call lets a
    # test prove the gate was consulted at all.
    calls = tmp_path / "calls.txt"
    (bdir / "audio_truth.py").write_text(
        "import sys\n"
        f"open({str(calls)!r}, 'a').write(' '.join(sys.argv[1:]) + chr(10))\n"
        f"print({stub_verdict!r})\n"
        f"sys.exit({stub_rc})\n"
    )
    alarms = tmp_path / "alarms.txt"
    fake_alarm = tmp_path / "raise-alarm.sh"
    fake_alarm.write_text(
        f'#!/bin/bash\necho "$@" >> "{alarms}"\necho "{tmp_path}/spooled.json"\n')
    fake_alarm.chmod(0o755)
    env = dict(os.environ, BRAINROT_DIR=str(bdir), RG_DIR=str(bdir / ".tmp"),
               RG_ALARM_BIN=str(fake_alarm), RG_WORKSPACE=str(bdir),
               WATCH_TODAY=TODAY, CHECK_TODAY=TODAY, HOME=str(tmp_path),
               PATH=os.environ["PATH"])
    env.pop("AUDIO_TRUTH_CHECK", None)
    return bdir, calls, alarms, env


def _run(script, env):
    return subprocess.run(["bash", os.path.join(env["BRAINROT_DIR"], script)],
                          capture_output=True, text=True, env=env, timeout=120)


def test_the_sandbox_is_actually_sandboxed(tmp_path):
    """A meta-test, and the reason _sandbox sets BRAINROT_DIR at all.

    Caught in development: check-episode.sh hardcoded /Users/kylekillen/brainrot-radio,
    so the first version of this suite appended its verdicts to Kyle's LIVE
    check-episode.log and judged the LIVE output/ directory. The gate that matters
    is 'does the script respect the sandbox', because without it every other test
    here is testing Kyle's real show.
    """
    _, _, _, env = _sandbox(tmp_path, "audio-truth: OK", 0)
    assert env["BRAINROT_DIR"] == str(tmp_path / "brainrot")
    assert env["CHECK_TODAY"] == TODAY


def test_check_episode_reports_ok_when_the_audio_is_audible(tmp_path):
    bdir, calls, _, env = _sandbox(tmp_path, "audio-truth: OK — 41,848,873 bytes", 0)
    (bdir / "output" / f"killen-time-{TODAY}.mp3").write_bytes(b"x" * 2_000_000)
    r = _run("check-episode.sh", env)
    log = (bdir / "logs" / "check-episode.log").read_text()
    assert r.returncode == 0
    assert "OK: Episode published" in log
    assert calls.exists(), "check-episode.sh must actually consult audio_truth.py"


def test_check_episode_fails_loudly_on_a_silent_episode(tmp_path):
    """The regression: a file at the MP3 path that holds no audio.

    Before this change this logged `OK: Episode published` and exited 0.
    """
    bdir, _, _, env = _sandbox(tmp_path, "audio-truth: SILENT — inaudible", 1)
    (bdir / "output" / f"killen-time-{TODAY}.mp3").write_bytes(b"x" * 2_000_000)
    r = _run("check-episode.sh", env)
    log = (bdir / "logs" / "check-episode.log").read_text()
    assert r.returncode != 0, "a silent episode must not exit 0"
    assert "FAIL" in log and "no audible audio" in log
    assert "OK: Episode published" not in log


def test_check_episode_leaves_the_silent_file_in_place(tmp_path):
    """The MP3 is the evidence, and its existence is what stands down a retry."""
    bdir, _, _, env = _sandbox(tmp_path, "audio-truth: SILENT — inaudible", 1)
    mp3 = bdir / "output" / f"killen-time-{TODAY}.mp3"
    mp3.write_bytes(b"x" * 2_000_000)
    _run("check-episode.sh", env)
    assert mp3.exists(), "the gate must not delete the artifact it is judging"


def test_watch_stands_down_on_audible_audio(tmp_path):
    bdir, _, _, env = _sandbox(tmp_path, "audio-truth: OK — 41,848,873 bytes", 0)
    (bdir / "output" / f"killen-time-{TODAY}.mp3").write_bytes(b"x" * 2_000_000)
    r = _run("watch-episode.sh", dict(env, WATCH_HOUR="8"))
    alarms = (tmp_path / "alarms.txt")
    assert r.returncode == 0
    assert not alarms.exists() or alarms.read_text() == ""


def test_watch_alarms_instead_of_standing_down_on_a_silent_mp3(tmp_path):
    """The regression: `[ -f mp3 ] && exit 0` silenced the watcher outright."""
    bdir, _, alarms, env = _sandbox(tmp_path, "audio-truth: SILENT — inaudible", 1)
    (bdir / "output" / f"killen-time-{TODAY}.mp3").write_bytes(b"x" * 2_000_000)
    _run("watch-episode.sh", dict(env, WATCH_HOUR="8"))
    assert alarms.exists(), "a silent MP3 must not silence the watcher"
    assert "has not shipped" in alarms.read_text()


def test_generate_episode_refuses_to_publish_a_silent_mix():
    """The publish path itself, not just the checkers.

    Extracts the gate out of the real generate-episode.sh and runs it against a
    silent mix: it must exit non-zero and say it is not publishing.
    """
    src = open(os.path.join(ROOT, "generate-episode.sh")).read()
    start = src.index('log "Verifying the mixed audio has actual sound in it..."')
    end = src.index('log "Publishing..."', start)
    block = src[start:end]

    script = (
        "set -e\n"
        "RESULT_LOG=$1\n"
        'log() { echo "[x] $1" >> "$RESULT_LOG"; }\n'
        "OUTPUT_MP3=$2\n"
        + block
    )
    tmp = os.path.dirname(ROOT) + "/__probe"
    import tempfile
    d = tempfile.mkdtemp()
    gate = os.path.join(d, "gate.sh")
    open(gate, "w").write(script)
    logf = os.path.join(d, "run.log")
    mp3 = os.path.join(d, "ep.mp3")
    open(mp3, "wb").write(b"x" * 2_000_000)
    stub = os.path.join(d, "audio_truth.py")
    open(stub, "w").write(
        "import sys\nprint('audio-truth: SILENT — inaudible')\nsys.exit(1)\n")

    r = subprocess.run(["bash", gate, logf, mp3], capture_output=True, text=True,
                       cwd=d, timeout=120)
    out = open(logf).read()
    assert r.returncode != 0, "the gate must abort before publish"
    assert "NOT publishing" in out
