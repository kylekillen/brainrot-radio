#!/usr/bin/env python3
"""Tests for publish_review.py — the review-artifact -> private-feed primitive.

All external effects are monkeypatched: render_report.py is never actually run
(subprocess.run is faked). No network, no TTS, no ffmpeg, no real feed writes.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import publish_review  # noqa: E402


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def fake_render(monkeypatch):
    """render_report subprocess that 'publishes' and prints a fresh EPISODE_URL.
    Records each call so tests can assert it ran / didn't run."""
    calls = []

    def fake_run(cmd, capture_output=True, text=True):
        calls.append(cmd)
        n = len(calls)
        return _Proc(returncode=0,
                     stdout=f"[render] done\nEPISODE_URL: https://feed.here.now/ep-{n}.mp3\n")

    monkeypatch.setattr(publish_review.subprocess, "run", fake_run)
    return calls


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_publishes_and_records_ledger(tmp_path, fake_render):
    md = _write(tmp_path, "pitch.md", "# Build Pitch\n\nUse effort tiers. Real evidence here.\n")
    ledger = tmp_path / "ledger.json"
    res = publish_review.publish_review("Pitch", md, ledger_path=ledger)
    assert res["state"] == "published"
    assert res["url"] == "https://feed.here.now/ep-1.mp3"
    assert len(fake_render) == 1
    data = json.loads(ledger.read_text())
    assert res["sha"] in data
    assert data[res["sha"]]["url"] == res["url"]


def test_idempotent_skip_on_same_content(tmp_path, fake_render):
    md = _write(tmp_path, "pitch.md", "# Build Pitch\n\nSame body, twice.\n")
    ledger = tmp_path / "ledger.json"
    first = publish_review.publish_review("Pitch", md, ledger_path=ledger)
    second = publish_review.publish_review("Pitch", md, ledger_path=ledger)
    assert first["state"] == "published"
    assert second["state"] == "skipped-duplicate"
    assert second["url"] == first["url"]
    # render_report ran exactly once — the retry did NOT double-publish.
    assert len(fake_render) == 1


def test_whitespace_churn_does_not_republish(tmp_path, fake_render):
    ledger = tmp_path / "ledger.json"
    a = _write(tmp_path, "a.md", "# T\n\nThe   pitch body.\n")
    b = _write(tmp_path, "b.md", "# T\n\nThe pitch body.\n\n\n")
    publish_review.publish_review("T", a, ledger_path=ledger)
    res = publish_review.publish_review("T", b, ledger_path=ledger)
    assert res["state"] == "skipped-duplicate"
    assert len(fake_render) == 1


def test_force_republishes(tmp_path, fake_render):
    md = _write(tmp_path, "pitch.md", "# Build Pitch\n\nForce me.\n")
    ledger = tmp_path / "ledger.json"
    publish_review.publish_review("Pitch", md, ledger_path=ledger)
    res = publish_review.publish_review("Pitch", md, ledger_path=ledger, force=True)
    assert res["state"] == "published"
    assert len(fake_render) == 2


def test_skips_empty_file(tmp_path, fake_render):
    md = _write(tmp_path, "empty.md", "   \n\n")
    res = publish_review.publish_review("Empty", md, ledger_path=tmp_path / "l.json")
    assert res["state"] == "skipped-empty"
    assert res["url"] is None
    assert len(fake_render) == 0  # never invoked render_report


def test_skips_no_verified_pitch(tmp_path, fake_render):
    md = _write(tmp_path, "none.md", "# Build Pitches — 2026-06-25\n\nNO_VERIFIED_PITCH\nNothing cleared the bar.\n")
    res = publish_review.publish_review("None", md, ledger_path=tmp_path / "l.json")
    assert res["state"] == "skipped-empty"
    assert len(fake_render) == 0


def test_render_failure_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(publish_review.subprocess, "run",
                        lambda *a, **k: _Proc(returncode=1, stderr="kokoro unreachable"))
    md = _write(tmp_path, "pitch.md", "# P\n\nbody\n")
    with pytest.raises(RuntimeError, match="render_report failed"):
        publish_review.publish_review("P", md, ledger_path=tmp_path / "l.json")
    # Nothing recorded on failure.
    assert not (tmp_path / "l.json").exists()


def test_missing_episode_url_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(publish_review.subprocess, "run",
                        lambda *a, **k: _Proc(returncode=0, stdout="rendered but forgot to print url"))
    md = _write(tmp_path, "pitch.md", "# P\n\nbody\n")
    with pytest.raises(RuntimeError, match="no EPISODE_URL"):
        publish_review.publish_review("P", md, ledger_path=tmp_path / "l.json")


def test_main_argv_published_prints_episode_url(tmp_path, fake_render, capsys):
    md = _write(tmp_path, "pitch.md", "# P\n\nreal body\n")
    rc = publish_review.main_argv(["--title", "P", "--md-file", str(md),
                                   "--ledger", str(tmp_path / "l.json")])
    assert rc == 0
    assert "EPISODE_URL: https://feed.here.now/ep-1.mp3" in capsys.readouterr().out


def test_main_argv_failure_returns_1(tmp_path, monkeypatch):
    monkeypatch.setattr(publish_review.subprocess, "run",
                        lambda *a, **k: _Proc(returncode=2, stderr="boom"))
    md = _write(tmp_path, "pitch.md", "# P\n\nbody\n")
    rc = publish_review.main_argv(["--title", "P", "--md-file", str(md),
                                   "--ledger", str(tmp_path / "l.json")])
    assert rc == 1
