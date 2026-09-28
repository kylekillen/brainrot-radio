# New Hire re-test: one Sonnet pass vs the aired two-pass Sonnet episode

**Result: FAIL, both variants.** B-long misses 3 of 7 criteria, B-short misses 4
of 7. No lane errored, so neither is INCONCLUSIVE. **Keep the two-pass format.**

<!--ran on: space-bunny-free-->

The first test (PR #42) was not a fair fight — a 32K-context local model against
Sonnet with full context. This one holds the writer model fixed at Sonnet and
varies only the pass count. It answers the question Kyle actually asked, and the
two-pass format turns out to be doing real work.

| | A (control, as aired) | B-long | B-short |
|---|---|---|---|
| writer | claude sonnet | claude sonnet | claude sonnet |
| passes | 2 agentic | **1** | **1** |
| context | 1M | 1M | 1M |
| spoken words | 9,596 | 13,430 | 3,116 |
| writer tokens | **10,907,026** | 2,743,998 (25%) | 1,206,200 (11%) |
| cost | not logged by the pipeline | $1.79 | $0.83 |
| wall clock | ~9 min (both passes) | 348s | 120s |
| QC (report-only) | FAIL, 2 real | **FAIL, 8 real findings / 36 defects** | **FAIL, 8 real findings** |
| seam/leak defects | 0 | 3 | 3 |

**A's token figure is measured, not estimated.** The pipeline logs no writer
tokens, but every `claude -p` run writes a session transcript carrying
per-message `usage`. The 09-28 writer sessions sum to 10,907,026 (pass 1 =
6,669,818; pass 2 = 4,237,208), build-pitch reporter and QC excluded.

## The criteria, one at a time

Pre-registered and committed **before either variant existed**
(`2026-09-28-sonnet-onepass-criteria.md`, commit `7e27c3f`).

| criterion | B-long | B-short |
|---|---|---|
| 1. 0 seam/leak defects not also in A | **FAIL** — 3 vs A's 0 | **FAIL** — 3 vs A's 0 |
| 2. no QC FAIL beyond dedup-replay | **FAIL** — 8 real findings | **FAIL** — 8 real findings |
| 3. Build Pitch of the Day present | PASS — 1,627-word block | PASS — 303-word block |
| 4. within its length band | PASS — 13,430 (band 11,900–20,700) | PASS — 3,116 (band 3,000–4,000) |
| 5. writer tokens ≤ 60% of A's | PASS — 25% | PASS — 11% |
| 6. BOTH judges: B ≥ A on SOURCING | **FAIL** — 4/5 and 3/4 | **FAIL** — 3/5 and 3/4 |
| 7. BOTH judges: B ≥ A on SUBSTANCE | PASS — 5/4 and 5/4 | **FAIL** — 4/5 and 4/5 |

## Two blind judges, both reported

Each got its own shuffled X/Y order, seeded and recorded, so neither can infer
the control from position. Scores are SOURCING/SUBSTANCE/PITCH/FLOW.

| band | judge | blind order | A | B |
|---|---|---|---|---|
| long | space-bunny-free | X=B | 5/4/5/5 | 4/5/3/5 |
| long | opus | X=A | 4/4/4/4 | 3/5/2/4 |
| short | space-bunny-free | X=B | 5/5/5/4 | 3/4/4/5 |
| short | opus | X=A | 4/5/5/4 | 3/4/3/4 |

**They disagree on 6 cells in the long band and 3 in the short** — Opus is
consistently a point harsher on A's sourcing and on B's pitch. But on the
direction that decides the criteria they agree completely: **both judges rank B
below A on sourcing in both bands**, and both rank B above A on substance in the
long band. B-short loses substance too, to both judges.

Opus on B-long: it "relies on several callbacks to earlier episodes … that can't
be checked against today's material, and its build pitch is" unsupported.
space-bunny-free on B-short: it "repeatedly promotes paraphrase into quotation
marks" and "misattributes the fifteen-percent stock drop."

## The replay artifact, separated

09-28 already aired, so anything written from 09-28's brief re-covers 09-28 and
the dedup ledger flags it. Those items are ignored for A and B alike and reported
separately, as the criteria require. B-long: 1 of 9 QC findings was a dedup
artifact. B-short: 2 of 10. **The rest are real**, and they are what fail both
variants.

For calibration: A as aired also FAILs a fresh report-only QC, with 2 real
findings — both attribution errors (a Klickstein quote attributed to Attia; a
Moonshots line pinned to a speaker the transcript does not label). The two-pass
pipeline does not ship a clean script either. It ships a noticeably less broken
one, and this test cannot score A as perfect.

## What actually explains the gap

**1. Asking one pass for 14,000–18,000 words makes it go and get material — or
invent it.** B-long hit its length band, and QC, asked to fix it, cut it from
13,615 to 8,476 spoken words. About **5,100 words, 37% of the episode, were
ungrounded or re-aired.** QC's own words: "B-long hit the 14–18k target only by
invention."

But the more precise story is worse, and it is a confound in this test's own
framing. **B-long made 8 `WebFetch` calls. B-short made none. A's pass 1 made
none.** Given a 16k-word target and a bundle that could not source it, the
one-pass writer went to the live web — fetching Willison, the MIT Tech Review
piece and the Opus 5.5 prompting docs — and then built the missing length on
whatever came back. The evidence rules in the prompt say only provided text
counts as a source, so every one of those segments is unsourced by the show's
own standard, and QC correctly cut them. Within the fetched material the writer
still invented specifics: a false "I read the whole thing", a Jensen line
misattributed to Alex Wissner-Gross, a keynote body that exists in no source.

So the length band is **not** a neutral variable. Changing the pass count and
the length target together also changed the writer's tool behaviour, and
B-long's sourcing failure is partly *policy* — it reached for material the show
is not allowed to use — rather than pure confabulation. B-short is the cleaner
isolation of pass count: no web access, no extra tool, and it still fails.

The two-pass format does not exist because a single pass is lazier. It exists
because **one pass given a length it cannot source will go and get it, or make
it up** — and "do not fill a length target with invention" is exactly the rule a
single 16k-word pass cannot honour. Note also that A itself is 9,596 words, well
under the 14–18k spec, because the sources are thin: **the spec is not what the
show actually produces.**

**2. The prompt and QC contradict each other, and now it is reproduced on
demand.** Pass 1's prompt *orders* the writer to say the pitch "is logged in the
build-pitches folder so Kyle can point an agent at it and greenlight the build."
QC then cuts that exact sentence as a MUST-FIX private-system leak. Both B
variants produced it (all 3 seam defects, one line each) because the one-pass
prompt reuses pass 1's wording verbatim to keep the fight fair. A is free of it
**only because production QC cut it.** Not a pass-count effect — a standing
contradiction in the daily prompts. Worth fixing whatever happens to the format
question.

**3. The token saving is real and buys less than it costs.** One pass is 25%
(13,430 words) or 11% (3,116 words) of the control's tokens, at $1.79 or $0.83.
That is a genuine saving. It buys an episode that fails QC for fabrication and
loses on sourcing to both judges. One pass at 3,116 words is not a cheaper show,
it is a smaller one at the same defect rate.

## Harness defects found by running it

All fixed here, all pinned by tests (96 pass):

- **QC was measuring its own surgery.** Asked to edit, QC cut B-long 13,615 →
  8,476 and reported PASS on the result — a verdict describing QC's rewrite, not
  the writer's episode. QC is now REPORT ONLY. This one nearly produced a false
  PASS for the whole test.
- **The dedup/real split reported zero real defects for a control QC had found
  two of.** A parse that captured fewer findings than QC stated now marks itself
  incomplete and the criterion fails, rather than scoring a lower bound as a
  pass. A false clean bill is worse than no number.
- **Concurrent stages clobbered each other.** qc and judge each read the metrics
  file once and wrote their own copy back; whichever finished last deleted the
  other's results, and a report with no judge scores reads as a judge-lane error
  that did not happen.
- `KT_TEST_QC_ONLY` wiped the other variant's QC entry; dropping the verdict
  *line* discarded the findings a Stop hook appends below it; the classifier
  could not read QC's numbered-finding format and missed "repeats 09-24" as a
  dedup cue.

## Limits

One day, one bundle, one writer model, n=1 per band. The judges are a rubric, not
airtime. The length spec in `editorial-voice.md` (14,000–18,000 words) is not
what the pipeline actually produces — A came in at 9,596 — so "within 15% of the
spec" is a target the control itself misses. And B-long's sourcing failure is
partly a thin-bundle problem: 09-28's own second-half writer logged that the
sources were too thin, which is why that half shipped short.

**B-long is confounded, and the confound is the finding, not a footnote.** The
brief asked B-long to "isolate pass count" at the production length spec, but
that target also drove 8 off-bundle web fetches that A's pass 1 never made. A
clean pass-count isolation would hold the length target fixed at what the
pipeline really produces (~9,600) rather than at the spec. B-short is the closer
isolation and it fails too, so the conclusion does not rest on B-long.

**One-line recommendation: keep the two-pass format.** The savings are real and
the defect rate is not lower; the second pass is what keeps an episode inside
what its sources can support.

## Artifacts

- `2026-09-28-sonnet-long.txt` / `2026-09-28-sonnet-short.txt` — the two scripts
- `2026-09-28-single-pass-metrics-{long,short}.json` — every number above
- `2026-09-28-sonnet-bundle/` + `…-bundle-manifest.json` — the frozen source
  bundle, sha256'd, reconstructed from pass 1's own tool calls; 09-28's script
  deliberately absent so the writer cannot read the control
- `2026-09-28-qc-{A,B}-{long,short}.log` + the `-findings` files — report-only QC
- `2026-09-28-judge-raw-{opus,space-bunny-free}-{long,short}.json` — both judges

Not done, by design: no TTS, no audio, nothing to the feed, nothing to `/read`.
Kokoro :8765, `render_report.py`, `publish_private.py`, the daily pipeline and
the production prompts are untouched. Ran 20:41Z–22:1xZ, clear of the
10:00Z–13:00Z production window.
