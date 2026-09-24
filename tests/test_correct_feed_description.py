#!/usr/bin/env python3
"""Tests for correct_feed_description.py — the feed-correction primitive.

The metadata store is redirected to tmp_path using the REAL flat schema
(`{tag: {duration, description, mp3_size, artwork_url}}`, see publish.py). Only
the gh/git-touching calls (list_all_episodes, push_feed) are monkeypatched;
enrich_episodes and generate_feed run for real. No network, no feed writes.
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import correct_feed_description as cfd  # noqa: E402
import publish  # noqa: E402

TAG = "ep-2026-09-24-01"


def _release(tag, **kw):
    """What list_all_episodes() returns: GitHub-only facts, no duration, size 0."""
    return {"tag": tag, "title": f"Title {tag}", "published": "2026-09-24T11:01:51Z",
            "mp3_url": f"https://example.com/{tag}.mp3", "mp3_size": 0,
            "mp3_name": f"{tag}.mp3", "artwork_url": None, **kw}


@pytest.fixture
def store(monkeypatch, tmp_path):
    path = tmp_path / "episode-metadata.json"
    monkeypatch.setattr(publish, "EPISODE_META_FILE", str(path))
    return path


def test_update_replaces_description_and_keeps_stored_fields():
    meta = {TAG: {"description": "Today's Killen Time Update.", "duration": "1:31:36",
                  "mp3_size": 123, "artwork_url": "u"}}
    new = cfd.update_description(meta, TAG, "Corrected text.")
    assert new[TAG] == {"description": "Corrected text.", "duration": "1:31:36",
                        "mp3_size": 123, "artwork_url": "u"}
    assert "episodes" not in new
    assert meta[TAG]["description"] == "Today's Killen Time Update."  # input untouched


def test_update_creates_entry_for_tag_missing_from_store():
    new = cfd.update_description({"ep-other": {"description": "x"}}, TAG, "Note.")
    assert new[TAG] == {"description": "Note."}
    assert new["ep-other"] == {"description": "x"}


def test_update_refuses_to_blank_an_existing_item():
    with pytest.raises(ValueError):
        cfd.update_description({"ep-1": {"description": "x"}}, "ep-1", "   ")


def test_dry_run_changes_nothing(monkeypatch, capsys, store):
    store.write_text(json.dumps({TAG: {"description": "old"}}))
    monkeypatch.setattr(publish, "list_all_episodes", lambda: pytest.fail("dry-run must not hit GitHub"))
    rc = cfd.main([TAG, "new text", "--dry-run"])
    assert rc == 0
    assert "new text" in capsys.readouterr().out
    assert json.loads(store.read_text())[TAG]["description"] == "old"


def test_main_description_reaches_feed_and_durations_survive(monkeypatch, store):
    store.write_text(json.dumps({
        TAG: {"description": "old", "duration": "1:31:36", "mp3_size": 55555, "artwork_url": "https://a/1.jpg"},
        "ep-2026-09-23-01": {"description": "d2", "duration": "0:45:00", "mp3_size": 4444},
    }))
    calls = {}
    monkeypatch.setattr(publish, "list_all_episodes",
                        lambda: [_release(TAG), _release("ep-2026-09-23-01")])
    real_generate = publish.generate_feed
    monkeypatch.setattr(publish, "generate_feed",
                        lambda eps: (calls.update(feed=[dict(e) for e in eps]), real_generate(eps))[1])
    monkeypatch.setattr(publish, "push_feed", lambda xml, art=None: calls.update(pushed=(xml, art)))

    rc = cfd.main([TAG, "Correction: the count was wrong."])

    assert rc == 0
    by_tag = {e["tag"]: e for e in calls["feed"]}
    # correction text reaches generate_feed's input ...
    assert by_tag[TAG]["description"] == "Correction: the count was wrong."
    # ... and every episode keeps its stored duration / size / artwork
    assert by_tag[TAG]["duration"] == "1:31:36"
    assert by_tag[TAG]["mp3_size"] == 55555
    assert by_tag[TAG]["artwork_url"] == "https://a/1.jpg"
    assert by_tag["ep-2026-09-23-01"]["description"] == "d2"
    assert by_tag["ep-2026-09-23-01"]["duration"] == "0:45:00"
    assert by_tag["ep-2026-09-23-01"]["mp3_size"] == 4444
    # the rendered XML carries it too
    xml = calls["pushed"][0]
    assert "Correction: the count was wrong." in xml
    assert "1:31:36" in xml
    assert calls["pushed"][1] == cfd.DEFAULT_ARTWORK
    # store: flat schema, no stray "episodes" key, other fields preserved
    saved = json.loads(store.read_text())
    assert "episodes" not in saved
    assert saved[TAG]["description"] == "Correction: the count was wrong."
    assert saved[TAG]["duration"] == "1:31:36"


def test_main_refuses_unknown_tag_and_leaves_store_untouched(monkeypatch, store):
    original = {"ep-other": {"description": "keep", "duration": "1:00"}}
    store.write_text(json.dumps(original))
    monkeypatch.setattr(publish, "list_all_episodes", lambda: [_release("ep-other")])
    monkeypatch.setattr(publish, "push_feed", lambda *a, **k: pytest.fail("must not push"))
    rc = cfd.main(["ep-nope", "text"])
    assert rc == 1
    assert json.loads(store.read_text()) == original


def test_unknown_tag_does_not_create_store_file(monkeypatch, store):
    monkeypatch.setattr(publish, "list_all_episodes", lambda: [_release("ep-other")])
    assert cfd.main(["ep-nope", "text"]) == 1
    assert not store.exists()
