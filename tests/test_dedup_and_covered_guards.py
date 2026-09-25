#!/usr/bin/env python3
"""Tests for dedup_guard.py, covered_guard.py, the writer evidence rules and the
COVERED_DEFER ledger deferral — the 2026-09-25 fabrication / covered-file-poisoning fixes.
"""
import json
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import covered_guard  # noqa: E402
import dedup_guard  # noqa: E402

FILLER = ("the quick analysis of the semiconductor export controls suggests that regulators "
          "will keep tightening licensing rules through next spring according to two people "
          "familiar with the drafting process at the commerce department ")


def _script(*paras):
    """A script where every paragraph is a speaker block, alternating BASIL/BROOKE."""
    out = []
    for i, p in enumerate(paras):
        out.append(f"[{'BASIL' if i % 2 == 0 else 'BROOKE'}] {p}")
    return "\n\n".join(out) + "\n"


def _write(dirpath, name, text):
    p = dirpath / name
    p.write_text(text)
    return p


# ── dedup_guard ──────────────────────────────────────────────────────────────

def test_prior_scripts_window_excludes_today_and_older(tmp_path):
    for d in ("2026-09-17", "2026-09-18", "2026-09-24", "2026-09-25"):
        _write(tmp_path, f"killen-time-{d}.txt", "x")
    _write(tmp_path, "killen-time-2026-09-24-02.txt", "x")
    _write(tmp_path, "killen-time-2026-09-23.txt.unaired-partial", "x")
    names = [p.name for p in dedup_guard.prior_scripts("2026-09-25", 7, tmp_path)]
    assert names == ["killen-time-2026-09-18.txt", "killen-time-2026-09-24-02.txt",
                     "killen-time-2026-09-24.txt"]


def test_find_repeats_flags_a_reaired_block_and_not_fresh_ones(tmp_path):
    old = _write(tmp_path, "killen-time-2026-09-22.txt", _script(FILLER * 2, "unrelated old block " * 30))
    draft = _script("A completely different story about basketball trades and salary caps " * 6,
                    FILLER * 2)
    flags = dedup_guard.find_repeats(draft, [old])
    assert [f["block_no"] for f in flags] == [2]
    assert flags[0]["episode"] == "killen-time-2026-09-22.txt"
    assert flags[0]["overlap"] >= 0.9


def test_find_repeats_ignores_short_banter(tmp_path):
    old = _write(tmp_path, "killen-time-2026-09-22.txt", _script("Right, exactly, that is the point."))
    assert dedup_guard.find_repeats(_script("Right, exactly, that is the point."), [old]) == []


def test_digest_lists_segment_openers_newest_last(tmp_path):
    _write(tmp_path, "killen-time-2026-09-21.txt",
           _script("First opener of monday. more words") + "\n[TRANSITION]\n\n" + _script("Second segment opener"))
    _write(tmp_path, "killen-time-2026-09-24.txt", _script("Thursday opener here"))
    d = dedup_guard.digest("2026-09-25", 7, tmp_path)
    assert d.index("2026-09-21") < d.index("2026-09-24")
    assert "First opener of monday" in d and "Second segment opener" in d and "Thursday opener" in d


def test_check_cli_exit_code(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(dedup_guard, "SCRIPTS_DIR", tmp_path)
    _write(tmp_path, "killen-time-2026-09-22.txt", _script(FILLER * 2))
    draft = _write(tmp_path, "killen-time-2026-09-25.txt", _script(FILLER * 2))
    assert dedup_guard.main(["check", str(draft), "--today", "2026-09-25"]) == 3
    assert "already aired" in capsys.readouterr().out
    fresh = _write(tmp_path, "fresh.txt", _script("nothing seen before about volcanoes and lava tubes " * 8))
    assert dedup_guard.main(["check", str(fresh), "--today", "2026-09-25"]) == 0


# ── covered_guard ────────────────────────────────────────────────────────────

FINAL = (
    _script("Good morning. Scott Alexander untangled neuralese this week and OpenAI's Jakub Pachocki says the depth is within 2x of GPT-4 " * 4)
    + "\n[TRANSITION]\n\n"
    + _script("Percy Hynes White and Jeff Wahlberg are cast in Crime Novella from Omar de Soto, shot on 35mm film for Deadline " * 4)
)


def test_derive_uses_only_the_final_script_text():
    d = covered_guard.derive(FINAL, "2026-09-25", transcript_dirs=[])
    assert d["derived_from"] == "final-script"
    blob = json.dumps(d).lower()
    assert "pachocki" in blob and "crime novella" in blob
    assert "knicks" not in blob            # a draft-only story can never appear
    assert d["stories"] == sorted(d["segments"])
    assert d["podcast_guids"] == []


def test_used_guids_only_counts_transcripts_the_script_drew_from(tmp_path):
    used = tmp_path / "podcast_guid-used.txt"
    unused = tmp_path / "podcast_guid-unused.txt"
    used.write_text("noise before " + FINAL.replace("[BASIL] ", "").replace("[BROOKE] ", "") + " noise after")
    unused.write_text("a wholly unrelated conversation about gardening and soil acidity " * 40)
    old = tmp_path / "podcast_guid-old.txt"
    old.write_text(used.read_text())
    stale = time.time() - 5 * 86400
    os.utime(old, (stale, stale))
    assert covered_guard.used_guids(FINAL, [tmp_path]) == ["guid-used"]


def test_commit_replaces_a_poisoned_ledger(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / ".covered-2026-09-25.json").write_text(json.dumps(
        {"stories": ["fabricated-knicks-preview"], "segments": {"fabricated-knicks-preview": "invented"},
         "podcast_guids": ["never-read"], "last_episode": "x"}))
    final = tmp_path / "killen-time-2026-09-25.txt"
    final.write_text(FINAL)
    covered_guard.commit(final, "2026-09-25", scripts_dir=scripts, transcript_dirs=[])
    data = json.loads((scripts / ".covered-2026-09-25.json").read_text())
    assert "fabricated-knicks-preview" not in data["stories"]
    assert "never-read" not in data["podcast_guids"]
    assert any("pachocki" in v.lower() for v in data["segments"].values())
    assert not list(scripts.glob("*.tmp"))       # atomic write left nothing behind


# ── ledger deferral (ingest.save_covered_stories under COVERED_DEFER=1) ──────

def test_save_covered_stories_defers_to_pending_when_flag_set(tmp_path, monkeypatch):
    ingest = pytest.importorskip("ingest")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    monkeypatch.setattr(ingest, "SCRIPTS_DIR", scripts)
    monkeypatch.setenv("COVERED_DEFER", "1")
    ingest.save_covered_stories(["draft-story"], {"draft-story": "s"}, podcast_guids=["g1"])
    assert not list(scripts.glob(".covered-*.json")), "draft claim must not reach the live ledger"
    pending = list((tmp_path / ".tmp").glob("covered-pending-*.json"))
    assert len(pending) == 1 and "draft-story" in pending[0].read_text()
    monkeypatch.delenv("COVERED_DEFER")
    ingest.save_covered_stories(["manual"], {"manual": "s"})
    assert list(scripts.glob(".covered-*.json")), "without the flag the legacy behaviour is unchanged"


# ── writer prompts carry the evidence rules ─────────────────────────────────

BRIEF = """# Topic Brief

## 1. [Podcast] Sharp Tech preview
Type: podcast (transcript available)
Link: x

body

## 2. [Podcast] Plain English on AI
Type: podcast (no transcript)
Link: y

## 3. Kalshi Steph Curry
Type: substack (full text (3944 words))
"""


def test_evidence_ledger_marks_no_transcript_items_blurb_only():
    or_writer = pytest.importorskip("or_writer")
    ledger = or_writer._evidence_ledger(BRIEF)
    lines = ledger.splitlines()
    assert "usable ONLY if its text is inlined" in lines[0]
    assert "NO TRANSCRIPT" in lines[1] and "blurb only" in lines[1]
    assert "full article text" in lines[2]


def test_pass_prompts_include_rules_ledger_and_digest():
    or_writer = pytest.importorskip("or_writer")
    src = {"claude_md": "", "topic_brief": BRIEF, "build_pitches": "", "transcripts": [], "articles": [],
           "recent_scripts": [], "covered": [],
           "evidence_rules": "NO TRANSCRIPT = BLURB ONLY", "evidence_ledger": or_writer._evidence_ledger(BRIEF),
           "aired_digest": "killen-time-2026-09-24.txt:\n  · Thursday opener"}
    p1 = or_writer._pass1_prompt(src, "morning")
    p2 = or_writer._pass2_prompt(src, "morning", "[BASIL] first half\n\n[TRANSITION]\n")
    for p in (p1, p2):
        assert "NO TRANSCRIPT = BLURB ONLY" in p
        assert "AIRED IN THE LAST 7 DAYS" in p and "Thursday opener" in p
        assert "EVIDENCE LEDGER" in p
        assert "COVERED_JSON" not in p, "the writer no longer files the ledger"
    assert "no transcript" in or_writer.SYSTEM.lower()


def test_evidence_rules_file_states_the_blurb_rule():
    text = open(os.path.join(ROOT, ".claude", "context", "evidence-rules.md")).read()
    assert "NO TRANSCRIPT = BLURB ONLY" in text
    assert "last 7 days" in text


def test_generate_episode_wires_the_guards():
    sh = open(os.path.join(ROOT, "generate-episode.sh")).read()
    assert "export COVERED_DEFER=1" in sh
    # ledger is committed only after publish succeeded, never before QC
    assert sh.index("covered_guard.py commit") > sh.index('log "Publish complete"') > sh.index("QC VERDICT")
    assert "dedup_guard.py check" in sh and "dedup_guard.py digest" in sh
    assert "trap 'rg_on_exit" in sh and "rg_finish ok" in sh
