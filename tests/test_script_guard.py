#!/usr/bin/env python3
"""Direct unit tests for script_guard.py's three rules.

The module shipped in PR #50 with no tests of its own: its only coverage was the
generator test asserting it gets CALLED. These exercise the rule bodies, because
`leaks()` is the one whose consumer edits MUST-FIX hits straight out of the script
(generate-episode.sh), so a false positive here is a cut sentence, not a number.

The archive test is the regression for the 2026-10-01 review finding. `worktree` sat
in LEAK_PATTERNS and fired on killen-time-2026-09-24.txt:61 — the Cline Desktop
git-worktree passage, inside the show's own "Agents & Building With AI" beat. Any
token added to LEAK_PATTERNS must be one that has no innocent on-air use; this test
is what stops the next generic word from being promoted into a MUST-FIX.
"""
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import script_guard  # noqa: E402


# ── speaker_collisions ───────────────────────────────────────────────────────

def test_two_blocks_by_the_same_host_collide():
    text = "[BASIL] One.\n\n[BASIL] Two.\n\n[BROOKE] Three.\n"
    found = script_guard.speaker_collisions(text)
    assert [f["rule"] for f in found] == ["speaker_collision"]
    assert found[0]["line"] == 3 and found[0]["previous_line"] == 1
    assert found[0]["speaker"] == "BASIL"


def test_alternating_hosts_are_clean():
    assert script_guard.speaker_collisions(
        "[BASIL] One.\n\n[BROOKE] Two.\n\n[BASIL] Three.\n") == []


def test_transition_between_two_blocks_is_still_a_collision():
    """BASIL / [TRANSITION] / BASIL is the two-pass join defect, not a clean join."""
    text = "[BASIL] Sign-off.\n\n[TRANSITION] And that's the show.\n\n[BASIL] Wait.\n"
    found = script_guard.speaker_collisions(text)
    assert [f["rule"] for f in found] == ["speaker_collision"]
    assert found[0]["speaker"] == "BASIL"


def test_two_transitions_back_to_back_are_flagged_once():
    text = "[BASIL] A.\n\n[TRANSITION] B.\n\n[TRANSITION] C.\n\n[BROOKE] D.\n"
    found = script_guard.speaker_collisions(text)
    assert [f["rule"] for f in found] == ["back_to_back_transition"]


# ── leaks ────────────────────────────────────────────────────────────────────

def test_unambiguous_private_markers_still_fire():
    """The trim must not disarm the rule — the real 09-24 leak is still caught."""
    for phrase, rule in (
        ("observer-system had twenty-seven launch sites", "internal_name"),
        ("it's all in the build-pitches folder", "private_system"),
        ("the fleet budget is not the point", "private_system"),
        ("our agents each get a lane", "internal_metric"),
        ("I greenlighted the build yesterday", "internal_metric"),
    ):
        found = script_guard.leaks(phrase)
        assert found, f"no longer flagged: {phrase!r}"
        assert found[0]["rule"] == rule, (phrase, found)


def test_generic_on_air_vocabulary_is_not_a_leak():
    """Every phrase here is ordinary show content; flagging it costs a real sentence."""
    clean = [
        "Cline Desktop added git worktrees and parallel subagents, and the pattern "
        "worth stealing is the author-and-janitor split.",
        "You want a sweeper loop that clears stale branches overnight.",
        "Make a .venv, pip install the package, and freeze the lockfile.",
        "defaults read the plist, or you edit it by hand.",
        "Quantum mechanics calls it the observer effect; so does every economist.",
        "Here is a git worktree you can throw away when the branch goes stale.",
    ]
    for phrase in clean:
        assert not script_guard.leaks(phrase), f"false positive on {phrase!r}"


def test_leak_finding_carries_line_match_and_context():
    found = script_guard.leaks("[BASIL] Fine.\n\n[BROOKE] See observer-system for it.\n")
    assert len(found) == 1
    assert found[0]["line"] == 3
    assert "observer-system" in found[0]["context"]


def test_the_aired_archive_has_no_false_positive_leaks():
    """Replay real aired scripts. Fails on killen-time-2026-09-24.txt:61 pre-fix."""
    paths = sorted(glob.glob(os.path.join(ROOT, "test-runs", "*", "scripts", "*.txt")))
    assert paths, "no archived scripts found — the regression would pass vacuously"
    for path in paths:
        text = open(path, errors="replace").read()
        # observer-system / build-pitches really are on air in these episodes (that
        # was the 09-24 incident) and MUST keep firing; what must not appear is a
        # finding on ordinary vocabulary, so allow only the two known-real markers.
        findings = [f for f in script_guard.leaks(text)
                    if f["rule"] not in ("internal_name", "private_system")
                    or f["match"].lower() not in ("observer-system", "build-pitches")]
        assert not findings, (
            f"{os.path.relpath(path, ROOT)} false positives: "
            + "; ".join(f"L{f['line']} {f['rule']} {f['match']!r}" for f in findings))


# ── unsourced_bylines ────────────────────────────────────────────────────────

BRIEF = """## 1. TSMC bet on overseas fabs (Mei Chen / Nikkei Asia): the company says
capacity at its Arizona plant will double by next year and
"""

SCRIPT = """[BASIL] Mei Chen argues the fab is a bet on subsidies.
"""


def test_name_only_on_a_truncated_byline_is_reported(tmp_path):
    found = script_guard.unsourced_bylines(SCRIPT, BRIEF)
    assert [f["rule"] for f in found] == ["unsourced_byline"]
    assert found[0]["match"] == "Chen"
    assert found[0]["line"] == 1


def test_a_name_present_in_the_sources_is_not_reported(tmp_path):
    src = tmp_path / "article.txt"
    src.write_text("Mei Chen has covered semiconductors for a decade.")
    assert script_guard.unsourced_bylines(SCRIPT, BRIEF, [src]) == []


def test_a_full_credit_line_is_not_a_byline_claim():
    """Attribution without an attribution verb is not invented analysis."""
    assert script_guard.unsourced_bylines("[BASIL] Mei Chen, on the fab.\n", BRIEF) == []


def test_plain_mention_of_a_name_is_not_flagged():
    assert script_guard.unsourced_bylines(
        "[BASIL] TSMC is building in Arizona.\n", BRIEF) == []
