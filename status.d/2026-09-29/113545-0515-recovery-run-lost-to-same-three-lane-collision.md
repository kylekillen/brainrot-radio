### 2026-09-29 11:35 — The 05:15 recovery run died to the SAME three-lane collision as the 04:00 run; the 402 is a credit condition, not a code defect

Alarm `20260929T052636-brainrot-radio-41742-30996` names `or_writer: OpenRouter
completion failed at all budgets: HTTP Error 402: Payment Required`. That is the
last body, not the disease — the same shape already logged an hour earlier in
`status.d/2026-09-29/103200-three-writer-lanes-dead-simultaneously.md`, and this
run is the 05:15 MDT *recovery re-run* of the 04:00 failure, so it is the second
identical loss today, not a new class.

Measured this run (`logs/generate-20260929-051500.log`, 375 lines):

| # | Lane | Body | Real state |
|---|---|---|---|
| 1 | external free `nemotron-3-ultra-550b-free` | 429 `free-models-per-day-high-balance` ×2 (attempt + retry) | `limit_source: openrouter_free_tier_daily`, `X-RateLimit-Limit: 1000`, `Remaining: 0`, reset `1790726400000` = **2026-09-30T00:00:00Z** |
| 2 | Claude (`write-pass1`, `-retry`) | `You've hit your weekly limit · resets Oct 1 at 8am (America/Denver)` | `~/.observer/burn-status.json` now reads `weekly_pct: 1.0`, `weekly_reset: 1790863200` = **2026-10-01T14:00:00Z** |
| 3 | OpenRouter offload (`or_writer.py`) | 402 at max_tokens 16000/8000/4000 | footer `OpenRouter: $-0.20 of $105 remaining` — overdrawn |

Currency check (b), counted with `grep -c` over whole files, never from a tail:
`HTTP Error 402` appears **16 times across 4 `generate-*.log` files**, on
**2026-09-23 and 2026-09-29** only. `You've hit your weekly limit` appears **12
times** across the September generate logs. This is a recurring capacity
condition, not a one-off.

Three things this run adds that the 04:32 entry did not have:

1. **The 1000/day free bucket was already empty 11.3 hours into the UTC day.**
   The 429 is stamped `11:16Z`; the UTC day began `00:00Z`. The show's own 04:00
   MDT slot is `10:00Z` — *earlier in the day than the moment the bucket died*.
   The podcast spent at most 4 of those dispatches on a ~343,390-char prompt, so
   ~996 came from elsewhere in the fleet. **`free-models-per-day-high-balance` is
   an account-level daily bucket the fleet is eating before the show gets to
   run** — the midnight reset is therefore NOT a reliable recovery, and no
   scheduled event will fix this. It needs a money call.
2. **The burn gate is not the cause, and degrading is still correct.** The
   `podcast.pause` flag (95% at 2026-09-28T18:14:45) forced `PODCAST_ENGINE=external`
   per Kyle's 2026-09-08 ruling. But Claude is at `weekly_pct: 1.0` — dead
   regardless — so the degrade changed which lane died first, not whether the
   episode shipped. A skip would have lost the same episode. The flag's own
   `auto-clears when utilization drops below 90%` cannot fire before 2026-10-01T14:00Z.
3. **Two log lines now demonstrably lie, and both are reporting-class.** See the
   task filed alongside this note; not edited in place because `generate-episode.sh`
   is a 53KB bash script read by byte offset while running and `com.mojo.brainrot-watch`
   re-arms every 600 s, so an in-place edit risks corrupting a live run.

Counts, not tails: the render word floor was **never reached** — the run aborted
at pass 1 before a script existed. The 6,000-word floor in `voice.py` is untouched
and stays exactly where it is. No threshold, guard or trading code changed.

The money question is already open twice and is not re-asked here:
`20260929T041239-brainrot-radio-23984-23826` (filed 10:35:32Z today, "Fix needs a
money call — Kyle's") and `20260923T090904-cap-fallback-probe-legacy-91794-5312`
(OpenRouter overdrawn, still open). The balance moved: the limit was raised
$95 → $105 and the balance is still negative.
