### 2026-09-29 13:41 — Reviewed PR #46: approval-published (three gates pass, CI green on the reviewed head)

Ran on space-bunny-free. Head reviewed and pinned: `2fb37f071b873c21e52bb42b63c6bf9987eac0b1`
(branch `fix/x-pulse-kyle-fleet-scrub`). PR: x_pulse: stop the scrub deleting "Kyle" and
"fleet" as production meta. This is the fix for the defect PR #41's review filed as task
`b555b616` — the META regex's bare words `\bKyle\b` and `fleet` deleting real news from the
X PULSE section the second-half writer prompt is told to mine for NFL/entertainment stories.

**Decision: APPROVE.** Not merged by this session — the trusted external lane posts the formal
review as the reviewer bot; the merge lane lands the PR afterwards.

**Correctness — PASS.** `META` drops the bare `\bKyle\b` and `fleet` alternatives and gains
`KYLE_INTERNAL`/`FLEET_INTERNAL`, anchored to the internal forms they stood in for.
Re-derived independently, not taken on faith: running the new test file against
`origin/main:x_pulse.py` reproduces the bug (`test_person_named_kyle_is_not_scrubbed_as_meta`
and `test_fleet_the_ordinary_english_word_is_not_scrubbed_as_meta` both FAIL on main, PASS at
head), so the two news tests genuinely pin the regression. `PRIVATE` — the GUARDRAILS row-18
invariant — is untouched. `scrub_dispatch`'s signature and sentence-level failure path are
unchanged, and `_keep` still refuses to return any text tripping META or PRIVATE, so the
wider word list cannot turn the clause trimmer into a leak. No caller outside the module reads
the regex internals (`generate-episode.sh` only invokes the script), and its second-half
prompt needs no change — it already directs the writer at this section.

**Coherence — PASS.** The new constants follow the file's existing module-level compiled-regex
convention (`PROVENANCE`, `META`, `SENTENCE`, `CLAUSE`, `PRIVATE`), are interpolated into
`META` in place rather than duplicating it, and are reused by both the scrub and the new tests.
No dead code, no second copy of the word list, no doc left contradicting the behaviour.

**Smallness — PASS.** 2 files, +79/-2, no dependency change, no refactor, no drive-by edit.
Test additions are three focused cases.

**CI receipt.** `gh pr checks` on the reviewed head: `pytest pass 14s`, `pytest pass 17s`;
two check-runs, both `conclusion: success`, both `head_sha` == `2fb37f07...`, two CI workflow
runs green (`ci.yml` = `pip install requests feedgen pytest` then `pytest tests/ -q`).
Locally: `116 passed` under the repo's own venv (3.13.15). The 3 collection errors under the
system `python3` are environmental and reproduce on main — `feedgen` is absent there and
`covered_guard.py:111` uses a PEP 604 `float | None` annotation 3.9 cannot evaluate;
hosted CI runs 3.12 and is green, so they are not this PR's.

`merge_gate_check.py --head 2fb37f07...` (check-only; this PR carries no
`program:harness-parity` label): CI lane green on this exact head, no protected paths, red-team
lane N/A. Its only refusal is the absent non-red-team APPROVED review — which is precisely what
the trusted runner posts from this receipt — so the gate is satisfied on publication, not a
block. No comments and no prior reviews on the PR, so no standing HOLD and no standing
REQUEST_CHANGES.

**Findings — none blocking.**

1. *Accepted trade-off, recorded for the next author (not a defect).* The anchors are finite
   lists, so sentences main used to drop now survive: "the fleet went silent for three hours",
   "Kyle's rules are that...", "Kyle Killen said...". This is a coverage gap in a heuristic
   corpus-grounded list, not a guardrail breach: GUARDRAILS row 18 forbids internal
   repo/role/launchd names, file paths, config keys and uncited counts of the listener's launch
   sites/workers/spend — all of which `PRIVATE` still covers, unchanged. The author grounded
   the anchors against all 69 dispatches and reports a full-corpus old-vs-new diff of 3 changed
   lines, all real news, with nothing internal added back. Widening the verb/possessive lists
   as the corpus grows is the right follow-up; it is not grounds to hold this fix.
2. *Test-strength nit.* In `test_internal_kyle_and_fleet_forms_are_still_scrubbed` the
   KYLE-QUEUE case appends "; not pulled further", which trips META on its own — so that
   assertion would still pass if the `KYLE[-_ ]QUEUE` alternative were deleted. Verified
   `META.search()` does trip on the KYLE-QUEUE token itself, so the anchor is genuinely
   present and the pin is real; it just reads stronger than it is. Trivial to tighten later.
3. *Self-review identity, recorded plainly because it bears on how much this approval weighs.*
   The author commit is `task-worker <task-worker@localhost>`, the same role label and model
   as this reviewer. That string is a shared fleet service identity, not a session id — PR #44
   and several `main` commits carry the same author name from unrelated sessions, while this
   repo's review receipts are committed as `code-reviewer`. The authoring dispatch wrote its
   log at 13:37:02Z and ended; this review dispatch began 13:37:30Z in a separate worktree
   under session `8c2a5ed7e21f4a298d20f34d2d399dfd`. Different session, so the self-review
   guard does not trip. Caveat stated rather than hidden: I had read that authoring log (this
   review's own charter step points at `status.d/`), so my three gates were re-derived with
   empirical probes the author did not report — the fails-on-main reproduction, the finite-list
   leak probes, and the KYLE-QUEUE test-reason check — but the two principals are not a fully
   independent pair of eyes, and a human should know that when weighing this receipt.
