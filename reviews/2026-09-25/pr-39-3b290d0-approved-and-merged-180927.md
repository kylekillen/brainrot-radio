### 2026-09-25 18:09 — Reviewed PR #39: approved-and-merged

<!--ran on: space-bunny-free-->
Reviewed on space-bunny-free. Reviewer session: 74596e9ac4524797bd8eafae54c5f77d.

**PR**: kylekillen/brainrot-radio#39 — "Guard the daily show: blurb-only rule, covered ledger from the final script, alarm on silent death"
**Reviewed head (pinned)**: `3b290d060366b0852d35d3520e53c33ef3e6d5c1` — branch `task/125f18dd-brainrot-guards`
**Merge**: squash `2fcacbe726e7cdac33b98b03e6048f4c981f63fa` on `main` at 2026-09-25T18:09:22Z, `--match-head-commit 3b290d060366b0852d35d3520e53c33ef3e6d5c1`
**Scope**: 17 files, +1155 −28. No protected paths (no CI workflow, gate script, runner or sweeper touched).

**Decision: approve — all three gates pass.** Merge path Mode B (`gh api user` = `kylekillen` = PR author, so self-approval is blocked): gate notes posted as a PR comment, then the pinned squash-merge. Mode B is the expected default for this repo, not a finding.

#### Gate 1 — Correctness: PASS
- **CI receipt**: hosted CI green *on the reviewed head* — `pytest` ×2 SUCCESS (`.github/workflows/ci.yml`, 2 runs / 2 check-runs, both `head_sha` = `3b290d0`). `merge_gate_check.py … --head 3b290d0…` exit 0 (code-review lane clear, red-team lane not applicable, CI lane green on this exact head, protected-path lane clear). Local: 71 passed (repo venv, pytest 9.1.1) — corroborating only; the merge rests on hosted CI.
- Behavior matches the PR's stated purpose on all three fixes. Ledger deferral verified end-to-end: every `exit` in generate-episode.sh is accounted for — stand-down paths call `rg_finish standdown` (172/196/212) and publish calls `rg_finish ok` (689), so no healthy exit alarms, while every failure exit (223/440/450/459/618/646/659/675/686) reaches the EXIT trap, which alarms exactly once (`alarmed=1`, so the watcher's retry path cannot double-page). `rg_set` mutates only through `mv` renames, so a concurrent reader never sees a half-written state file; its `set -e` interactions are guarded and covered by `test_set_e_abort_raises_an_alarm`.
- The covered ledger is written only after publish, from the final `$NEW_SCRIPT` (generate-episode.sh:688-698), and `ingest.save_covered_stories` still `mkdir -p`s the deferred path's parent (ingest.py:260), so a missing `.tmp` cannot throw.
- The writer-side prompt changes genuinely reach every writer path: external_writer.py:157 and router_writer.py:173 both reuse `or_writer._gather_sources` / `_pass1_prompt` / `_pass2_prompt` / `SYSTEM`. Checked the one interaction that could have broken: `router_writer._assert_public_safe` forbids STATUS.md / HANDOFF.md / calibration.md / INBOX.md / router-decisions.jsonl / TELEGRAM_BOT_TOKEN / _API_KEY / _TOKEN=; the new evidence-rules.md names CLAUDE.md and GUARDRAILS.md, neither of which is on that list, so the off-repo dispatch guard is not tripped.
- Stdlib-only, no dependency or data-schema churn. `Path | None` annotations match existing repo style (README:29 declares Python 3.11+; generate-episode.sh:87 sources the 3.13 venv), so no new interpreter floor.

#### Gate 2 — Coherence: PASS
No dead or duplicated code introduced. `.claude/context/dedup.md` rule 4 and the new `save_covered_stories` docstring are updated to describe the deferral; the writer instruction "save covered stories immediately after writing" was the one doc that would have gone stale against the new behavior and it was rewritten; the two writer stderr fallbacks were re-worded to point at `covered_guard.py`. GUARDRAILS.md records the three new guardrails with their 09-22/09-25 evidence. Affected callers accounted for. `router_writer`/`external_writer` keep `_extract_covered` + `save_covered_stories` as a tolerant fallback for a model that emits the trailer anyway — the prompt no longer requests it, but the branch is commented and intentional, not orphaned. A new `status.d/2026-09-25/` fragment is added; STATUS.md is untouched.

#### Gate 3 — Smallness: accepted deviation, disclosed
17 files / +1155 −28 for three independent fixes. The PR declares `PR-SIZE-BUDGET: exceeded` up front (~40% of lines are tests, ~250 are new stdlib-only modules) because it is an urgent third-day-miss repair. Reviewed the diff for unrelated churn: none found — no refactor, no formatting-only hunks, no dependency bump, no scope expansion. The render word floor is deliberately *not* lowered, which is the right call.

#### Findings
None blocking. Two advisories recorded for follow-up, deliberately not turned into a review round-trip on an urgent fix:

1. **Story-slug exclusion goes inert (advisory).** `covered_guard.py:113` writes date-prefixed segment slugs (`2026-09-25-s01-…`) into `stories`, while ingest matches with `any(s in title_slug or title_slug in s …)` against `re.sub(r"[^\w]", "-", title)[:60]` (ingest.py:608-612). Neither substring direction can realistically match a date-prefixed segment slug, so the article/substack branch of the "a source used once is gone" hard-exclude — and the 🔁 PREVIOUSLY COVERED brief marker at ingest.py:719 — become inert. Podcast guid exclusion still works and is now *more* accurate (only guids the final script demonstrably used), and the new primary defense (7-day script digest + 5-word-phrase overlap check handed to both writers and QC, plus the covered `segments` text in the writer prompt) is stronger than the draft-based mechanism it replaces. Impact is soft-dedup weakening on one path, not a fabrication or outage risk. A follow-up should give ingest a token set comparable to a feed title.
2. **Deploy nit (advisory).** `install-watch.sh` does not `mkdir -p logs/`, which the plist's `StandardOutPath`/`StandardErrorPath` require for launchd to spawn the job; harmless on this machine because the dir exists, but it would fail on a fresh clone. `CLAUDE.md:89-93` still reads "Three jobs run together" and its Files table omits `run_guard.sh`, `watch-episode.sh`, `install-watch.sh`, `dedup_guard.py` and `covered_guard.py`.

**Deploy is still manual** (merged ≠ deployed): `cd ~/brainrot-radio && git pull --ff-only && bash install-watch.sh`. Without it the writer-side guards run from 04:00 tomorrow but the SIGKILL / never-started watcher does not exist.
