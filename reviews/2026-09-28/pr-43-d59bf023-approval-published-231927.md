### 2026-09-28 23:19 — Reviewed PR #43: approved on the merits; already merged, formal seat via trusted delivery

Reviewed on space-bunny-free. Head reviewed: `d59bf0237e6cbd103885c5ba66ade8fb0798a6b0` (captured before
reading the diff, as the first command after preflight; unchanged at the end of review).

**State note — this PR is already on main.** It was squash-merged at 2026-09-28T23:08:12Z by `kylekillen`
(the PR author) as `d0528ad153e2cbecd282e0a4ce6f020a4a65a28e`, which is the current tip of `main`. No merge
was performed or attempted by this review, and no merge gate is left to pass: the code-review seat the gate
refused on has nothing left to gate. The approval is published through the trusted runner and is a
post-merge record of the exact merged head, not a permission slip.

**Purpose.** A pre-registered re-test of the New Hire format question ("does one Sonnet pass beat the
aired two-pass Sonnet episode?"), correcting the unfair fight of PR #42 by holding the writer model fixed
and varying only pass count. The criteria were committed at `7e27c3f` — before either B script existed —
and `test-runs/2026-09-28-sonnet-onepass-criteria.md` says so on its face. The conclusion is FAIL in both
bands; keep the two-pass format.

**Correctness — PASS.** `gh pr checks` reports two completed successful `pytest` check-runs on this exact
head (`.github/workflows/ci.yml`, runs `36496255307` and `36496265953`), no pending, no skipped.
`tests/test_single_pass_harness.py` grows from 9 to 18 tests and the new ones pin the thing that would
silently invalidate the experiment: that the one-pass prompt differs from pass 1 in exactly one way. They
assert the whole-episode instruction and the self-written outro, the absence of every piece of two-pass
scaffolding (`FIRST HALF`/`SECOND HALF`/"Another pass will write"), the presence of every show beat
(sports/entertainment/economics/quick-hits/outro), the retention of pass 1's evidence, dedup,
build-pitch and no-private-system discipline, each band's own pre-registered target, the refusal to read
`scripts/killen-time-`, the per-lane blind-order seed (both judges must not land on the same order) and
the score parser against a prose-wrapped reply. 18/18 pass locally on this head; the 3 collection errors
in a full local run are `feedgen` missing under this machine's Python 3.9 and are unrelated to the change
(hosted CI runs 3.12 with deps installed, and is green).

The harness's own numbers agree with its report. `test-runs/2026-09-28-single-pass-metrics-long.json`
carries `verdict: FAIL` with per-criterion evidence that reproduces `test-runs/2026-09-28-sonnet-onepass.md`
exactly: `B 2,743,998 vs A 10,907,026 = 25%`, `13430 spoken words` in band 11,900–20,700, `B 3 vs A 0` B-only
seam defects, `36 real (non-dedup) MUST-FIX`, and both judges below A on SOURCING. The short-band file is
the same shape at 11%. The report's "8 real findings / 36 defects" is the code's deliberate dual count
(`findings_real` vs `real_defects`), not a discrepancy.

The load-bearing correctness claim — that A's tokens are now MEASURED, not estimated — holds:
`measure_writer_A_real()` selects sessions by their own opening prompt (`FIRST HALF`/`SECOND HALF`), so the
build-pitch reporter and QC sessions are excluded, sums the same four usage fields the Sonnet lane reports,
and returns `None` rather than falling back, which drives `INCONCLUSIVE` instead of a pass.

**Coherence — PASS with two non-blocking nits.** The new Sonnet lane, the frozen-bundle branch in the
manifest stage, report-only QC on a copy, the cached-A reuse guarded by its `.reportonly` sidecar (so an
edit-enabled log can never be mistaken for a report-only measurement), `KT_TEST_QC_ONLY`'s merge-never-wipe
of `metrics["qc"]`, the two-judge loop with per-lane seeds and an explicit disagreement report, and the
merge-on-flush metrics writer all fit the file's existing shape and each say why in the code. The stop-hook
`status.d/` snapshot-and-fold-in is what keeps a report-only QC's MUST-FIX list from being lost when the
session writes findings to a file instead of stdout. Nits, below.

**Smallness — PASS.** 69 files / +6,215 / −104, but the code change is two files: `bin/test-single-pass.py`
and `tests/test_single_pass_harness.py`. The remaining 67 are the frozen bundle, raw QC logs, judge replies
and metrics that the pre-registration commits on purpose — "The raw log is committed next to this so the
split can be checked by hand." No dependency change, no formatting churn, no refactor of production code;
`or_writer` and the daily prompts are untouched, which the docstring's hard-limits claim requires and the
diff honours.

**Findings (non-blocking; the PR is on `main`, so these are a follow-up, not a revert).**

1. `bin/test-single-pass.py:661` — `estimate_writer_A()` is now dead. This PR replaced its only call site
   with `measure_writer_A_real()` (`bin/test-single-pass.py:1082`) but kept the function: 24 lines plus the
   hardcoded `.tmp/covered-pending-2026-09-28.json` at `bin/test-single-pass.py:667`. An AST sweep of this
   head finds no reference to `estimate_writer_A` anywhere. This is half of a finding already recorded
   against PR #42 (`reviews/2026-09-28/pr-42-8820964-approval-published-230653.md`): the manifest-stage half
   was correctly fixed here — `bin/test-single-pass.py:1253` now derives the name from `--date` — but the
   dead function carrying the identical literal was left behind, so the file still ships a hardcoded date in
   a harness whose `--date` is a required argument. It is also the exact thing that makes a reader believe
   A's tokens are still an estimate. Fix: delete lines 661–684.
2. `bin/test-single-pass.py:977` — `_judge_claude()` mirrors `_summon()`'s `pf.write_text(prompt)` at line
   955, where the file is then passed as `--message-file` and is load-bearing. Here the prompt is handed to
   `claude -p` inline, so `/tmp/kt-judge-<model>.txt` is written and never read. Fix: drop the two lines.

**CI and gate receipt.** Two completed successful hosted check-runs on this head (see above), each with
`head_sha: d59bf0237e6cbd103885c5ba66ade8fb0798a6b0`. `merge_gate_check.py --head d59bf023…` exited 1 on
exactly one line: `code-review lane: no independent code review (non-red-team APPROVED review) pinned to
this head — do not merge`. The red-team lane does not apply (no `program:harness-parity` label), the CI lane
is green on this head, and no protected path is touched. The PR had zero comments and zero formal reviews
when this review began, so there is no standing HOLD or BLOCKING — and my own comment is not a HOLD.

**Decision.** The change is correct, coherent and minimal for its stated purpose, CI is green on the
reviewed head, and the two nits are dead code in a private test harness with one-line fixes that do not
touch the experiment's result. Approving on the merits. No merge was performed or attempted by this
review — the PR reached `main` at 23:08:12Z, six minutes before the sweeper dispatched this review, under
`d0528ad1`. The formal APPROVED review is published by the trusted runner pinned to
`d59bf0237e6cbd103885c5ba66ade8fb0798a6b0`.
