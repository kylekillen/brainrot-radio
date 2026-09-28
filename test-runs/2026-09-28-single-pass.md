# New Hire test — single-pass ~3,500 words vs the two-pass control

**Written 2026-09-28 18:30Z, BEFORE variant B was written.** The criteria below
are frozen. Nothing in this section moves after the run; results are appended
under "Results" further down.

Source: All Hands Round 3, `kt-podcast` section —
*"the ~6,000-word, two-pass episode. An older model set that length…"*
Doctrine applied: an inherited conclusion is information, not a verdict.

## The question

Is one writer pass of 3,000–4,000 spoken words a better episode than today's
two writer passes, on the same day's sources?

## Setup

| | A (control) | B (variant) |
|---|---|---|
| script | `scripts/killen-time-2026-09-28.txt`, as aired (`ep-2026-09-28-01`) | `test-runs/2026-09-28-single-pass.txt` |
| passes | 2 (pass 1 = 6,341 words; pass 2 appended → 9,804) | 1 |
| writer | Claude Sonnet, agentic (production, `PODCAST_ENGINE=claude`) | **non-Anthropic** free lane (harness default `ollama:muse-glimmer:30b-mlx`) |
| target | as produced | 3,000–4,000 **spoken** words |
| sources | `.tmp/topic-brief.txt` (45,877 B, 09-28 04:01), `.tmp/build-pitches.md`, `.tmp/transcripts/`, `.tmp/articles/`, `scripts/.covered-*.json`, last 3 scripts | the same bundle, fingerprinted in `test-runs/2026-09-28-single-pass-sources.json` |
| QC | production `.claude/commands/qc-episode.md`, 3 skeptics + synthesis | same, same day, same command |
| seam scan | `bin/test-single-pass.py --stage scan` | same |

**Judge:** one free model that is not the writer, labels shuffled by a seed
derived from the date (`sha256(date)`, so the blinding is reproducible), scoring
**sourcing, substance, build-pitch quality, flow** 1–5.

## Frozen criteria

**PASS** (recommend single-pass as the new default) only if **all** hold:

1. B has **0** seam/leak defects;
2. B gets **no QC FAIL**;
3. B includes a **Build Pitch of the Day**;
4. B is **3,000–4,000 spoken words**;
5. B's writer tokens are **≤ 60%** of A's (A's tokens are not logged by
   `generate-episode.sh`, so A is **estimated** from the corpus its two passes
   read at B's measured token rates — and labelled an estimate everywhere);
6. the blind judge scores **B ≥ A on sourcing**;
7. the blind judge scores **B ≥ A on substance**.

**FAIL** if B has any seam, any QC FAIL, or the judge ranks A above B on sourcing
or substance.

**INCONCLUSIVE** if the writer lane or the judge lane errors. Report which lane
and what error. Do not retry on Claude.

## Limits

Script only. No TTS, no audio, nothing published, nothing to the public feed or
`/read`. Kokoro :8765, `render_report.py` and `publish_private.py` untouched.
The daily pipeline and its prompts are not changed — switching formats is
kt-podcast's call after this result, not this test's.

## Known confound, stated up front

The task forbids an Anthropic writer for B, so B differs from A in **two** ways
at once: one pass instead of two, **and** a different model. This test can
answer "is B better than A" but it **cannot** attribute the difference to the
pass structure alone. Read the result as a verdict on the *proposed* single-pass
configuration (one free-model pass, ~3,500 words), not as a clean measurement of
pass-count.

## Second thing this run already found

The control is not ~6,192 words. `scripts/killen-time-2026-09-28.txt` is
**9,596 spoken words** (9,693 raw), and `ep-2026-09-28-01` ran **54:00**. The
6,192 figure — quoted in the task brief, in `HANDOFF.md` and in a prior
verification note — is **09-27's** count (`ep-2026-09-27-01`, 37:20). 09-28 is
the longest episode in weeks (09-26: 8,877 / 49:09; 09-25: 6,206 / 36:22), so
the "≈6,000 is the format" premise is weaker than it looked, and the two-pass
format's variance is itself part of what the expansion pass buys.

---

## Results

*(appended by `bin/test-single-pass.py --stage report`)*
