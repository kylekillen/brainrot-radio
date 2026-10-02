### 2026-10-02 00:57 — PR #50 review: approved (approval published)

Reviewed head: `0b4a585ce3a71975691078552c1682c9a9bb945a` (captured before the diff was
read; re-confirmed unmoved at the end of the review). Cycle 1 of 5.

<!--ran on: space-bunny-free-->

Decision: approve. All three gates pass on this head. Not merged by this lane — the
external code-review lane publishes the formal APPROVED review from the task result
and the merge lane lands the PR.

**CI receipt.** Hosted CI green on the reviewed head: 2 × `pytest` check-runs, both
`completed`/`success`, each with `head_sha` equal to
`0b4a585ce3a71975691078552c1682c9a9bb945a` (started 2026-10-01T23:01:08Z and
23:01:10Z, completed 23:01:22Z and 23:01:30Z). `mergeable_state: clean`, labels
`[]` (not harness-parity, so the red-team composed lane does not apply). Local run on
the tarball of this exact SHA: **164 passed**, with `tests/test_correct_feed_description.py`
and `tests/test_render_report.py` erroring at collection on a missing module
(`requests` here, `feedgen` in the author's environment) — neither file is touched by
this change, exactly as the PR body states. `bash -n generate-episode.sh` clean.

**Evidence route.** `review_preflight.py` exited 3 and printed UNVERIFIED: GitHub
GraphQL was rate-limited for the account for the whole of this session
(`gh api graphql` returns `RATE_LIMITED` for user 192653736) while REST stayed healthy
(core 3818/5000). Every authoritative fact was therefore read over REST —
`pulls/50`, `pulls/50/files`, `pulls/50/reviews`, `issues/50/comments`,
`commits/<sha>/check-runs`, `commits/<sha>/status`. This is the documented fallback,
not an evidence gap: metadata, the complete diff, the prior review and the hosted CI
state were all reachable.

- **Correctness: pass.** Behaviour matches the stated purpose. The pass-1
  BUILD PITCH bullet no longer orders the folder locator; it still asks for the
  sign-off, now in general terms, and carries the explicit "LEAVE THE SENTENCE OUT"
  escape. `script_guard.py` is stdlib-only, deterministic, and wired in at two points:
  pre-QC (`generate-episode.sh:636-640`, findings handed to the skeptics alongside the
  existing `QC_DEDUP_BLOCK`) and post-QC as Step 3.6 (`generate-episode.sh:796-811`),
  deliberately last before the render so it audits the text `voice.py` will speak,
  including top-up material appended after the skeptics ran.

  The prior cycle's blocking finding is genuinely fixed, verified rather than taken on
  trust: `worktree`, `sweeper`, `.venv`, `plist` and `the observer` are gone from
  `LEAK_PATTERNS`, and `test_the_aired_archive_has_no_false_positive_leaks` is not
  vacuous — it finds 4 tracked fixture scripts under `test-runs/*/scripts/`, asserts
  non-emptiness, and passes. Independent probe of the 09-24 incident: the real
  `observer-system`/`build-pitches` markers still fire, the ordinary vocabulary does
  not. The second half of that finding is fixed too — `QC_GUARD_BLOCK` now scopes
  MUST-FIX to `speaker_collision`, `back_to_back_transition` and `unsourced_byline`
  and marks `internal_name` / `internal_metric` / `private_system` ADVISORY with an
  explicit "Do not edit a line just because a pattern matched it", which is the correct
  mitigation for a heuristic feeding an editor.

  All four non-blocking notes from the prior cycle are addressed: `QC_GUARD_BLOCK=""`
  is initialised beside `QC_DEDUP_BLOCK`; the flag file uses `${QC_VERDICT:-n/a}`,
  matching the file's own convention at `generate-episode.sh:781`; the three rule
  bodies now have direct unit tests; and the unfailable `assert "pass-1" not in line
  or True` is replaced by `_bullet()`'s exactly-one-bullet assertion.

  Callers and failure paths: both call sites pass valid arguments, both are `|| true`
  and non-fatal by design (no `exit` added), cwd is `$BRAINROT_DIR` so
  `python3 script_guard.py` resolves, `RUN_ID` is set at `generate-episode.sh:38`
  before the flag write, and `logs/` is already required by the run's own logging.
  A guard crash therefore degrades to "no guard check" rather than killing an episode
  — the same silent-degradation shape an earlier review flagged on the dedup call
  sites, here deliberate and documented. No new injection surface: bash does not
  re-expand the result of a parameter expansion inside a heredoc, so script text
  interpolated through `${QC_GUARD_BLOCK}` cannot execute.

  Independently exercised beyond the author's own tests: the headline-byline form the
  last commit claims to have fixed (`## 1. (Cheng Ting-Fang / Nikkei Asia) …` against
  a truncated body) now reports `Ting-Fang`, and the surname no longer resolves to the
  outlet's last word; a full-text brief item is correctly not treated as truncated;
  an empty brief returns no findings rather than raising; the name pattern is
  hyphen/en-dash tolerant. `tests/test_no_private_system_on_air.py`, the pre-existing
  lock on the very bullet this PR edits, still passes (3).

- **Coherence: pass.** The module follows the established `dedup_guard.py` convention
  rather than inventing one — findings on stdout, exit 3 when findings exist, `2>/dev/null
  || true` at the call site, a flag file beside the qc-FAIL flags. Findings are rendered
  for QC's own consumption (rule, line, and the remediation text QC needs) and the
  prompt assigns each rule to the skeptic that owns it, matching the file's existing
  Agent B / Agent C split. The Step 3.5 → Step 3.6 ordering is documented at the
  anchor rather than left implicit. No dead or duplicated code: the only redundancy is
  the defensive `out[-1]["line"] != line` dedupe in `speaker_collisions`, which cannot
  currently fire and is harmless.

- **Smallness: pass.** 4 files, +562/-1. No dependency added, no unrelated refactor, no
  formatting churn, no scope expansion. The middle commit is conflict resolution only —
  main's render-floor top-up and the new guard both kept, in the order that makes the
  guard mean what it says.

**Findings: none blocking.** Three advisory notes for the author, none of which
warrant holding the PR:

1. `generate-episode.sh:658` — the injected block says a real leak "is MUST-FIX under
   the GUARDRAILS row below", but there is no GUARDRAILS row below the injection point
   in `step3-qc.txt`; the row lives in `.claude/commands/qc-episode.md:47` and
   `GUARDRAILS.md:18`, which the agent is instructed to read. Wording only — the agent
   has the guardrail in context. "the GUARDRAILS row" would read correctly.
2. `logs/guard-$RUN_ID.flag` is not wired into the publish-time Kyle-notification
   block at `generate-episode.sh:1004-1017`, which reads the qc-FAIL and qc-ERROR flags.
   Deliberate per the Step 3.6 comment ("a visible flag is the right weight"), and the
   ⚠️ line does reach `logs/generate.log` — but the flag is log-only by design, not a
   notification.
3. `script_guard.py` is not in `CLAUDE.md`'s Files table. The same omission was flagged
   advisory for `dedup_guard.py`, `covered_guard.py`, `run_guard.sh` and
   `watch-episode.sh` in `reviews/2026-09-25/pr-39-3b290d0-approved-and-merged-180927.md`,
   so this inherits standing documentation debt rather than breaking a convention.
   Related: `\b(our|my) (agents|workers?|repos?)\b` and `\bdurable record\b` can still
   fire on a sentence that is ordinary content for a show whose featured beat is
   multi-agent tooling. `launchd` and `credit balance` are explicitly named in
   `GUARDRAILS.md:18` and are project-justified; the other two are the softer edge.
   ADVISORY status bounds the consequence to a logged note.

**Merge gate.** `merge_gate_check.py --head 0b4a585ce3a71975691078552c1682c9a9bb945a`
could not execute: it reads PR state via `gh pr view` (GraphQL), so it exited 1 three
times with `gate check failed to read PR state: … GraphQL: API rate limit already
exceeded for user ID 192653736`. That exit 1 is a transport failure of the checker,
not a lane verdict — it is indistinguishable, by exit code alone, from a genuine lane
refusal. Its components were therefore verified directly over REST: hosted CI is green
on this exact head (above); no `CHANGES_REQUESTED` or `BLOCKING` review is pinned to
`0b4a585` (the only one on the PR is pinned to the superseded `10b8350` and is
addressed by the head under review); zero `APPROVED` reviews exist on this head yet,
which is expected on the external lane because the runner publishes the formal review
from the task result; the red-team lane is not applicable (no labels, no
`program:harness-parity`); no `CODEOWNERS` and no branch protection on `main`, and the
four changed files are an episode generator, a new guard and two test files — no
agent-governing rulebook, so the two-distinct-reviewer-seat rule does not apply.

**HOLD check.** One comment on the PR. No comment carries a literal `HOLD:` line, so
no HOLD stands (no `HOLD CLEARED:` needed). Nothing to unblock.

**Self-review guard: clear.** This session did not author the PR. The three commits
are `task-worker <kyle@observer.local>` dated 2026-09-30T22:34 and 2026-10-01T23:00;
this session's `HANDOFF.md` records unrelated observer-system work (PRs #1951, #1908,
#1821), and an independent reviewer session (`killen-fleet-reviewer`) already posted the
CHANGES_REQUESTED on the first head. Different session: reviewed, not self-reviewed.