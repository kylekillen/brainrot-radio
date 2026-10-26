"""Trifecta lane 1: every web-reading claude step goes through bin/sandboxed-claude.sh."""
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WRAPPER = ROOT / "bin" / "sandboxed-claude.sh"
OBS_PY = Path.home() / "observer-system" / ".venv" / "bin" / "python"


def _fake_claude(tmp_path, body):
    f = tmp_path / "fake-claude"
    f.write_text("#!/bin/bash\n" + body)
    f.chmod(0o755)
    return f


def _sandbox_ready():
    if not OBS_PY.exists():
        return False
    r = subprocess.run([str(OBS_PY), "-m", "observer.mcp.sandbox", "available"],
                       capture_output=True, text=True, cwd="/tmp")
    return r.stdout.strip() == "sandbox-exec-ok"


def test_no_bare_claude_bypass_left_in_web_reading_steps():
    for name in ("generate-episode.sh", "gemini-show.sh"):
        text = (ROOT / name).read_text()
        assert not re.search(r"\$CLAUDE\s+--dangerously-skip-permissions", text), name
        assert re.search(r'sandboxed-claude\.sh"? --dangerously-skip-permissions', text), name
    top = (ROOT / "episode_topup.py").read_text()
    assert "[CLAUDE_BIN, \"--dangerously" not in top
    assert "sandboxed-claude.sh" in top


def test_off_switch_runs_claude_unfenced(tmp_path):
    fake = _fake_claude(tmp_path, 'echo "args=$*"\n')
    env = {**os.environ, "CLAUDE_BIN": str(fake), "BRAINROT_CLAUDE_SANDBOX": "off"}
    r = subprocess.run([str(WRAPPER), "--model", "x"], capture_output=True, text=True, env=env)
    assert r.returncode == 0 and "args=--model x" in r.stdout
    assert "UNFENCED" in r.stderr


def test_degraded_mode_scrubs_env_and_drops_shell(tmp_path):
    fake = _fake_claude(tmp_path, 'echo "args=$*"; echo "gh=${GH_TOKEN:-none}"\n')
    env = {**os.environ, "CLAUDE_BIN": str(fake), "OBS_PY": "/nonexistent",
           "GH_TOKEN": "secret"}
    r = subprocess.run([str(WRAPPER), "-p", "hi"], capture_output=True, text=True, env=env)
    assert "gh=none" in r.stdout
    assert "--tools Read,Write,Edit,WebSearch,WebFetch -p hi" in r.stdout
    assert "DEGRADED" in r.stderr


@pytest.mark.skipif(not _sandbox_ready(), reason="needs macOS sandbox-exec + deployed observer-system")
def test_sandbox_blocks_secrets_scrubs_env_allows_work_dir(tmp_path):
    fake = _fake_claude(tmp_path, (
        'echo "gh=${GH_TOKEN:-none} ledger=${BEAT_LEDGER_DIR:-none}"\n'
        f'echo ok > {tmp_path}/out.txt && echo wrote\n'
        'cat ~/.config/gh/hosts.yml >/dev/null 2>&1 && echo READ_GH || echo gh-blocked\n'
        'ls ~/.ssh >/dev/null 2>&1 && echo READ_SSH || echo ssh-blocked\n'
    ))
    env = {**os.environ, "CLAUDE_BIN": str(fake), "GH_TOKEN": "secret",
           "BEAT_LEDGER_DIR": "/x/ledger", "BRAINROT_SANDBOX_WRITE": str(tmp_path)}
    r = subprocess.run([str(WRAPPER)], capture_output=True, text=True, env=env, timeout=60)
    assert "gh=none ledger=/x/ledger" in r.stdout, r.stderr
    assert "wrote" in r.stdout
    assert "gh-blocked" in r.stdout and "ssh-blocked" in r.stdout
    assert "READ_" not in r.stdout
