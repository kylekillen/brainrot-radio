#!/usr/bin/env python3
"""generate-episode.sh — the two branches this ticket changed, run for real.

The Python tests cover topup_writer.py's loop. These cover the two shell decisions the
loop hangs off, by extracting the actual function / gate out of generate-episode.sh and
running them under bash with stubbed dependencies — so a refactor that quietly drops the
floor check, or that folds "QC errored" back into "QC ran and said FAIL", fails here.

  1. run_topup_loop: verifies with voice.py's own count, repairs via topup_writer.py, and
     returns non-zero when the repair budget is exhausted (so the run aborts loudly
     instead of dying at the render floor with no explanation).
  2. The QC gate: a QC step that ERRORED (never ran — the 10-01 weekly-cap case) must be
     a DIFFERENT state from one that ran and returned FAIL: its own flag file, its own
     knob, its own log line.
"""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHELL = os.path.join(ROOT, "generate-episode.sh")

FLOOR = 20          # stand-in for config.MIN_WORD_COUNT (6000)
RUN_ID = "20261001-040002"


def _shell_text():
    with open(SHELL) as f:
        return f.read()


def _extract_function(name):
    lines = _shell_text().splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(f"{name}() {{"))
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "}")
    return "\n".join(lines[start:end + 1])


def _extract_qc_gate():
    lines = _shell_text().splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("QC_MAX_ATTEMPTS="))
    end = next(i for i in range(start, len(lines))
               if lines[i].startswith("else")
               and i + 1 < len(lines) and "Gemini engine: GOAL-SEEKING" in lines[i + 1])
    # Keep the `fi` that closes `if [ "$QC_VERDICT" != "PASS" ]`; drop the `else` that
    # opens the Gemini branch, so the block stands alone.
    assert lines[end - 1] == "fi", f"QC gate slice is unbalanced: {lines[end-2:end]!r}"
    return "\n".join(lines[start:end])


def _extract_signal_block():
    """The post-publish signals block — the only consumer of the qc-FAIL/qc-ERROR flags."""
    lines = _shell_text().splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("SIGNALS_PY="))
    end = next(i for i in range(start, len(lines)) if lines[i] == "fi")
    return "\n".join(lines[start:end + 1])


def _bash(body, cwd, env, tmp_path):
    driver = tmp_path / "driver.sh"
    driver.write_text("#!/bin/bash\n" + body)
    return subprocess.run(["bash", str(driver)], cwd=str(cwd),
                          capture_output=True, text=True, env=env)


def _speech(n, tag="BASIL"):
    return f"[{tag}] " + " ".join(f"w{i}" for i in range(n))


STUB_TOPUP_WRITER = """\
import argparse, os, sys
from voice import parse_script
ap = argparse.ArgumentParser()
ap.add_argument('--script'); ap.add_argument('--mode'); ap.add_argument('--phase')
ap.add_argument('--max-attempts', type=int); ap.add_argument('--min-words', type=int)
a = ap.parse_args()
segs = parse_script(a.script)
n = sum(len(t.split()) for sp, t in segs if sp != 'TRANSITION')
if os.environ.get('STUB_NOOP'):
    # Report failure WITHOUT repairing, so the caller logs the pre-repair count.
    sys.exit(1)
if n >= a.min_words:
    sys.exit(0)
with open(a.script, 'a') as f:
    f.write('\\n[TRANSITION]\\n[BROOKE] ' + ' '.join('z%d' % i for i in range(60)) + '\\n')
sys.exit(int(os.environ.get('STUB_TOPUP_RC', '0')))
"""


@pytest.fixture
def topup_run(tmp_path):
    """run_topup_loop from the real shell, with a stub topup_writer.py in the cwd.

    The stub measures with voice.py's parse_script (as the real one does), appends 60
    words when under the floor, and exits $STUB_TOPUP_RC — so a test can make the repair
    budget fail on demand, or make it fail WITHOUT repairing so the caller logs the
    pre-repair count.
    """
    workdir = tmp_path / "wd"
    workdir.mkdir()
    (workdir / "topup_writer.py").write_text(STUB_TOPUP_WRITER)
    (tmp_path / "logs").mkdir()
    logs = tmp_path / "generate.log"
    script = tmp_path / "episode.txt"

    def _run(script_text, env_extra=None, rc="0"):
        script.write_text(script_text)
        env = dict(os.environ, STUB_TOPUP_RC=rc, PYTHONPATH=ROOT)
        env.update(env_extra or {})
        body = f"""
BRAINROT_DIR={tmp_path}
RESULT_LOG={logs}
RUN_ID={RUN_ID}
NEW_SCRIPT={script}
MIN_RENDER_WORDS=${{MIN_RENDER_WORDS:-{FLOOR}}}
TOPUP_MAX_ATTEMPTS=${{TOPUP_MAX_ATTEMPTS:-2}}
TOPUP_ENABLED=${{TOPUP_ENABLED:-1}}
PODCAST_ENGINE=${{PODCAST_ENGINE:-external}}
TOTAL_WORDS=0
log() {{ echo "$1"; }}
{_extract_function('run_topup_loop')}
set +e
run_topup_loop "post-write"
echo "RC=$?"
"""
        return _bash(body, workdir, env, tmp_path)

    return _run


class TestRunTopupLoop:
    def test_short_script_is_repaired_and_returns_zero(self, topup_run):
        proc = topup_run(_speech(5))
        assert "RC=0" in proc.stdout, proc.stdout + proc.stderr

    def test_exhausted_budget_returns_nonzero_and_says_so_loudly(self, topup_run):
        proc = topup_run(_speech(5), rc="1")
        assert "RC=1" in proc.stdout, proc.stdout + proc.stderr
        assert "TOP-UP LOOP EXHAUSTED" in proc.stdout
        assert "NOT publishing a short stub" in proc.stdout

    def test_already_long_enough_script_costs_nothing(self, topup_run):
        proc = topup_run(_speech(40))
        assert "RC=0" in proc.stdout
        assert f"40 speech words (floor {FLOOR})" in proc.stdout

    def test_kill_switch_disables_the_loop_entirely(self, topup_run):
        proc = topup_run(_speech(5), env_extra={"TOPUP_ENABLED": "0"})
        assert "RC=0" in proc.stdout
        assert "DISABLED" in proc.stdout

    def test_reports_voice_pys_count_not_wc_w(self, topup_run):
        """10 speech words here; `wc -w` would call the same file 14 (4 speaker tags +
        2 [TRANSITION]s). The number the gate logs must be the one voice.py gates on."""
        text = "\n".join([_speech(5), "[TRANSITION]", _speech(5, "BROOKE")])
        proc = topup_run(text, env_extra={"STUB_NOOP": "1"})
        assert f"10 speech words vs {FLOOR} floor" in proc.stdout, proc.stdout + proc.stderr

    def test_external_engine_selects_the_free_lane(self, tmp_path):
        (tmp_path / "logs").mkdir()
        body = f"""
PODCAST_ENGINE=external
TOPUP_ENABLED=1
log() {{ echo "$1"; }}
{_extract_function('run_topup_loop')}
run_topup_loop "post-write"
"""
        proc = _bash(body, ROOT, dict(os.environ), tmp_path)
        assert "mode=external" in proc.stdout, proc.stdout + proc.stderr


class TestQcGateErroredIsNotFailed:
    """QC that ERRORED (never ran) is a different state from QC that ran and said FAIL."""

    def _gate(self, tmp_path, step_body, env_extra=""):
        (tmp_path / "logs").mkdir(exist_ok=True)
        logs = tmp_path / "qc.log"
        logs.write_text("")
        body = f"""
RESULT_LOG={logs}
BRAINROT_DIR={tmp_path}
RUN_ID={RUN_ID}
TODAY=2026-10-01
NEW_SCRIPT={tmp_path}/s.txt
QC_MAX_ATTEMPTS=1
QC_FAIL_ACTION=publish
{env_extra}
log() {{ echo "$1"; }}
run_claude_step() {{ {step_body} ; }}
{_extract_qc_gate()}
echo "RC_VERDICT=$QC_VERDICT QC_RAN=$QC_RAN"
"""
        return _bash(body, ROOT, dict(os.environ), tmp_path), tmp_path

    def test_qc_that_ran_and_failed_is_the_fail_state(self, tmp_path):
        proc, d = self._gate(tmp_path, 'echo "QC VERDICT: FAIL" >> "$RESULT_LOG"; return 0')
        assert "QC_RAN=1" in proc.stdout, proc.stdout + proc.stderr
        assert "QC GATE FAILED" in proc.stdout
        assert (d / "logs" / f"qc-FAIL-{RUN_ID}.flag").exists()
        assert not (d / "logs" / f"qc-ERROR-{RUN_ID}.flag").exists()

    def test_qc_that_errored_is_a_distinct_state(self, tmp_path):
        """The 2026-10-01 case: weekly limit hit, step exits non-zero, nobody read it."""
        proc, d = self._gate(tmp_path, "return 1")
        assert "QC_RAN=0" in proc.stdout, proc.stdout + proc.stderr
        assert "QC NEVER RAN" in proc.stdout
        assert "UNREVIEWED" in proc.stdout
        assert (d / "logs" / f"qc-ERROR-{RUN_ID}.flag").exists()
        assert not (d / "logs" / f"qc-FAIL-{RUN_ID}.flag").exists()

    def test_error_action_publish_is_the_default_and_names_the_gap(self, tmp_path):
        proc, _ = self._gate(tmp_path, "return 1")
        assert "publishing WITHOUT any QC review" in proc.stdout

    def test_error_action_abort_blocks_an_unreviewed_episode(self, tmp_path):
        proc, _ = self._gate(tmp_path, "return 1", env_extra="QC_ERROR_ACTION=abort")
        assert "QC_ERROR_ACTION=abort" in proc.stdout
        # `exit 1` inside the gate aborts the script, so the trailing echo never runs.
        assert "RC_VERDICT=" not in proc.stdout
        assert proc.returncode != 0


def test_generate_episode_is_valid_bash():
    proc = subprocess.run(["bash", "-n", SHELL], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


class TestQcFlagEmitsASignal:
    """The two flag names must stay wired to the fleet signal stream together.

    Code review (2026-10-01): splitting "QC errored" from "QC failed" moved a flag
    file that generate-episode.sh's signals block does not know about. The unreviewed
    broadcast then emitted NO fleet signal where, before the split, it emitted one —
    strictly quieter than the reviewed-and-rejected ship it replaced. These run the real
    signals block so the two names cannot drift apart again.
    """

    def _run(self, tmp_path, flags):
        (tmp_path / "logs").mkdir()
        (tmp_path / "scripts").mkdir()
        for name in flags:
            (tmp_path / "logs" / name).write_text("flag\n")
        home = tmp_path / "home"
        stub = home / "observer-system" / "scripts" / "signals.py"
        stub.parent.mkdir(parents=True)
        emitted = tmp_path / "emitted.txt"
        stub.write_text(
            "import argparse\n"
            "ap = argparse.ArgumentParser()\n"
            "ap.add_argument('cmd')                       # signals.py emit ...\n"
            "ap.add_argument('--source'); ap.add_argument('--category')\n"
            "ap.add_argument('--summary'); ap.add_argument('--tags')\n"
            "ap.add_argument('--linked'); ap.add_argument('--body')\n"
            "a = ap.parse_args()\n"
            f"open({str(emitted)!r}, 'a').write((a.category or '?') + '\\t' + "
            "(a.summary or '') + '\\n')\n"
        )
        logs = tmp_path / "generate.log"
        body = f"""
HOME={home}
RUN_ID={RUN_ID}
RESULT_LOG={logs}
SCRIPT_FILE=scripts/killen-time-2026-10-01.txt
log() {{ echo "$1"; }}
{_extract_signal_block()}
"""
        proc = _bash(body, tmp_path, dict(os.environ, HOME=home), tmp_path)
        lines = emitted.read_text().splitlines() if emitted.exists() else []
        return proc, lines

    def test_qc_fail_still_emits_its_gap_signal(self, tmp_path):
        _, lines = self._run(tmp_path, [f"qc-FAIL-{RUN_ID}.flag"])
        assert any(l.startswith("gap\t") and "qc-FAIL-" in l for l in lines), lines

    def test_qc_errored_emits_its_own_signal(self, tmp_path):
        """The regression: this state used to emit nothing at all."""
        _, lines = self._run(tmp_path, [f"qc-ERROR-{RUN_ID}.flag"])
        assert any(l.startswith("flag\t") and "qc-ERROR-" in l for l in lines), lines
        assert any("UNREVIEWED" in l for l in lines), lines

    def test_the_two_names_are_never_silently_merged(self, tmp_path):
        """Both flag names must appear in the signals block — the drift guard itself."""
        block = _extract_signal_block()
        assert "qc-FAIL-" in block
        assert "qc-ERROR-" in block

    def test_clean_episode_emits_no_qc_signal(self, tmp_path):
        _, lines = self._run(tmp_path, [])
        assert not any("qc-" in l for l in lines), lines