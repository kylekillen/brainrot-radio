#!/usr/bin/env python3
"""Tests for render_report.py (CONTRACT A) and the publish() return-value change.

All external effects are monkeypatched: kokoro HTTP (requests.post/get),
ffmpeg/ffprobe (subprocess.run), and publish(). No network, no TTS, no ffmpeg.
"""
import os
import re
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import render_report  # noqa: E402


FAKE_MP3_BYTES = b"\xff\xfb" + b"\x00" * 4096  # > 500 bytes so tts() accepts it
FAKE_URLS = {"mp3": "https://example.com/fake-episode.mp3"}


class _Resp:
    def __init__(self, ok=True, content=b"", json_data=None, status=200):
        self.ok = ok
        self.content = content
        self.status_code = status
        self._json = json_data or {}

    def json(self):
        return self._json


@pytest.fixture
def fake_kokoro(monkeypatch):
    """Healthy kokoro that returns fake mp3 bytes for every TTS request."""
    def fake_get(url, *a, **k):
        return _Resp(ok=True, json_data={"ok": True})

    def fake_post(url, *a, **k):
        return _Resp(ok=True, content=FAKE_MP3_BYTES)

    monkeypatch.setattr(render_report.requests, "get", fake_get)
    monkeypatch.setattr(render_report.requests, "post", fake_post)


@pytest.fixture
def fake_ffmpeg(monkeypatch):
    """Stub subprocess.run: ffmpeg writes a fake mp3, ffprobe reports a duration."""
    real_run = subprocess.run

    def fake_run(cmd, *a, **k):
        prog = cmd[0] if isinstance(cmd, (list, tuple)) else cmd
        if prog == render_report.FFMPEG:
            # last arg is the output mp3 path
            out = cmd[-1]
            with open(out, "wb") as f:
                f.write(FAKE_MP3_BYTES)
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        if prog == render_report.FFPROBE:
            return subprocess.CompletedProcess(cmd, 0, "123.4\n", "")
        return real_run(cmd, *a, **k)

    monkeypatch.setattr(render_report.subprocess, "run", fake_run)


@pytest.fixture
def captured_publish(monkeypatch):
    """Replace publish() with a stub that records its args and returns fake urls."""
    calls = {}

    def fake_publish(mp3_path, title=None, description=None, **k):
        calls["mp3_path"] = mp3_path
        calls["title"] = title
        calls["description"] = description
        return dict(FAKE_URLS)

    monkeypatch.setattr(render_report, "publish", fake_publish)
    return calls


def _write(tmp_path, text):
    p = tmp_path / "report.txt"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_short_text_renders_and_publishes(
    tmp_path, capsys, fake_kokoro, fake_ffmpeg, captured_publish
):
    """A short (well under 6000-word) report still renders + publishes (floorless)."""
    short = "This is a short report.\n\nIt has two paragraphs and is far under any floor."
    assert len(short.split()) < 6000
    text_file = _write(tmp_path, short)

    rc = render_report.main_argv(["--title", "Tiny Report", "--text-file", text_file])

    assert rc == 0
    # (a) it actually published
    assert captured_publish.get("mp3_path")
    # (b) generated mp3 filename matches the killen-time-<date> contract
    fname = os.path.basename(captured_publish["mp3_path"])
    assert re.match(r"^killen-time-\d{4}-\d{2}-\d{2}(?:-\d{2})?\.mp3$", fname), fname
    # (c) final stdout line is the EPISODE_URL contract, exit 0
    out_lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    assert out_lines[-1] == f"EPISODE_URL: {FAKE_URLS['mp3']}"


def test_title_and_description_forwarded(
    tmp_path, fake_kokoro, fake_ffmpeg, captured_publish
):
    text_file = _write(tmp_path, "Body text for the episode.")
    rc = render_report.main_argv(
        ["--title", "My Title", "--text-file", text_file, "--description", "My Desc"]
    )
    assert rc == 0
    assert captured_publish["title"] == "My Title"
    assert captured_publish["description"] == "My Desc"


def test_kokoro_unreachable_nonzero(
    tmp_path, monkeypatch, capsys, captured_publish
):
    """Kokoro health never returns ok => nonzero exit, no publish."""
    monkeypatch.setattr(render_report.time, "sleep", lambda *a, **k: None)

    def dead_get(url, *a, **k):
        return _Resp(ok=False, json_data={"ok": False})

    monkeypatch.setattr(render_report.requests, "get", dead_get)

    text_file = _write(tmp_path, "Some text that will never render.")
    rc = render_report.main_argv(["--title", "Doomed", "--text-file", text_file])

    assert rc != 0
    assert "ERROR" in capsys.readouterr().err
    assert not captured_publish  # publish() never called


def test_empty_text_file_nonzero(tmp_path, captured_publish):
    text_file = _write(tmp_path, "   \n\n  ")
    rc = render_report.main_argv(["--title", "Empty", "--text-file", text_file])
    assert rc != 0
    assert not captured_publish


def test_publish_returns_urls_dict(monkeypatch):
    """publish() now RETURNS the urls dict it builds (additive change)."""
    import publish as publish_mod

    monkeypatch.setattr(publish_mod, "next_episode_number", lambda d: 1)
    monkeypatch.setattr(
        publish_mod, "upload_to_github",
        lambda *a, **k: {"mp3": "https://example.com/x/killen-time-2026-06-22.mp3"},
    )
    monkeypatch.setattr(publish_mod, "get_mp3_metadata", lambda p: {"size": 1000, "duration_secs": 60})
    monkeypatch.setattr(publish_mod, "load_episode_metadata", lambda: {})
    monkeypatch.setattr(publish_mod, "save_episode_metadata", lambda m: None)
    monkeypatch.setattr(publish_mod, "list_all_episodes", lambda: [])
    monkeypatch.setattr(publish_mod, "generate_feed", lambda eps: "<rss/>")
    monkeypatch.setattr(publish_mod, "push_feed", lambda xml, art=None: None)
    monkeypatch.setattr(publish_mod, "update_covered_stories", lambda p: None)
    monkeypatch.setattr(publish_mod, "_notify_published", lambda *a, **k: None)
    monkeypatch.setattr(publish_mod.os.path, "abspath", lambda p: p)

    urls = publish_mod.publish("killen-time-2026-06-22.mp3", "T", "D")
    assert isinstance(urls, dict)
    assert urls["mp3"].endswith("killen-time-2026-06-22.mp3")
