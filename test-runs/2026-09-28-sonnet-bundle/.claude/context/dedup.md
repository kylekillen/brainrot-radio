# Multi-Episode Dedup

**This is the most critical quality issue.** Repeated content across episodes
destroys listener trust.

## Rules (MANDATORY)
1. **Read ALL scripts from the last 48 hours** before writing. Not just the most
   recent — ALL of them.
2. **If a podcast episode was used in ANY previous script, SKIP IT.** Do not
   extract different quotes from the same episode. It has been consumed.
3. **If a topic was covered in ANY previous script, SKIP IT.** A different author
   writing about the same event is NOT a new development. A new take on the same
   facts is NOT new. New developments mean: a price moved, a deal closed, someone
   resigned, new data was released. Read the "segments" dict in the covered JSON —
   if the underlying facts were already stated on-air, skip the topic entirely.
4. **The covered ledger is written AFTER the episode airs, from the FINAL script.**
   (Changed 2026-09-25. It used to be saved from the writer's draft, before QC; QC
   then cut/rewrote the script and the ledger kept listing stories that never aired,
   which tomorrow's ingest hard-excludes.) `generate-episode.sh` exports
   `COVERED_DEFER=1`, so a writer's `save_covered_stories(...)` only parks a draft
   claim in `.tmp/covered-pending-DATE.json`; after publish, `covered_guard.py commit`
   REPLACES `scripts/.covered-DATE.json` with segments derived from the script's own
   text and only the podcast guids the script demonstrably drew from. Nothing to do
   by hand — unless an episode is published manually, then run
   `python3 covered_guard.py commit scripts/killen-time-DATE.txt --date DATE`.
   Independently, `dedup_guard.py` compares drafts against the last 7 days of
   BROADCAST scripts (no ledger needed) before the back half is written and before QC.
5. **Archive used source files** after writing. Move used transcripts and articles
   to `.tmp/used/` so the next episode's writer doesn't even see them.
6. **Content summaries are mandatory.** When saving covered stories, include the
   specific talking points, quotes, and arguments used — not just a slug.

## How to save (legacy/manual — the pipeline now defers this, see rule 4)
Inline Python via bash single-quotes breaks on apostrophes in string values —
write to a `.py` file and execute it instead.

```python
from ingest import save_covered_stories, archive_used_sources

save_covered_stories(
    ["story-slug-1", "story-slug-2"],
    {
        "story-slug-1": "Covered Cursor hitting $2B ARR, Thieblot quote, 60% corporate stat",
        "story-slug-2": "Covered Dort-Jokic incident via Raja Bell physical/reckless/dirty framing",
    },
    podcast_guids=["guid-1", "guid-2"],
)

archive_used_sources(
    used_transcript_guids=["guid-1", "guid-2"],
    used_article_paths=[".tmp/articles/slow_boring_solar-lead.txt"],
)
```

## Known multi-pass / two-pass QC patterns
- Two-pass scripts reliably produce a consecutive same-speaker collision at the
  half-boundary (BASIL closes the first half AND opens the second). Fix by merging
  the two consecutive same-speaker paragraphs into one block — do NOT flip the
  speaker tag, which cascades through every subsequent turn. Or have Pass 2 open
  its first section with BROOKE by convention.
- Watch for back-to-back `[TRANSITION]` tags at the half-join (would double the
  audio sting) — collapse to one.
- `voice.py parse_script` appends any non-speaker-tag line (including `---`
  dividers) into the current segment, so it would be spoken aloud. Use
  `[TRANSITION]`, not `---`, as the section separator.
