### 2026-09-29 04:32 — All three writer lanes died in the same 12 minutes; the 402 is the last body, not the disease

Run `20260929-040004` shipped no episode. The alarm names the last failure
(`or_writer ... HTTP Error 402: Payment Required`), but that is the THIRD
writer lane to die, not the cause. Full chain, from `logs/generate-20260929-040004.log`:

1. `~/.observer/pause-flags/podcast.pause` stands (burn_monitor, 95% of the 7d
   Max allowance, 2026-09-28T18:14:45). The run was therefore BURN-DEGRADED:
   writes routed to the EXTERNAL free lane, `nemotron-3-ultra-550b-free` via
   `external_summon`, not the normal Claude path.
2. External free lane 429s twice (attempt + retry):
   `Rate limit exceeded: free-models-per-day-high-balance`,
   `X-RateLimit-Limit: 1000`, `X-RateLimit-Remaining: 0`,
   `limit_source: openrouter_free_tier_daily`,
   `X-RateLimit-Reset: 1790726400000` = **2026-09-30T00:00:00Z**.
3. Falls back to Claude (`write-pass1`, then `write-pass1-retry`): both print
   `You've hit your weekly limit · resets Oct 1 at 8am (America/Denver)`.
4. Falls back to OpenRouter via `or_writer.py` → 402 at all three max_tokens
   budgets (16000/8000/4000). 402 is an account-credit condition.

Two things worth recording that the log does not state:

- **`free-models-per-day-high-balance` is an ACCOUNT-level daily bucket, not a
  per-model one.** The metadata carries `limit_source: openrouter_free_tier_daily`
  with a flat 1000/day and `Remaining: 0`. So swapping `external_writer.py`'s
  `DEFAULT_MODEL` from `nemotron-3-ultra-550b-free` to a different `:free` slug
  on the same key would hit the SAME exhausted bucket and change nothing. The
  09-08 "rotate the free model" fix does not apply to this failure mode. That
  makes the `⚠️ Fix the free lane (external_writer.py DEFAULT_MODEL) before
  tomorrow's run` line the pipeline prints at 04:12:01 actively misleading here.
- **The balance moved since the 09-23 escalation.** That row recorded
  "overdrawn at -$0.18 of $95". Today's footer reads `OpenRouter: $-0.20 of $105
  remaining` — the limit was raised $95 → $105, and the balance is still
  negative. Same condition, current figures, now with an episode actually lost.

Timing, because it decides whether a re-run helps: the free-tier bucket resets
2026-09-30T00:00:00Z = **18:00 MDT today**. `com.mojo.brainrot-check` fires at
05:15 and 05:45 MDT — both BEFORE the reset, so both recovery attempts today
will fail identically. The 402 is unaffected by any of this (still overdrawn)
and the Claude weekly lane is dead until Oct 1.

Local `$0` capacity does exist and is genuinely up (ollama serving
`muse-glimmer:30b-mlx`, `qwen3.6:35b-a3b`, `retired-qwen3-30b-a3b`), but wiring a
30B local model into the writer path is a pipeline design change, not a
threshold fix, and on the 09-25/09-27 precedent those engines undershoot the
render word floor badly. Flagged, not attempted.

No code changed. No threshold touched — in particular the 6,000-word render
floor in `voice.py` was never reached and stays exactly where it is.
