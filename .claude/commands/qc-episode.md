---
description: Step 5 (MANDATORY) — adversarial 3-skeptic + synthesizer QC of the episode script
argument-hint: "[path/to/script.txt]"
---

# QC the episode — adversarial verification

Pipeline step 5 of 5, **MANDATORY**. Working directory:
`/Users/kylekillen/brainrot-radio`. Do NOT render until this passes.

**Script to QC:** `$1`
(If `$1` is empty, QC the newest file matching `scripts/killen-time-*.txt`.)

## Why three agents instead of one
A single QC agent asked to "find problems" tries to be *helpful* and misses
things — and it suffers self-preferential bias when reviewing AI-written prose.
Three independent agents each told to **attack and refute** the script from one
narrow angle catch more, and a synthesizer keeps only what holds up. An issue two
agents independently flag is real (MUST-FIX); a lone flag is ADVISORY.

## Step 1 — launch 3 skeptics IN PARALLEL
Spawn three `general-purpose` agents in a single message (concurrent). Give each
the script path and tell it explicitly: **your job is to prove this script is
broken from your angle — be adversarial, assume it's wrong until you confirm
otherwise, and report every defect with the exact line/segment.** Each returns a
findings list (each item: severity, location, the defect, a concrete fix).

**Agent A — Freshness & Dedup Skeptic.** Attack ONLY for repetition and
staleness. Read the script, ALL `scripts/.covered-*.json`, and the last 48h of
`scripts/killen-time-*.txt`. Refute the claim "every story here is fresh and
unduplicated": find stories/quotes/podcast episodes covered in a previous episode,
facts already stated on-air (check the `segments` dict), and anything presented as
"breaking" that is >48h old (check age labels). See
`.claude/context/dedup.md`.

**Agent B — Coherence Skeptic.** Attack ONLY structure and flow. Refute "this
reads as one coherent episode." Find: orphaned/duplicated content from earlier
drafts, segments out of logical order, segments referencing stories not yet
introduced, repeated sign-offs or intro phrases (e.g. triple "good morning"),
wrong day of week (verify:
`python3 -c "from datetime import date; print(date.today().strftime('%A'))"`),
topic coverage promised in the intro but missing, two consecutive same-speaker
blocks, BASIL/BASIL or BROOKE/BROOKE collisions across `[TRANSITION]` joins
(common in two-pass scripts), back-to-back `[TRANSITION]` tags, `---` dividers
(would be spoken), and any speaker tag that isn't `[BASIL]`/`[BROOKE]`/
`[TRANSITION]`.

**Agent C — Sourcing Skeptic.** Attack ONLY grounding. Refute "every claim is
sourced." Find: segments with no direct source quote, editorial claims with no
grounding in the material ("here's what I imagine" / speculation presented as
fact), quotes that can't be traced to a transcript/article, and forced
connections asserted between unrelated stories. See
`.claude/context/editorial-voice.md`.

## Step 2 — synthesize (you, the main agent)
Read all three reports. Produce a single verdict:
- **MUST-FIX** — every issue flagged by **≥2 agents**, PLUS any single-agent issue
  that is unambiguously fatal (wrong day of week, a duplicated story, a spoken
  `---`, a non-existent speaker tag). These block rendering.
- **ADVISORY** — single-agent findings that are judgment calls. Note them; don't
  necessarily fix.
- **VERDICT: PASS** (no MUST-FIX remaining) or **FAIL** (MUST-FIX present).

## Step 3 — fix and re-verify
If FAIL: fix every MUST-FIX item directly in the script file, then re-check the
fixed spots (a targeted re-read, not a full re-run) and confirm VERDICT: PASS.
For consecutive same-speaker fixes, **merge the two paragraphs into one block** —
do not flip a speaker tag, which cascades through the rest of the alternation.

Print the final MUST-FIX / ADVISORY summary and the verdict. End on a line that
literally contains `QC VERDICT: PASS` or `QC VERDICT: FAIL` so callers can grep
it.
