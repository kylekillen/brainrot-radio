### 2026-09-30 22:49 — PR #50 review: changes requested

Reviewed head: `10b8350ad1db61fdf87672151391775607d9924e`. Ran on space-bunny-free.

Decision: changes requested. The prompt fix (the headline change) is correct and
well-locked; the blocker is in the new guard that feeds QC.

- Correctness: fails on one citable defect. `script_guard.py:55` and
  `script_guard.py:59` carry generic on-air vocabulary in `LEAK_PATTERNS` —
  `\bworktree\b`, `\bsweeper\b`, `\.venv\b`, `\bplist\b` in `internal_name`, and
  `\bthe observer\b` in `internal_metric` — and `generate-episode.sh:588-589`
  escalates every guard hit to QC as "MUST-FIX — they are exact string/tag
  matches, not judgment calls", after which QC edits the script directly.
  Reproduced against the repo's own aired archive:
  `python3 script_guard.py check test-runs/2026-09-28-sonnet-bundle/scripts/killen-time-2026-09-24.txt`
  reports `L61 internal_name: "worktree"` on the passage describing Cline
  Desktop's git worktrees and the author/janitor split — content that aired on
  09-24 and sits squarely inside the prompt's named "Agents & Building With AI"
  beat (Latent Space, Simon Willison, Karpathy, a16z). Also confirmed by probe:
  "the observer effect" matches `internal_metric`, ordinary `.venv` packaging
  talk matches `internal_name`, and "a sweeper loop" matches `internal_name`.
  Smallest adequate fix: drop or fleet-context-gate those tokens, and add a
  regression test asserting `script_guard.leaks()` runs clean over
  `test-runs/*/scripts/*.txt` (it fails today on killen-time-2026-09-24.txt:61).
  Secondarily, scope the QC prompt's blanket MUST-FIX to the collision and
  byline rules, which really are exact; the PR itself disproves "exact string
  match implies a real leak" when it deliberately declines to flag
  "point an agent at it / greenlight the build" (script_guard.py:63-70).

- Coherence: the pattern set is inherited verbatim from `SEAM_PATTERNS` in
  `bin/test-single-pass.py:600-625`, whose consumer is a measurement harness
  that only counts defects in a diagnostic report. Reusing it unchanged for an
  enforcing consumer changes the consequence of a false positive from "one more
  count" to "QC cuts a sentence", which is the mismatch above;
  `script_guard.py:47-50`'s own comment claims the trim kept "the markers that
  describe Kyle's setup rather than the show", and these tokens do not describe
  his setup. Otherwise coherent: both call sites pass correct arguments, cwd is
  `$BRAINROT_DIR` via generate-episode.sh:86 so `python3 script_guard.py`
  resolves, both call sites are `|| true` and non-fatal as designed (no `exit`
  added in step 3.5), and the flag file lands beside the existing qc-FAIL flags.

- Smallness: passes. 3 files, +392/-1, no dependency, no unrelated refactor, no
  formatting churn, and the diff is confined to the prompt, the guard and its
  tests.

- Hosted CI: green on the reviewed head — 2 `pytest` check-runs, both
  `completed`/`success`, each with `head_sha` equal to
  `10b8350ad1db61fdf87672151391775607d9924e`. Local run agrees: 106 passed with
  `tests/test_correct_feed_description.py` and `tests/test_render_report.py`
  ignored for the missing `feedgen` module, exactly as the PR body states.
- Merge gate: `merge_gate_check.py --head 10b8350ad1db61fdf87672151391775607d9924e`
  reports CI green, no protected paths touched, red-team lane not applicable,
  and the code-review lane awaiting the formal seat this lane publishes. No HOLD
  comment on the PR (zero comments, zero reviews).

Non-blocking notes:

1. `generate-episode.sh:585` — `QC_GUARD_BLOCK` is never initialized to `""`
   before being expanded in the heredoc at `generate-episode.sh:611`, unlike
   `QC_DEDUP_BLOCK=""` two lines up at `generate-episode.sh:575`. Benign today
   (the script sets only `set -e` at line 9, no `set -u`), but it is a one-word
   fix and the asymmetry is the exact shape of a future `set -o nounset`
   breakage in the daily run, in the common case where the guard is clean.
2. `generate-episode.sh:691` — bare `$QC_VERDICT` in the flag file. On the
   gemini path `QC_VERDICT` is never assigned (it is set at
   `generate-episode.sh:628`, inside the non-gemini branch), so the flag file
   records an empty verdict. The file's own convention at
   `generate-episode.sh:781` is `${QC_VERDICT:-n/a}`.
3. The new 255-line module ships with no direct unit tests for
   `speaker_collisions`, `leaks` or `unsourced_bylines`; only
   `test_the_sanctioned_sentence_passes_the_deterministic_guard` exercises the
   guard, on one case. The archive regression test in the blocking fix covers
   most of that ground.
4. `tests/test_build_pitch_prompt.py:35` — `assert "pass-1" not in line or True`
   is unconditionally true and can never fail.