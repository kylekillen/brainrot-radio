# PR #44 review — approval-published

<!--ran on: space-bunny-free-->

Ran on space-bunny-free. Independent code review, cycle 1 of 5.
PR: https://github.com/kylekillen/brainrot-radio/pull/44 — "cap keep_alive at 5m: fix 2h ollama hold on muse-glimmer:30b-mlx"
Reviewed head: 3da1f98d810aa8bb733a6242715a4c376483a664 (branch fix/cap-keep-alive-5m, base main, +2/-2, 2 files, not a draft)
Date: 2026-09-29 01:47:37 UTC

## Decision

APPROVE. All three gates pass on the exact head above. The reviewer gh identity
equals the PR author (kylekillen), so the formal APPROVED review is delivered to
the trusted runner for publication as the reviewer bot, and the merge lane lands
the PR. No merge was performed by this review.

## Gate 1 — correctness: PASS

- The change does exactly what its title and body claim, and nothing else:
  bin/test-single-pass.py:439 keep_alive 2h -> 5m, code-voice/server.py:117 30m -> 5m.
- The PR's premise is factually true on this machine. OLLAMA_MAX_LOADED_MODELS=1
  is really set, in both ~/Library/LaunchAgents/com.codevoice.ollama.plist and
  sh.brew.ollama.plist, so a qwen2.5:7b request on :11434 does evict a resident
  muse-glimmer:30b-mlx. Live GET :11434/api/ps returned [] at review time; :11435
  is a separate ollama serving qwen3:4b-instruct-2507-q4_K_M.
- ctx_tokens() (bin/test-single-pass.py:405-411) is the one call site whose
  behaviour could have shifted, because it reads the loaded context from
  /api/ps and falls back to 32768. It is not newly broken: the last real Glimmer
  run (test-runs/2026-09-28-single-pass-metrics.json) already recorded
  context_tokens 32768 with prompt_tokens_est 21914 + OUTPUT_RESERVE_TOK 9000
  = 30914 <= 32768, clearing the WRITER LANE ERROR guard at
  bin/test-single-pass.py:422 with 1854 tokens to spare. A shorter hold can only
  move ctx toward that same 32768 value — the value that already worked.
- Failure paths unchanged. summarize() (code-voice/server.py:107-134) still
  catches every exception and falls back to the cleaned first three sentences,
  logging either way. code-voice/server.log (4.5 MB, current through
  2026-09-28 19:43) contains zero "summarize failed" lines.
- No test asserts the old literals — no keep_alive reference exists anywhere
  under tests/ — so no test needed updating. tests/test_single_pass_harness.py
  covers the touched harness file and is green on this head.
- No security boundary is touched: both hunks are a request-body literal on a
  loopback ollama call, with no auth, input-validation or injection surface.

## Gate 2 — coherence: PASS

- Neither replaced value was a fix for a documented residency bug. 30m dates to
  05210fe "Add Code Voice" (2026-06-08) and 2h to 088def7 (PR #42, 2026-09-28);
  neither commit message cites a latency problem this change would reintroduce.
- The inline comment at code-voice/server.py:117 was rewritten to state the new
  intent rather than left stale ("keep summarizer resident through a work
  session" -> "cap: avoid evicting the 19 GB Glimmer on 11434").
- dictate_gateway.py is correctly untouched, and the body says so accurately: it
  talks to :11435 with KEEP_ALIVE defaulting to "-1m"
  (dictate_gateway.py:49,51), and its :11434 reword path
  (dictate_gateway.py:54,115,132) already passes that same "-1m".
- No doc in the repo records the old values (grepped .md/.json/.sh/.py).
- Completeness inside the repo: after this PR the only four keep_alive sites are
  2x "5m" plus 2x KEEP_ALIVE ("-1m"), so nothing in brainrot-radio holds a model
  on :11434 longer than 5m. No dead or duplicated code, no orphaned constant.

## Gate 3 — smallness: PASS

+2/-2 across two files in one commit. No refactor, no dependency change, no
formatting churn, no scope expansion, no drive-by edits, no test churn.

## CI receipt (pinned to the reviewed head, not the default branch)

- CI run 36508750519 (event push): head_sha 3da1f98d810aa8bb733a6242715a4c376483a664,
  status completed, conclusion success, 01:37:05Z -> 01:37:23Z.
- CI run 36508793900 (event pull_request): head_sha 3da1f98d810aa8bb733a6242715a4c376483a664,
  status completed, conclusion success, 01:37:39Z -> 01:37:55Z.
- Both head_sha values were read from the Actions API and compared literally to
  the captured pin, not inferred from "gh pr checks" passing.
- scripts/merge_gate_check.py --head 3da1f98d810aa8bb733a6242715a4c376483a664
  (check-only): CI lane green on this head (ci.yml, 2 runs / 2 check-runs), no
  protected paths touched, red-team lane not applicable (no
  "program:harness-parity" label). Exit 1 came solely from "no independent
  code-review APPROVED review pinned to this head" — which is this very review
  awaiting publication as the reviewer bot, not a substantive refusal. Nothing
  was merged by this session.
- PR state at review time: no prior comments, no prior reviews, therefore no
  standing HOLD (a HOLD requires both a literal "HOLD:" line and a
  "Reviewer session:" line in the same comment; there were zero comments).

## Findings (non-blocking; neither is a merge blocker)

1. code-voice/server.py:127 — summarize() uses urlopen(..., timeout=30). With a
   5m hold the summarizer is cold on most voice notes (consecutive turns are
   typically more than 5 minutes apart), so each one now pays a qwen2.5:7b load
   inside that 30-second budget. The warm path has always fit (0 failures in the
   log), but a marginal warm call at 26-29s could now tip past 30s into the
   existing fallback, producing a cruder voice note rather than an error. Graceful
   and logged, and an explicit trade the author chose. Deliberately not measured
   here: timing a load on the shared :11434 would itself evict Glimmer, the exact
   effect this PR removes.
2. Pre-existing, NOT introduced by this PR: ctx_tokens() takes models[0] from
   /api/ps without checking which model is resident, so a resident qwen2.5:7b
   would have its own context_length reported as the writer lane's budget. This
   change slightly reduces that exposure, since every other :11434 caller in the
   repo now unloads.

## Self-review guard

Not tripped. The author git identity is the fleet's generic task-worker
<kyle@observer.local> with an empty commit body (no session trailer), and
task-worker is a synthetic non-persona role with no standing session. This
reviewer's session is c6bec10ef7eb4f14aca71681ac110362; this workspace's
HANDOFF.md concerns observer-system PR #838 and holds no trace of authoring
this change, and the curated memory for this role is empty (early session). The
only brainrot-radio trace in the workspace status log is a prior review of PR #39
by a different reviewer session.

## Where the verdict went

Gate notes were posted to the PR as
https://github.com/kylekillen/brainrot-radio/pull/44#issuecomment-5882075763
(starting with the required "Reviewed on space-bunny-free" line, carrying no
"Reviewer session:" line). The formal review is left to the trusted runner,
which publishes it as the reviewer bot pinned to the pre-fetched head.
