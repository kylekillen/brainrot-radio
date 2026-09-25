#!/usr/bin/env python3
"""Tests for run_guard.sh (writer-side EXIT trap) and watch-episode.sh (watcher).

The 2026-09-25 recovery run ended at 05:54 without a success line and nothing raised.
These run the real bash with a fake raise-alarm.sh that records its arguments.
"""
import os
import subprocess
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = "2026-09-25"


@pytest.fixture
def env(tmp_path):
    """Sandbox: fake brainrot dir (with the real scripts), fake alarm binary."""
    bdir = tmp_path / "brainrot"
    (bdir / ".tmp").mkdir(parents=True)
    (bdir / "output").mkdir()
    (bdir / "logs").mkdir()
    for f in ("run_guard.sh", "watch-episode.sh"):
        (bdir / f).write_text(open(os.path.join(ROOT, f)).read())
    alarms = tmp_path / "alarms.txt"
    fake = tmp_path / "raise-alarm.sh"
    fake.write_text(f'#!/bin/bash\necho "$@" >> "{alarms}"\necho "{tmp_path}/spooled.json"\n')
    fake.chmod(0o755)
    e = dict(os.environ, BRAINROT_DIR=str(bdir), RG_DIR=str(bdir / ".tmp"), RG_ALARM_BIN=str(fake),
             RG_WORKSPACE=str(bdir), WATCH_TODAY=TODAY, WATCH_HOUR="8",
             HOME=str(tmp_path))
    return bdir, alarms, e


def _alarms(path):
    return path.read_text().splitlines() if path.exists() else []


def _writer(bdir, e, body):
    """Run `body` in a bash that sourced run_guard.sh under set -e, like generate-episode.sh."""
    script = f'set -e\nexport RG_RUN_ID=20260925-051500\n. "{bdir}/run_guard.sh"\nrg_start\n' \
             f"trap 'rg_on_exit || true' EXIT\n{body}\n"
    return subprocess.run(["bash", "-c", script], env=e, capture_output=True, text=True, timeout=30)


def _state(bdir):
    (f,) = list((bdir / ".tmp").glob("run-state-*.env"))
    return dict(l.split("=", 1) for l in f.read_text().splitlines() if "=" in l)


# ── writer side ──────────────────────────────────────────────────────────────

def test_exit_1_without_declaring_ok_raises_an_alarm(env):
    bdir, alarms, e = env
    r = _writer(bdir, e, 'rg_beat "Rendering TTS audio..."\nexit 1')
    assert r.returncode == 1
    (line,) = _alarms(alarms)
    assert "--no-telegram" in line and "brainrot-radio" in line and "critical" in line
    assert "ended without shipping an episode (exit 1)" in line and "Rendering TTS audio" in line
    st = _state(bdir)
    assert st["state"] == "failed" and st["alarmed"] == "1" and st["rc"] == "1"


def test_set_e_abort_raises_an_alarm(env):
    bdir, alarms, e = env
    r = _writer(bdir, e, "false\necho unreachable")
    assert r.returncode == 1
    assert len(_alarms(alarms)) == 1


def test_sigterm_is_converted_to_an_exit_and_alarms(env):
    bdir, alarms, e = env
    r = _writer(bdir, e, "kill -TERM $$\nsleep 5")
    assert r.returncode == 143
    assert len(_alarms(alarms)) == 1


def test_ok_and_standdown_do_not_alarm(env):
    bdir, alarms, e = env
    assert _writer(bdir, e, "rg_finish ok\nexit 0").returncode == 0
    assert _state(bdir)["state"] == "ok"
    for f in (bdir / ".tmp").glob("run-state-*.env"):
        f.unlink()
    assert _writer(bdir, e, "rg_finish standdown\nexit 0").returncode == 0
    assert _alarms(alarms) == []


def test_alarm_that_fails_to_spool_stays_retryable(env):
    bdir, alarms, e = env
    silent = bdir.parent / "silent.sh"
    silent.write_text("#!/bin/bash\nexit 0\n")  # like raise-alarm.sh on an encode failure: exit 0, no path
    silent.chmod(0o755)
    _writer(bdir, dict(e, RG_ALARM_BIN=str(silent)), "exit 1")
    assert _state(bdir)["alarmed"] == "0"          # the watcher will retry


# ── watcher side ─────────────────────────────────────────────────────────────

def _watch(e, **over):
    return subprocess.run(["bash", os.path.join(e["BRAINROT_DIR"], "watch-episode.sh")],
                          env=dict(e, **over), capture_output=True, text=True, timeout=30)


def _state_file(bdir, run_id, **kv):
    base = {"state": "running", "pid": "999999", "run_id": run_id, "date": TODAY,
            "started": str(int(time.time())), "heartbeat": str(int(time.time())), "step": "QC", "alarmed": "0"}
    base.update({k: str(v) for k, v in kv.items()})
    (bdir / ".tmp" / f"run-state-{run_id}.env").write_text("".join(f"{k}={v}\n" for k, v in base.items()))


def test_watcher_alarms_on_a_run_that_died_without_its_trap(env):
    bdir, alarms, e = env
    _state_file(bdir, "r1", pid=999999)             # no such pid: SIGKILL / power loss
    _watch(e)
    (line,) = _alarms(alarms)
    assert "DIED SILENTLY" in line and "r1" in line
    _watch(e)                                        # idempotent: same problem, no second page
    assert len(_alarms(alarms)) == 1


def test_watcher_leaves_a_live_run_with_a_fresh_heartbeat_alone(env):
    bdir, alarms, e = env
    p = subprocess.Popen(["sleep", "30"])
    try:
        _state_file(bdir, "r2", pid=p.pid)
        _watch(e)
        assert _alarms(alarms) == []
    finally:
        p.kill()


def test_watcher_alarms_on_a_hung_run(env):
    bdir, alarms, e = env
    p = subprocess.Popen(["sleep", "30"])
    try:
        _state_file(bdir, "r3", pid=p.pid, heartbeat=int(time.time()) - 80 * 60)
        _watch(e)
        (line,) = _alarms(alarms)
        assert "HUNG" in line and "no progress for 80 min" in line
    finally:
        p.kill()


def test_watcher_retries_a_failed_run_whose_alarm_never_spooled(env):
    bdir, alarms, e = env
    _state_file(bdir, "r4", state="failed", rc=1, reason="exit 1 at: Rendering", alarmed=0)
    _watch(e)
    assert len(_alarms(alarms)) == 1
    _watch(e)
    assert len(_alarms(alarms)) == 1                 # marked alarmed=1 now


def test_watcher_alarms_when_nothing_ran_by_the_deadline_once(env):
    bdir, alarms, e = env
    _watch(e, WATCH_HOUR="6")
    assert _alarms(alarms) == []                     # before the deadline: quiet
    _watch(e, WATCH_HOUR="7")
    _watch(e, WATCH_HOUR="8")
    (line,) = _alarms(alarms)
    assert "no episode for" in line and "no run in progress" in line


def test_watcher_does_not_double_page_a_failed_run_at_the_deadline(env):
    bdir, alarms, e = env
    _state_file(bdir, "r5", state="failed", rc=1, reason="x", alarmed=1)
    _watch(e, WATCH_HOUR="9")
    assert _alarms(alarms) == []


def test_watcher_is_quiet_once_the_episode_exists_or_outside_the_window(env):
    bdir, alarms, e = env
    (bdir / "output" / f"killen-time-{TODAY}.mp3").write_text("x")
    _state_file(bdir, "r6", pid=999999)
    _watch(e)
    assert _alarms(alarms) == []
    (bdir / "output" / f"killen-time-{TODAY}.mp3").unlink()
    _watch(e, WATCH_HOUR="15")
    assert _alarms(alarms) == []


def test_watcher_ignores_yesterdays_state(env):
    bdir, alarms, e = env
    _state_file(bdir, "old", pid=999999, date="2026-09-24")
    _watch(e, WATCH_HOUR="6")
    assert _alarms(alarms) == []


# ── the real generate-episode.sh, sandboxed ──────────────────────────────────

def _sandboxed_generate(env_tuple):
    """generate-episode.sh with its hard-coded BRAINROT_DIR pointed at the sandbox and no
    ingest.py, so it runs its real preamble, then dies at the first real step."""
    bdir, alarms, e = env_tuple
    src = open(os.path.join(ROOT, "generate-episode.sh")).read().replace("/Users/kylekillen/brainrot-radio", str(bdir))
    (bdir / "generate-episode.sh").write_text(src)
    (bdir / "venv" / "bin").mkdir(parents=True)
    (bdir / "venv" / "bin" / "activate").write_text("")
    e = dict(e, PODCAST_ENGINE="claude", RG_ALARM_BIN=e["RG_ALARM_BIN"])
    return bdir, alarms, e


def test_generate_episode_alarms_when_a_real_step_kills_it(env):
    bdir, alarms, e = _sandboxed_generate(env)
    r = subprocess.run(["bash", str(bdir / "generate-episode.sh")], env=e, capture_output=True, text=True,
                       timeout=60, cwd=str(bdir))
    assert r.returncode != 0
    (line,) = _alarms(alarms)                       # ingest.py is absent -> set -e abort -> trap
    assert "ended without shipping an episode" in line and "Running ingest" in line
    assert "Running ingest" in r.stderr             # log() now reaches the recovery/launchd log too


def test_generate_episode_standdown_when_already_published_is_quiet(env):
    bdir, alarms, e = _sandboxed_generate(env)
    today = time.strftime("%Y-%m-%d")
    (bdir / "output" / f"killen-time-{today}.mp3").write_text("x")
    r = subprocess.run(["bash", str(bdir / "generate-episode.sh")], env=e, capture_output=True, text=True,
                       timeout=60, cwd=str(bdir))
    assert r.returncode == 0
    assert _alarms(alarms) == []
