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

**VERDICT: FAIL.** Five of the seven criteria missed. B does not replace the
two-pass format as tested.

| criterion | | evidence |
|---|---|---|
| 1. B has 0 seam/leak defects | **FAIL** | 2 hits — L27 `internal_name` (*"in the sweeper"*, i.e. `pr-review-sweeper.py`) and L31 `private_system` (*"logged in the build-pitches folder for Kyle to greenlight"*) |
| 2. B gets no QC FAIL | **FAIL** | production QC returned `QC VERDICT: FAIL` |
| 3. B includes a Build Pitch of the Day | PASS | 397-word dedicated block, sourced to Opus 5.5 / Anthropic docs / Artificial Analysis / Berman |
| 4. B is 3,000–4,000 spoken words | **FAIL** | **1,648** spoken words — asked for 3,000+, wrote 45% of the floor |
| 5. B's writer tokens ≤ 60% of A's | PASS | B **27,534 measured** vs A **~381,757 estimated** = **7%** |
| 6. Judge: B ≥ A on sourcing | **FAIL** | B **2** vs A **5** |
| 7. Judge: B ≥ A on substance | **FAIL** | B **2** vs A **5** |

Judge, all four axes: **A 5 / 5 / 5 / 4, B 2 / 2 / 2 / 2** (sourcing, substance,
pitch, flow). Full reason in `2026-09-28-single-pass-metrics.json` → `judge.reason`.

### The numbers

| | A (control) | B (variant) |
|---|---|---|
| spoken words | **9,596** | **1,648** |
| writer | Claude Sonnet, 2 agentic passes, 1M ctx | Glimmer 30B local, 1 pass, 32,768 ctx |
| writer tokens | ~381,757 (**estimate**) | **27,534 measured** (20,689 in + 6,845 out) |
| source bundle read | 60,137 tok (all 16 transcripts, 6 articles) | 20,689 tok (3 transcripts, 2 articles, brief whole) |
| wall clock | 8 min (04:07→04:15) | 11 min |
| QC | PASS (on a **second** pass — see below) | **FAIL** |
| seam/leak defects | 0 | 2 |
| speaker collisions | 0 | 1 |

A's token figure is an **estimate**, as the criteria allowed: the pipeline logs
no writer tokens, so it is the corpus A's two passes read (1,313,076 chars over
34 files, ×2 passes) at B's measured 3.85 chars/input-token, plus A's 9,804
output words at B's measured 4.15 tokens/word. It is labelled `ESTIMATE`
everywhere. The *direction* is not in doubt — B used 7% of A's writer tokens —
but the exact ratio rests on that estimate.

### What actually failed, separated from what only looks like it did

Most of B's QC FAIL is a **replay artifact**, not a format defect: 09-28 had
already aired, so an episode written from 09-28's brief necessarily re-covers
09-28's stories, and the dedup ledger flags 15 of them — the whole AI/Tech
block, the entire build pitch, Sports, Entertainment. That is the experiment's
construction, not the writer's fault, and the same artifact inflates A's QC
verdict in the other direction. Stripping it out, the real defects are:

- **Two private-system leaks.** L31 names the build-pitches folder and Kyle's
  greenlight step; L27 says *"in the sweeper"*, naming `pr-review-sweeper.py`.
  The first is **instructed by the production pass-1 prompt itself**, which
  tells the writer to say the pitch "is logged in the build-pitches folder so
  Kyle can point an agent at it and greenlight the build" — and then QC deletes
  that exact sentence as a MUST-FIX. **That is a standing contradiction in the
  daily pipeline, not a single-pass defect**, and it burns a writer edit every
  episode. It should be fixed in the prompt.
- **A speaker collision** at L59/L61 (consecutive `[BASIL]`, a doubled
  sign-off) — the exact defect class the two-pass join is blamed for, produced
  here without any pass join at all.
- **One sourcing overreach**: a named analysis attributed to a named reporter
  (Cheng Ting-Fang / Nikkei) that the truncated blurb does not contain.
- **Length discipline**: told 3,000–4,000, delivered 1,648.

The judge, blind, independently reached the same three conclusions: *"Y is
largely headline paraphrase, internally contradicts itself … adds unsourced
specifics such as a $4/$20 price, repeats the same football description twice
back-to-back … ends with a doubled [BASIL] sign-off, and its build pitch
describes Kyle's own sweeper and build-pitches folder instead of the
technique."* Two independent graders, one scripted, agreed on the substance.

### Two findings that outlive this test

**1. A's 09-28 QC evidence was thinner than it looked.** Re-running the
production QC on the already-aired 09-28 script — a *second* pass, with fresh
eyes — returned PASS but found **8 MUST-FIX items** and fixed them in the copy:
a misattributed quote ("stupid bad pharma trick" is Klickstein's, not Attia's),
a wrong-date claim ("Last week it named Accenture" when the script itself says
it was flagged on the 19th), broken Moonshots attributions (lines credited to
Peter that the transcript does not tie to him), a stale sandbox-escape recap, a
false claim that two Ringer shows overlap, and a build-pitch line echoing Kyle's
private review lane. This is the direct evidence behind the Round 3 note about
missing final-script QC evidence: the pipeline's single QC pass is not a
sufficient gate, on the two-pass format as much as on any other.

**2. The control is 9,596 words, and the format's variance is the story.**
09-25 6,206 · 09-26 8,877 · 09-27 6,192 · 09-28 9,596. There is no stable
"~6,000-word episode"; there is a two-pass format that lands anywhere from 6k
to 9.6k depending on how much the second pass's sources support. The premise
this test was asked to re-test was itself shaky, and that is worth knowing
independently of the verdict.

### What this does NOT show

The confound stated up front, in numbers: B's writer saw **20,689 tokens**; A's
saw **60,137**. B's lane is a 32,768-token local 30B model; A's is a 1M-context
Sonnet. So this result is *"a one-pass 32K-context free local model loses to
the two-pass Sonnet format"*, and it cannot tell you whether one pass would
lose to **two** passes at equal input budget and equal model. Re-running B on a
long-context writer is the obvious next measurement, and the harness takes it
as `--date` + `KT_TEST_WRITER` with no code change.

The judge also deserves a caveat: the free judge lanes are thin. Two died
mid-test (`muse-spark-1.3-free` is registered in `external_models.py` but the
OpenCode provider has retired it; `orcarouter-hy3-free` is capacity-limited),
so the judge that scored this run is `space-bunny-free`. It is a different
model from the writer, as required — but it is the same model the harness
operator was running, and a 5/2 spread on a quality rubric deserves a second
opinion from a stronger judge before it changes anything.

### Verdict against the frozen criteria

**FAIL.** Keep the two-pass format. Three of the failures are fixable outside
the format question — the prompt/QC contradiction on the build-pitch line, the
sourcing overreach, the speaker collision — and they are worth fixing in the
daily pipeline regardless of what happens to single-pass writing.

