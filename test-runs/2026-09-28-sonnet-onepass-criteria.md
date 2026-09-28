# Pre-registered PASS/FAIL — Sonnet one-pass vs the aired two-pass Sonnet episode

Written and committed **2026-09-28 20:5xZ, BEFORE either variant was written.**
Task: KT Podcast New Hire re-test, fair fight. Neither B script existed when this
file was committed. Nothing below may be changed after the first B lands; a
criterion that moves after seeing the result is not a criterion.

<!--ran on: space-bunny-free-->

## The question

Does **one Sonnet pass** beat **two Sonnet passes** on the same day's sources?

The first test (PR #42, task 2f515490) was not a fair fight: B was a 32K-context
local model and A was Sonnet with full context. It answered "a free 32K local model
loses to the two-pass format", not "one pass loses to two". This run holds the
writer model fixed at Sonnet and varies only the **pass count** (and, as a second
axis, the target length).

## Design

| | writer | passes | context |
|---|---|---|---|
| **A (control)** | claude sonnet, as aired | 2 agentic passes | 1M |
| **B-long** | claude sonnet, one pass | 1 | 1M |
| **B-short** | claude sonnet, one pass | 1 | 1M |

`A` = `scripts/killen-time-2026-09-28.txt` (9,596 spoken words), as aired, never
regenerated. `B` is invoked exactly as `generate-episode.sh`'s `run_claude_step`
invokes pass 1 — `claude --dangerously-skip-permissions --model sonnet -p`, same
working directory, same tools, same uncompacted bundle — with the pass-1 prompt
changed **only** so it writes the whole episode in one pass. No pass 2, no
expansion step, no length top-up.

### The two B variants

- **B-long** targets the production length spec in `.claude/context/editorial-voice.md`
  (~14,000-18,000 words). This **isolates pass count**: same length target the
  format is specified at, one pass instead of two.
- **B-short** targets 3,000-4,000 spoken words. This tests the original length
  hypothesis: that the two-pass format exists to hit a length one pass cannot.

Each is scored **separately** against A. Neither rescues the other.

### Source bundle — frozen, not live

Both A and B read `test-runs/2026-09-28-sonnet-bundle/`, reconstructed from what
pass 1's own tool calls show it read at 04:07 on 09-28 (session
`dd611efd-abe4-4470-a8a9-827400c61c65`): the 12 transcript/article files, each
recovered from `.tmp/used/` at byte-identical size, plus `topic-brief.txt` (04:01),
`build-pitches.md` (04:06), `.claude/context/`, `CLAUDE.md`, `GUARDRAILS.md`, the
four prior scripts and the 09-20…09-27 covered ledgers. The live `.tmp/` has
drifted (the ingest daemon has since added and moved files) — a live read would
hand B a different bundle than A had, which is the exact unfairness this rerun
exists to remove. `opus55.txt` is included because pass 1 read it.

### A's token usage — MEASURED, not estimated

The pipeline does not log writer tokens, but `~/.claude/projects/-Users-kylekillen-brainrot-radio/`
holds the real session transcripts, each with per-message `usage`. Summing the
09-28 writer sessions gives A's actual input/output tokens. These are **measured**,
and labelled as such everywhere. (PR #42 carried an estimate; this run does not need one.)

### The replay artifact

09-28 already aired, so anything written from 09-28's brief re-covers 09-28 and the
dedup ledger flags the beats. **Every dedup-only QC item is ignored for A and B
alike** and reported separately from real defects. It is an artifact of replaying
a past date, not a property of either format.

## The criteria

**PASS** requires ALL of:

1. **0 seam/leak defects not also present in A.** Measured by `bin/test-single-pass.py`'s
   scanner. A's own defect count is the baseline; B is only penalised for defects
   A does not have.
2. **No QC FAIL beyond dedup-replay items.** Real (non-dedup) MUST-FIX count must be 0.
3. **A Build Pitch of the Day is present** — a substantive block carrying the mechanism
   and a named source.
4. **Within its length band.** B-long: within 15% of the spec (14,000-18,000).
   B-short: 3,000-4,000 spoken words.
5. **Writer tokens ≤ 60% of A's.** Both measured from the CLI's own JSON usage.
6. **BOTH judges score B ≥ A on SOURCING**, and
7. **BOTH judges score B ≥ A on SUBSTANCE.**

**FAIL** if any of those miss. **INCONCLUSIVE** if a lane errors — the lane and the
error are named. A different writer model is never substituted for the one asked for.

### Judges

Two blind judges, order shuffled: **space-bunny-free** and **Anthropic Opus** (via
the claude CLI). Both score SOURCING / SUBSTANCE / PITCH / FLOW 1-5. Both are
reported, including any disagreement between them. The writer is Sonnet; neither
judge is the writer. Blinding is by X/Y label with the order seeded and recorded.

## Hard limits

No TTS. No audio. Nothing to the feed. Nothing to `/read`. Kokoro :8765,
`render_report.py`, `publish_private.py`, the daily pipeline and the production
prompts are untouched. Runs happen between 14:00Z and 10:00Z so the 10:00Z-13:00Z
production window is never contended.
