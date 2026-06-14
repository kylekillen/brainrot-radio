---
description: Step 3 — launch parallel beat reporter agents, one per beat
---

# Run the beat reporters

Pipeline step 3 of 5 (step 2 is research, folded into generate-brief). Working
directory: `/Users/kylekillen/brainrot-radio`. Requires `.tmp/topic-brief.txt`
from `/generate-brief`.

Launch parallel `general-purpose` agents (Agent/Task tool) — one per active beat
in `beats.json`. Run them concurrently (multiple Agent calls in one message).

## Each beat agent receives
1. Its beat's editorial guidelines — the matching file in
   `.claude/context/beats/` (e.g. `ai-tech.md`, `agents-building.md`,
   `sports.md`, `entertainment.md`, `economics-culture.md`,
   `prediction-markets.md`). Give the agent ONLY its own beat file plus the
   shared `.claude/context/editorial-voice.md` — do not dump every beat.
2. Its beat's stories from `.tmp/topic-brief.txt` (filtered by beat).
3. Full transcripts for its podcast/Twitch items from `.tmp/transcripts/` and
   Substack full text from `.tmp/articles/`.
4. The dedup context: ALL `scripts/.covered-*.json` and recent episode scripts —
   see `.claude/context/dedup.md`. Anything already covered must be skipped.

## Each beat agent returns
- 1-3 written `[BASIL]`/`[BROOKE]` segments hitting its beat's word target.
- At least one direct source quote per segment, with citations.
- The story slugs + podcast GUIDs it used (for covered-story tracking later).

The **Build-Pitch of the Day** (from `.tmp/build-pitches.md`) slots inside the
Agents & Building beat — see `.claude/context/beats/claude-lab.md` and
`agents-building.md`.

Collect all beat outputs and hand them to `/assemble-episode`. STOP after the
beat agents return — do not assemble or QC here.
