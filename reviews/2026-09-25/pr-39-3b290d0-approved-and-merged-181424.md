### 2026-09-25 18:14 — Reviewed PR #39 (cycle 1): approved-and-merged, independent second pass

<!--ran on: space-bunny-free-->
Reviewed on space-bunny-free. Reviewer session: f8b7d4044cd74070acd6ce0673886d04.

**PR**: kylekillen/brainrot-radio#39 — "Guard the daily show: blurb-only rule, covered ledger from the final script, alarm on silent death"
**Reviewed head (pinned)**: `3b290d060366b0852d35d3520e53c33ef3e6d5c1` — branch `task/125f18dd-brainrot-guards`
**Scope**: 17 files, +1155 -28. No protected paths (no CI workflow, gate script, runner or sweeper touched).
**This session performed no merge**: the PR was already MERGED when this cycle started. Review lane `74596e9ac4524797bd8eafae54c5f77d` posted its approval at 2026-09-25T18:09:17Z and squash-merged as `2fcacbe726e7cdac33b98b03e6048f4c981f63fa` with `--match-head-commit 3b290d06...` at 18:09:22Z, and landed its receipt at 8d093cf. What this receipt records is an INDEPENDENT re-derivation of the three gates on the same head, not a rubber stamp. Concur.

#### Gate 1 — Correctness: PASS (re-derived)
- **CI receipt**: hosted CI green on the exact reviewed head — `pytest` x2, both `status=completed conclusion=success head_sha=3b290d06` (check-run ids 108181971784, 108181993518; runs 36168486423, 36168492957). Local corroboration only: 71 passed in 18.04s (brainrot-radio venv, python 3.13).
- Merge fidelity: `git diff 3b290d0 origin/main` outside `reviews/` is EMPTY — the tree on main is what was reviewed, nothing else rode in.
- Re-checked the three things that could have silently broken:
  1. the deferred-ledger path — `ingest.save_covered_stories` still does `covered_file.parent.mkdir(parents=True, exist_ok=True)` (ingest.py:259) for the new `.tmp/covered-pending-DATE.json` target, so a missing `.tmp` cannot throw;
  2. the off-repo dispatch guard — ran `router_writer._assert_public_safe` against `.claude/context/evidence-rules.md` and against real `_pass1_prompt`/`_pass2_prompt` output built from this checkout: all clean (the file names CLAUDE.md and GUARDRAILS.md; the eight forbidden markers are STATUS.md, HANDOFF.md, calibration.md, INBOX.md, router-decisions.jsonl, TELEGRAM_BOT_TOKEN, _API_KEY, _TOKEN=);
  3. ordering on the writer side — `rg_start` + the EXIT trap are installed (generate-episode.sh:165-166) before the first `log` call, and `source venv/bin/activate` (line 87) precedes every `dedup_guard.py` invocation (313, 466, 554), so the guard runs under the right interpreter. Both prompt builders also survive an empty source set instead of raising.
- Behavior matches the PR's stated purpose on all three fixes: draft claims park in `.tmp/covered-pending-*.json`; the live ledger is replaced only after `log "Publish complete"` from the final `$NEW_SCRIPT`; an exit that never declares ok|standdown alarms once through the EXIT trap, and the watcher covers SIGKILL / hang / never-started.

#### Gate 2 — Coherence: PASS
Fits the existing architecture: stdlib-only, reuses `or_writer`'s `_gather_sources` / `_pass1_prompt` / `_pass2_prompt` / `SYSTEM` so the external and router writers inherit the evidence rules, per-item ledger and 7-day AIRED digest without duplicating them; keeps ingest's ledger shape and adds only a `derived_from` field. `.claude/context/dedup.md` rule 4, the `save_covered_stories` docstring, both writer stderr fallbacks and GUARDRAILS.md are updated to the new behavior; STATUS.md is untouched and a new `status.d/2026-09-25/` fragment is added instead. `router_writer` / `external_writer` keep `_extract_covered` as a deliberate, commented fallback for a model that emits the trailer anyway — not orphaned code.

#### Gate 3 — Smallness: accepted deviation, disclosed
17 files / +1155 -28 for one incident's three coupled fixes, ~40% of lines tests, with an explicit `PR-SIZE-BUDGET: exceeded` in the PR body. No unrelated refactor, formatting churn, dependency bump or scope expansion found; the render word floor is deliberately not lowered.

#### Findings
None blocking. I independently reached the first pass's two advisories and add a third — all follow-ups, none of which restores a fabrication or silent-miss risk:
1. `covered_guard.py:113` writes date-prefixed segment slugs (`2026-09-25-s01-...`) into `stories`, which cannot match ingest's title-slug hard-exclude in either substring direction (ingest.py:608-612), so that soft-dedup path and the brief's PREVIOUSLY COVERED marker (ingest.py:718-719) are inert; podcast-guid exclusion is unaffected and now more accurate, and the 7-day script digest + QC phrase-overlap check carry the load instead.
2. `install-watch.sh` does not `mkdir -p logs/`, which the plist's StandardOut/StandardErrorPath need for launchd to spawn the job (harmless on this machine, fails on a fresh clone). CLAUDE.md:89-93 still says "Three jobs run together" and its Files table omits run_guard.sh, watch-episode.sh, install-watch.sh, dedup_guard.py, covered_guard.py.
3. NEW in this pass: the `dedup_guard.py` calls in generate-episode.sh are wrapped in `2>/dev/null || true`, so if the dedup guard itself ever crashes the run degrades silently to "no dedup check" with nothing raising — the silent-failure shape this PR exists to remove, on the new guard itself. A one-line existence/version check on those three call sites would close it.

**Deploy is still manual** (merged != deployed): `cd ~/brainrot-radio && git pull --ff-only && bash install-watch.sh`.
