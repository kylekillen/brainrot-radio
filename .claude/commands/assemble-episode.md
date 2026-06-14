---
description: Step 4 — editor assembles beat segments into one coherent episode
argument-hint: "[YYYY-MM-DD]"
---

# Assemble the episode

Pipeline step 4 of 5. Working directory: `/Users/kylekillen/brainrot-radio`. You
are the EDITOR (main session). Take the beat reporters' segments and build one
coherent episode. Date: `$1` (default today).

Read `.claude/context/editorial-voice.md` for voice, length target, and
connection discipline.

## Do this
1. **Order segments** for best flow — strongest story first, varied pacing. Front
   half is AI/Tech + Agents & Building (featured); back half is Sports →
   Entertainment → Economics/Culture → optional prediction-markets quick-hit.
2. **Write the intro** — cold open with the biggest story, then the show name +
   date. Get the day of week RIGHT:
   `python3 -c "from datetime import date; print(date.today().strftime('%A'))"`.
   Match the greeting to the TIME OF DAY (morning/afternoon/evening).
3. **Write the outro** — brief recap of the most interesting thread, short
   sign-off. Don't force a single thesis.
4. **Add `[TRANSITION]` markers** between beat changes (never `---`).
5. **Validate dates and freshness** — nothing >48h old presented as "breaking."
6. Write the full script to `scripts/killen-time-$1.txt` (add `-02` suffix for a
   second daily episode). Use `[BASIL]`/`[BROOKE]`/`[TRANSITION]` tags; alternate
   speakers (never two consecutive same-speaker blocks).
7. **Save covered stories immediately** (before QC/render) and archive used
   sources — see `.claude/context/dedup.md`.

Then run `/qc-episode scripts/killen-time-$1.txt`. Do NOT render until QC passes.
