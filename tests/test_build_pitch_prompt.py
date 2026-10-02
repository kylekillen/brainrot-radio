#!/usr/bin/env python3
"""Regression tests for the 2026-09-29 defect: the pass-1 writer prompt ORDERED a
line that QC deletes as a MUST-FIX, every episode.

The "BUILD PITCH OF THE DAY" bullet in generate-episode.sh used to end "Then have
a host say plainly that it's logged in the build-pitches folder so Kyle can point
an agent at it and greenlight the build if he likes it." QC's Coherence Skeptic then
deleted that exact sentence under the GUARDRAILS row "Never include internal fleet
state" — it names an internal folder and Kyle's private review lane. So every
episode paid a writer edit for a line the prompt had just requested. It is not
merely wasteful: replaying script_guard.py over the aired archive shows the line
survived QC and reached the microphone on 18 of the 26 September scripts.

These tests lock the fix and the surrounding ban, so neither half can drift back.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SH = os.path.join(ROOT, "generate-episode.sh")


def _read(rel):
    with open(os.path.join(ROOT, rel)) as f:
        return f.read()


def _bullet(sh):
    """The BUILD PITCH OF THE DAY bullet, pass-1 prompt."""
    lines = [l for l in sh.split("\n") if "**BUILD PITCH OF THE DAY:**" in l]
    assert len(lines) == 1, (
        f"expected exactly one BUILD PITCH OF THE DAY bullet, found {len(lines)}: "
        "a second copy in another pass can drift from this one untested")
    return lines[0]


def test_prompt_no_longer_orders_the_folder_locator():
    sh = _read("generate-episode.sh")
    bullet = _bullet(sh)
    assert "build-pitches folder" not in bullet, (
        "the pass-1 prompt must not tell the writer to name the build-pitches "
        "folder on air — QC deletes that sentence as a MUST-FIX")
    assert "logged in the build-pitches" not in bullet
    # the whole ordered sentence, gone in any form
    for m in re.finditer(r"logged in (the )?build-pitches", sh):
        raise AssertionError(f"generator still orders the leak at offset {m.start()}")


def test_prompt_asks_for_a_general_on_air_pointer():
    bullet = _bullet(_read("generate-episode.sh"))
    assert "WRITTEN UP AND LOGGED" in bullet, (
        "the bullet must still ask for the sign-off — the fix is to generalise "
        "it, not to drop it (the Build Pitch beat is Kyle's standing request)")
    assert "so he can point an agent at it" in bullet
    assert "in GENERAL terms only" in bullet
    assert "LEAVE THE SENTENCE OUT" in bullet, (
        "give the writer an explicit out; otherwise it invents a path to satisfy "
        "the instruction, which is how the original leak survived prompt edits")


def test_prompt_still_bans_the_private_system_and_the_off_air_sections():
    """The 2026-09-24 fix (tests/test_no_private_system_on_air.py) must not regress."""
    bullet = _bullet(_read("generate-episode.sh"))
    assert "Keep the listener's private system out of the audio" in bullet
    assert "observer-system, brainrot-radio" in bullet
    assert "launch-site counts" in bullet
    assert "\"Evidence it's real\" and \"local check\" sections are for Kyle" in bullet
    assert "not for airtime" in bullet


def test_the_sanctioned_sentence_passes_the_deterministic_guard():
    """The prompt's on-air sentence must not trip script_guard.py's leak rule.

    Guarding the contradiction in both directions: an earlier draft of
    script_guard.py flagged `point an agent at` / `greenlight the build`, which
    would have re-created the exact MUST-FIX the prompt fix exists to remove.
    """
    import sys
    sys.path.insert(0, ROOT)
    import script_guard

    bullet = _bullet(_read("generate-episode.sh"))
    m = re.search(r"say plainly that (.*?) — in GENERAL terms only", bullet)
    assert m, "could not lift the sanctioned sentence out of the prompt"
    sentence = ("The pitch is " + m.group(1).rstrip(".").lower() + ".")
    assert not script_guard.leaks(sentence), (
        f"the sentence the prompt orders is itself a leak: {script_guard.leaks(sentence)}")
    # ...and the thing it replaced still is.
    assert script_guard.leaks(
        "It's logged in the build-pitches folder, dated today, so Kyle can point "
        "an agent at it and greenlight the build whenever he wants.")


def test_pipeline_runs_the_guard_before_and_after_qc():
    sh = _read("generate-episode.sh")
    pre = sh.index("QC_GUARD_FLAGS=$(python3 script_guard.py check")
    assert pre < sh.index("cat > \"$BRAINROT_DIR/.tmp/step3-qc.txt\""), (
        "the guard must feed QC, not run after it")
    assert "${QC_GUARD_BLOCK}" in sh, "guard findings must reach the QC prompt"
    post = sh.index("POST_GUARD=$(python3 script_guard.py check")
    assert post > sh.index("QC VERDICT"), "the post-QC re-check must run after QC"
    assert post < sh.index("python3 voice.py"), "and before the render"
    # Non-fatal on purpose: 09-25, 09-27 and 09-29 were all lost to hard gates.
    tail = sh[post:post + 900]
    assert "exit 1" not in tail, "script_guard must never abort the pipeline"
    assert "logs/guard-$RUN_ID.flag" in tail, "findings must leave a flag file"
