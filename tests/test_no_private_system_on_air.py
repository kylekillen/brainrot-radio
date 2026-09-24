#!/usr/bin/env python3
"""Regression tests for the 2026-09-24 leak: private system details on public air.

On 2026-09-24 the Build-Pitch segment read a local "check" out of
build-pitches/2026-09-24.md and put the listener's private setup on air
("observer-system had twenty-seven places that launch Claude … only eight pass
an effort level"; measured at that day's commit: 48 and 9). The number was wrong
and the setup should not have been on air at all. GUARDRAILS.md already banned
internal fleet state since 2026-06-28; these tests assert the ban is present in
the two places that actually decide what gets spoken: the writer prompt and the
QC skeptic briefs.
"""
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(ROOT, rel)) as f:
        return f.read()


def test_writer_prompt_forbids_private_system_details_in_build_pitch():
    sh = _read("generate-episode.sh")
    assert "GENERAL terms" in sh, "pass-1 build-pitch prompt must keep the on-air explanation general"
    assert "observer-system, brainrot-radio" in sh, "prompt must name the private repos it forbids quoting"
    assert "launch-site counts" in sh
    assert "Keep the listener's private system out of the audio" in sh


def test_qc_coherence_skeptic_treats_private_system_as_must_fix():
    qc = _read(".claude/commands/qc-episode.md")
    agent_b = qc.split("**Agent B — Coherence Skeptic.**", 1)[1].split("**Agent C", 1)[0]
    assert "MUST-FIX" in agent_b
    assert "observer-system" in agent_b
    assert "launch sites" in agent_b
    assert "GUARDRAILS.md" in agent_b


def test_guardrails_has_the_private_setup_row():
    g = _read("GUARDRAILS.md")
    assert "private system" in g.lower() or "PRIVATE system" in g
    assert "2026-09-24" in g
