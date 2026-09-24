#!/usr/bin/env python3
"""Tests for correct_feed_description.py — the feed-correction primitive.

External effects (the metadata store, gh, git push) are monkeypatched or
redirected to tmp_path. No network, no GitHub, no real feed writes.
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import correct_feed_description as cfd  # noqa: E402
import publish  # noqa: E402


def test_update_replaces_description_and_keeps_stored_fields():
    meta = {"episodes": {"ep-2026-09-24-01": {"description": "Today's Killen Time Update.",
                                               "duration": "1:31:36", "artwork_url": "u"}}}
    new = cfd.update_description(meta, "ep-2026-09-24-01", "Corrected text.")
    assert new["episodes"]["ep-2026-09-24-01"]["description"] == "Corrected text."
    assert new["episodes"]["ep-2026-09-24-01"]["duration"] == "1:31:36"
    assert new["episodes"]["ep-2026-09-24-01"]["artwork_url"] == "u"
    # input untouched
    assert meta["episodes"]["ep-2026-09-24-01"]["description"] == "Today's Killen Time Update."


def test_update_refuses_to_blank_an_existing_item():
    meta = {"episodes": {"ep-1": {"description": "x"}}}
    with pytest.raises(ValueError):
        cfd.update_description(meta, "ep-1", "   ")


def test_dry_run_changes_nothing(monkeypatch, capsys, tmp_path):
    store = tmp_path / "episode-metadata.json"
    store.write_text(json.dumps({"episodes": {"ep-1": {"description": "old"}}}))
    monkeypatch.setattr(publish, "load_episode_metadata", lambda: json.loads(store.read_text()))
    monkeypatch.setattr(publish, "save_episode_metadata", lambda m: pytest.fail("dry-run must not save"))
    rc = cfd.main(["ep-1", "new text", "--dry-run"])
    assert rc == 0
    assert "new text" in capsys.readouterr().out
    assert json.loads(store.read_text())["episodes"]["ep-1"]["description"] == "old"


def test_main_updates_store_regenerates_and_pushes(monkeypatch, tmp_path):
    store = tmp_path / "episode-metadata.json"
    store.write_text(json.dumps({"episodes": {"ep-1": {"description": "old", "duration": "1:00"}}}))
    calls = {}
    monkeypatch.setattr(publish, "load_episode_metadata", lambda: json.loads(store.read_text()))
    monkeypatch.setattr(publish, "save_episode_metadata", lambda m: store.write_text(json.dumps(m)))
    monkeypatch.setattr(publish, "list_all_episodes", lambda: [{"tag": "ep-1", "title": "t", "description": "old",
                                                                "published": "2026-09-24T11:01:51Z", "mp3_url": "u",
                                                                "artwork_url": "a", "duration": "1:00"}])
    monkeypatch.setattr(publish, "generate_feed", lambda eps: (calls.update(feed=eps), "<rss/>")[1])
    monkeypatch.setattr(publish, "push_feed", lambda xml, art=None: calls.update(pushed=(xml, art)))
    rc = cfd.main(["ep-1", "Correction: the count was wrong."])
    assert rc == 0
    assert calls["pushed"][0] == "<rss/>"
    assert calls["feed"][0]["tag"] == "ep-1", "generate_feed must receive the release list"
    assert calls["pushed"][1] == cfd.DEFAULT_ARTWORK
    saved = json.loads(store.read_text())
    assert saved["episodes"]["ep-1"]["description"] == "Correction: the count was wrong."
    assert saved["episodes"]["ep-1"]["duration"] == "1:00"


def test_main_refuses_unknown_tag_after_store_write(monkeypatch, tmp_path):
    """A tag that isn't a GitHub release must not leave a store entry behind."""
    store = tmp_path / "episode-metadata.json"
    store.write_text(json.dumps({"episodes": {}}))
    monkeypatch.setattr(publish, "load_episode_metadata", lambda: json.loads(store.read_text()))
    monkeypatch.setattr(publish, "save_episode_metadata", lambda m: store.write_text(json.dumps(m)))
    monkeypatch.setattr(publish, "list_all_episodes", lambda: [{"tag": "ep-other"}])
    rc = cfd.main(["ep-nope", "text"])
    assert rc == 1
