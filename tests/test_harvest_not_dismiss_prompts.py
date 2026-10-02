#!/usr/bin/env python3
"""The build-pitch reporter brief lives in FOUR copies. Keep them from drifting.

PR #40 (harvest-not-dismiss) replaced "discard anything Kyle already runs" with a
harvest-the-delta rule — Kyle, 2026-09-27: "we already do this" is a strange
default posture. It landed in .claude/context/beats/claude-lab.md and
gemini_buildpitch.py, but the same brief is duplicated into two more places the
reporter actually reads on the default automated build-pitch path:

  * beats.json's claude_lab "editorial_notes"  (generate-episode.sh:247 tells the
    reporter to read it alongside the context file)
  * the inline prompt heredoc in generate-episode.sh

Both still told the reporter to discard any technique Kyle already runs, so the
reporter was handed the harvest rule and the reject rule in the same prompt and
could keep the exact dismissive behavior the PR set out to remove.

These tests assert the four copies agree: none may carry a discard-because-already
instruction, all must carry the delta rule, and all must keep the verification bar
so the conflict can't be "resolved" by deleting the bar instead.

A FIFTH surface is covered too — build-pitches/README.md, the human-facing
description of the beat. It is not read by the reporter, so it cannot change
behaviour, but it drifted anyway: it kept describing the pre-#40 reject rule for
two days after the merge, and the only reason anyone noticed was a human reading
it. The same assertions are cheap to run against it.
"""
import io
import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A discard-style verb whose object is a technique Kyle already runs. Sentence
# punctuation bounds the span so a verb in one instruction can't reach across
# into the next.
REJECT_EXISTING = re.compile(
    r"(?is)\b(?:discard|reject|drop|skip|exclude|filter\s+out)\b"
    r"[^.;!?]{0,160}?\balready\b[^.;!?]{0,40}?\b(?:runs?|does|do|has|have|uses?)\b"
)
# A correct phrasing may negate the verb ("do not discard what Kyle already runs").
# Only a negation immediately attached to the verb is exempt, so the original
# "…, (not a demo/hype), discard what's vague or what Kyle already runs" still trips.
_NEGATED = re.compile(r"(?i)(?:\bnot|\bnever|n't|\bno)\s*$")


def _read(rel):
    with io.open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _claude_lab_editorial_notes():
    beats = json.loads(_read("beats.json"))["beats"]
    return [b for b in beats if b["id"] == "claude_lab"][0]["editorial_notes"]


def _step1b_prompt():
    sh = _read("generate-episode.sh")
    start = sh.index("<<PROMPT_EOF")
    end = sh.index("\nPROMPT_EOF", start)
    return sh[start:end]


COPIES = {
    "beats.json:claude_lab": _claude_lab_editorial_notes,
    "generate-episode.sh:step1b": _step1b_prompt,
    ".claude/context/beats/claude-lab.md": lambda: _read(".claude/context/beats/claude-lab.md"),
    "gemini_buildpitch.py": lambda: _read("gemini_buildpitch.py"),
    # Human-facing, never read by the reporter — guarded because it is the copy
    # a person (or the next agent) actually reads when asking "what is this beat?".
    "build-pitches/README.md": lambda: _read("build-pitches/README.md"),
}
IDS = sorted(COPIES)


def _rejections(text):
    out = []
    for m in REJECT_EXISTING.finditer(text):
        if _NEGATED.search(text[max(0, m.start() - 8):m.start()]):
            continue
        out.append(m.group(0).replace("\n", " ")[:120])
    return out


def test_detector_actually_fires_on_the_pre_fix_wording():
    """Guard the guard: if the regex rots, every other test here passes silently."""
    for old in (
        "discard what's vague or what Kyle already runs.",
        "Discard anything vague, unverifiable, contradicted by other sources, "
        "or that Kyle already does (his stack: observer-system).",
        "Reject anything Kyle already runs (observer-system, COS).",
    ):
        assert _rejections(old), "detector must flag a reject-because-already instruction: %r" % old
    # ...and must NOT flag the harvest rule or a correctly negated instruction.
    for good in (
        "Overlap with his stack is not a disqualifier — a technique close to something "
        "he already runs is still in play. Name the DELTA instead.",
        "never \"do we already do this?\" — name the DELTA.",
        "Discard anything vague, unverifiable, or contradicted by other sources.",
    ):
        assert not _rejections(good), "detector false-positives on: %r" % good


@pytest.mark.parametrize("copy", IDS)
def test_copy_is_not_empty(copy):
    """An extraction bug must fail loudly, not pass as 'no violations found'."""
    text = COPIES[copy]()
    assert len(text) > 500, "%s: extraction returned %d chars — fix the extractor" % (copy, len(text))


@pytest.mark.parametrize("copy", IDS)
def test_no_copy_tells_the_reporter_to_discard_what_kyle_already_runs(copy):
    bad = _rejections(COPIES[copy]())
    assert not bad, "%s still tells the reporter to discard on overlap: %r" % (copy, bad)


@pytest.mark.parametrize("copy", IDS)
def test_every_copy_carries_the_delta_rule(copy):
    text = COPIES[copy]()
    assert "delta" in text.lower(), "%s is missing the harvest-the-delta rule" % copy


@pytest.mark.parametrize("copy", IDS)
def test_every_copy_keeps_the_verification_bar(copy):
    text = COPIES[copy]()
    assert "demo" in text.lower(), (
        "%s lost the evidence bar (cross-check / real evidence, not a demo or hype) — "
        "the harvest rule must not become a licence to pitch hype" % copy
    )


@pytest.mark.parametrize("surface", (
    ".claude/context/beats/claude-lab.md",
    "generate-episode.sh",
    "beats.json",
    "gemini_buildpitch.py",
    "build-pitches/README.md",
))
def test_build_pitch_format_surfaces_pin_delta_and_more_takeaways(surface):
    """The default and manual reporters must not leave these fields ad hoc."""
    text = _read(surface).lower()
    assert "delta vs kyle's current setup" in text, surface
    assert "more takeaways" in text, surface
