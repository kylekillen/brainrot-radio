---
description: Step 1 — ingest the ranked topic brief and research the top stories
---

# Generate the topic brief

Pipeline step 1 of 5. Working directory: `/Users/kylekillen/brainrot-radio`.

## Do this
1. Activate the venv and run ingest to produce the ranked brief:
   ```bash
   source venv/bin/activate
   python3 ingest.py --report -n 40 -o .tmp/topic-brief.txt
   ```
   (Scoring details: see `.claude/context/scoring.md`.)
2. **Research the top stories.** Don't write from RSS summaries alone — pull the
   actual source. WebFetch the full articles for the highest-ranked headlines.
   For podcast/Twitch items, the full transcripts are cached in
   `.tmp/transcripts/`; for Substack items marked `Type: substack (full text)`,
   read the full text from `.tmp/articles/`.
3. Confirm `.tmp/topic-brief.txt` exists and report the top stories grouped by
   beat, plus which transcripts and articles are available, so the next step
   (run-beat-reporters) knows what each beat has to work with.

Skipping research is the most common quality regression — do not skip it.

STOP after the brief is built and researched. Do not write segments here.
