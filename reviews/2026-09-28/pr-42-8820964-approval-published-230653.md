### 2026-09-28 23:06 — Reviewed PR #42: approved on the merits; already merged, formal seat via trusted delivery

Reviewed on space-bunny-free. Head reviewed: `8820964de32be418d5cd1bb84812b2626715e9cc` (captured before
reading the diff; unchanged at the end of review).

**State note — this PR is already on main.** It was squash-merged at 2026-09-28T20:31:36Z by `kylekillen`
as `088def7d26e46d08eab769a5da64d68fba1425a1`, which is currently the tip of `main`. No merge was performed
or attempted by this review; the approval is published through the trusted runner. This receipt records a
post-merge review of the exact merged head.

**Correctness — PASS.** Purpose: run the pre-registered New Hire test (single-pass variant B vs the aired
two-pass control A) and report the result. The delivered artifacts match the report: `metrics.json` verdict
is `FAIL` and its seven per-criterion booleans reproduce the PR body's table exactly (2 seam/leak hits,
QC FAIL, pitch present 397 words, 1,648 spoken words, 7% token ratio, judge 2-vs-5 on both axes). The harness
is fail-closed: `stage_write` exits if `not data.get("done")`, `stage_judge` exits on a lane error or
unparsable score JSON, and `stage_report` degrades to `INCONCLUSIVE` rather than passing on missing data.
A's writer tokens are labelled `ESTIMATE` at every point of use, and criterion 5 carries "(A = ESTIMATE)"
in its own name, so the estimate is never presented as measured. The blind judge order is seeded from a
sha256 of the date and recorded (`blind_order_XY: [A, B]`), and the judge lane is read from the cached
dispatch's own `model` field rather than the constant, so the label records the lane that actually scored.
The docstring's hard-limits claim holds: grep for `voice.py|mixer|artwork|publish|render_report|8765`
returns only the docstring lines, and every write is under `test-runs/`. Tests cover the scanners that feed
the pass/fail numbers — `tests/test_single_pass_harness.py`, 9 tests, passing locally and in CI.

**Coherence — PASS.** The harness deliberately keeps its own copy of the capped-source logic
(`compact_sources`) rather than editing `or_writer`, and the report says why: the daily pipeline's prompts
stay untouched. That is the right call for a test lane. The new `.gitignore` rule
(`test-runs/*-variant-A-copy.txt`) matches exactly what `stage_qc` writes for variant A
(`TEST_DIR / f"{date}-variant-A-copy.txt"`), so the copy of an already-aired script stays out of git while
variant B — which *is* the evidence — is committed. `test-runs/README.md` documents the artifacts and
repeats the no-render/no-publish boundary. No dead code: `VALID_TAGS`, `OUTPUT_RESERVE_TOK`, `b_tok_total`
and `sha` all have callers. `a_tok` guards its own division — the evidence string is the true-branch of
`... if a_tok else "n/a"`, so a `None` estimate cannot `ZeroDivisionError`.

**Smallness — PASS.** 4 commits, 11 files: one harness, one test file, one gitignore rule, one README, and
the test-run artifacts that *are* the deliverable. No dependency change, no formatting churn, no refactor
of production code. The seam-pattern list grew in the same change that added the tests that pin it, so the
calibration and its regression guard land together rather than as an orphan edit.

**CI receipt.** Two completed successful check-runs on this exact head —
`.github/workflows/ci.yml` run `36472296388` (push) and `36472302589` (pull_request), both `success`,
both `head_sha: 8820964de32be418d5cd1bb84812b2626715e9cc`, job 109097282626 / 109097302669. No pending,
no skipped. Gate receipt: `merge_gate_check.py --head 8820964d…` exited 1 on the single line
`code-review lane: no independent code review (non-red-team APPROVED review) pinned to this head`; the
red-team lane does not apply (no `program:harness-parity` label), the CI lane is green on this head, and no
protected path is touched. That is the expected seat-only refusal for an external-lane review — the formal
seat is supplied by the trusted runner. No comments and no formal reviews existed on the PR before this
review, so there is no standing HOLD or BLOCKING to clear.

**Diff-size artifact (not a defect).** GitHub reports 36 files / 2110 additions / 0 deletions; the true
contribution is 11 files. The recorded base sha `df0e2eb` is one commit behind the branch point `810b01b`,
and the 25 extra files all come from `810b01b` — which is already an ancestor of the merge commit
`088def7d` and of `main`, having reached it by another route. Confirmed with
`git merge-base --is-ancestor 810b01b origin/main` (yes) and against `088def7d` (yes). This is GitHub's
stale-base rendering, not scope creep in the change.

**Findings (non-blocking, for the next run of this harness).** `bin/test-single-pass.py:359`
(`estimate_writer_A`) and `bin/test-single-pass.py:627` (the `manifest` stage) both hardcode
`.tmp/covered-pending-2026-09-28.json` instead of deriving it from `date`, in a harness whose `--date` is a
required argument. For the 09-28 run this points at the correct file, so the delivered evidence is
unaffected; but a re-run on any other date would fingerprint and estimate against the 09-28 file, and the
manifest is the provenance record for the test. Folding `date` into that filename is the fix. Recorded, not
gating.

**Decision.** The change is correct, coherent and minimal for its stated purpose, and CI is green on the
reviewed head. Approving on the merits. Not merged by this review — the PR reached `main` before this
review ran, under `088def7d`; the formal APPROVED review is published by the trusted runner pinned to
`8820964de32be418d5cd1bb84812b2626715e9cc`.
