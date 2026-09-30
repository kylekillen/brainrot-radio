### 2026-09-30 11:35 — The 05:15 run is the THIRD identical loss of the day; the 402 line still names OpenRouter and the provider is still Google's

Alarm `20260930T052700-brainrot-radio-57723-7293` (run `20260930-051500`,
exit 1, no episode) is the 05:15 MDT **recovery re-run** of the 04:00 failure
that already alarmed at `20260930T041449-brainrot-radio-94750-552` and was
diagnosed one hour ago in `status.d/2026-09-30/103500-offload-402-is-google-not-openrouter.md`.
Same three lanes, same order, third time in 24h. This entry adds only what is
new; it does not re-open the diagnosis.

`run_guard.sh:85` (`rg_on_exit` → `rg_alarm`) raised it: `generate-episode.sh`
exited non-zero with no `RG_OUTCOME`, so `state=failed rc=1 alarmed=1` landed in
`.tmp/run-state-20260930-051500.env`. **That alarm is correct, not a false
positive** — the run genuinely shipped nothing.

Chain this run (`logs/generate-20260930-051500.log`, 388 lines):

| # | Lane | Body | Real state, re-measured 11:28Z |
|---|---|---|---|
| 1 | external free `nemotron-3-ultra-550b-free` | 429 `free-models-per-day-high-balance` ×2 | `limit_source: openrouter_free_tier_daily`, flat 1000/day, `Remaining: 0`, reset `1790812800000` = **2026-10-01T00:00:00Z** |
| 2 | Claude `write-pass1`, `-retry` | `You've hit your weekly limit · resets Oct 1 at 8am` | `~/.observer/burn-status.json` + `lane-availability.json` (gen 11:28:53Z): `weekly_pct: 1.0`, `weekly_reset: 1790863200` = **2026-10-01T14:00:00Z**, anthropic `quota-exhausted` |
| 3 | offload `or_writer.py` | 402 at max_tokens 16000/8000/4000 | **Google AI Studio prepay**, not OpenRouter (see below) |

`~/.observer/pause-flags/podcast.pause` still stands (burn_monitor, 95% of the 7d
allowance, raised 2026-09-28T18:14:45Z), so the run was BURN-DEGRADED and wrote
on the free lane by Kyle's 2026-09-08 ruling. The degrade remains correct and is
not the cause: Claude was at `weekly_pct: 1.0` regardless, so a skip would have
lost the same episode. The flag's own `auto-clears when utilization drops below
90%` cannot fire before 2026-10-01T14:00Z.

### The 402 line still mislabels the provider, and the fix is still unlanded

Verified again at this head, byte-for-byte: `or_writer.py:344`, `:362` and
`:370` hard-code the string `OpenRouter`, but the actual transport is
`or_complete.complete()` (line 358), and `OFFLOAD_BASE_URL` resolves to
`https://generativelanguage.googleapis.com/v1beta/openai`. The log line is a
string constant, not the provider. The reporting fix is **PR #47** (opened
2026-09-30T00:41:19Z) plus guard **PR #48** (01:12:54Z) — both still OPEN,
awaiting an independent reviewer. This run's log and the alarm's `raw_line`
both carry the false attribution, one day after the correction was filed.

### Currency check — counted over whole files, never from a tail

- `grep -c "HTTP Error 402"` over all 258 `logs/generate-*.log`: **24 hits in 6
  files** — 09-23 ×2, 09-29 ×2, 09-30 ×2. Same three dates only.
- `grep -l "free-models-per-day"`: **4 files** — 09-29 ×2, 09-30 ×2 (new class
  on 09-29; it was absent on 09-23, when only the credit condition bit).
- `grep -h "You've hit your weekly limit" | wc -l`: **40 hits across 13 files**,
  first on 2026-08-24. The weekly cap has been clipping runs for five weeks.
- `output/*.mp3` last written **2026-09-28 04:26**. No episode 09-29, none
  09-30. `logs/check-episode.log` shows 09-29 FAIL twice and 09-30 FAIL plus a
  05:15 recovery launch — the same two-run-per-day pattern both days.

Dated against the repo's own fix history: `git log --since="2026-09-28"` shows
the diagnosis (commits `f4dde0f`, `cdc9d05`, `e5ff10f`) landed **before** this
alarm went quiet, and nothing on `main` has changed a writer lane since. The
cause was diagnosed and is not yet cured.

### What did not change

No threshold, guard, retry, provider or episode logic touched. The 6,000-word
render floor in `voice.py` was never reached — the run aborted at pass 1,
before a script existed — and stays exactly where it is. `generate-episode.sh`,
`or_writer.py` and `run_guard.sh` on `main` are byte-unchanged by this
investigation; no daemon restart is needed.

**The one lever that is neither money nor a calendar date** is pointing the
writer at a lane measured alive. `lane-availability.json` (11:28:53Z) lists
`groq`, `local`, `mistral`, `opencode`, `opencode-cli` as alive and anthropic /
codex / google / meta / openrouter / orcarouter / straitly as not. That is a
pipeline design change with a measured quality warning — the 09-28 New Hire
test had local `muse-glimmer:30b-mlx` produce 1,648 spoken words against the
2-pass control's 9,596 and fail QC — so it is not a responder's move and not a
threshold fix. It needs the call it has never been given.
