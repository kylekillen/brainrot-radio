### 2026-09-30 10:35 — The 402 in every log line is Google's, not OpenRouter: the offload lane is generativelanguage.googleapis.com with depleted prepay credits

Alarm `20260930T041449-brainrot-radio-94750-552` (run `20260930-040001`, no
episode) names `or_writer: OpenRouter completion failed at all budgets: HTTP
Error 402: Payment Required`. **That provider attribution is false, and it is
the one new fact in this run.** The 402 is Google AI Studio.

Measured, not inferred — the configured route, then a live probe of it:

```
python3 -c "import or_complete; print(or_complete._config()[0], or_complete._config()[2])"
  -> https://generativelanguage.googleapis.com/v1beta/openai   gemini-flash-latest
or_complete.complete("Reply with the single word: ok", model, max_tokens=8)
  -> HTTP 402 on host generativelanguage.googleapis.com
     {"error":{"code":402,"message":"Your prepayment credits are depleted. Please
       go to AI Studio at https://ai.studio/projects to manage your project and
       billing...","status":"RESOURCE_EXHAUSTED"}}
```

`OFFLOAD_BASE_URL` and `OFFLOAD_MODEL` are both set in
`~/.config/personal-os/offload.env`, so `or_complete.DEFAULT_BASE` and the
legacy `openrouter.env` branch never fire. The string "OpenRouter" reaches the
log only because `or_writer.py` hard-codes it in two stderr lines while the
provider is, by that module's own design, a config choice. The offload lane has
been mislabelled since it was pointed away from OpenRouter, and the two
needs-decision rows filed for 09-23 and 09-29 both name OpenRouter as the
account to fund.

**Consequence for the money call:** topping up OpenRouter would not restore the
fallback. `~/.observer/data/lane-availability.json` (generated
2026-09-30T10:10:39Z) carries both, separately — `google` = quota-exhausted
(prepaid) and `openrouter` = quota-exhausted, `remaining` −$0.196 of $105. Two
accounts; the decision is top up both, or repoint `OFFLOAD_BASE_URL` back and top
up one. Neither is a responder's move.

### All three writer lanes were already dead before the run started

| # | Lane | Body in `generate-20260930-040001.log` | Real state, measured 10:10–10:25Z |
|---|---|---|---|
| 1 | external free `nemotron-3-ultra-550b-free` | 429 `free-models-per-day-high-balance` ×2 | `limit_source: openrouter_free_tier_daily`, limit 1000/day, `Remaining: 0`, reset `1790812800000` = **2026-10-01T00:00:00Z** |
| 2 | Claude (`write-pass1`, `-retry`) | `You've hit your weekly limit · resets Oct 1 at 8am (America/Denver)` | `weekly_pct: 1.0`, `weekly_reset: 1790863200` = **2026-10-01T14:00:00Z** |
| 3 | offload (`or_writer.py`) | 402 at max_tokens 16000/8000/4000 | **Google AI Studio prepay depleted** (body above) |

`~/.observer/pause-flags/podcast.pause` still stands (burn_monitor, 95%, raised
2026-09-28T18:14:45Z), so the run was BURN-DEGRADED and wrote on the free lane by
Kyle's 2026-09-08 ruling. That degrade remains correct: Claude was at
`weekly_pct: 1.0` regardless, so a skip would have lost the same episode. The
bucket that the free lane drew on was empty **10 hours into the UTC day** — the
show's 04:00 MDT slot is 10:00Z — so the midnight reset never helps it, the same
race the 09-29 11:35 note measured.

### Currency check, counted not tailed

`grep -c` over every `logs/generate-*.log`: `HTTP Error 402` in **5** files
(09-23 ×2, 09-29 ×2, 09-30); `You've hit your weekly limit` in **13**;
`free-models-per-day` in **3**. No episode shipped 09-23, 09-29 or 09-30 — five
lost runs, one condition. The diagnosis is already in this repo
(`status.d/2026-09-29/103200-…`, `…/113545-…`), and so is the reporting fix for
the two lying log lines: **PR #47** (opened 2026-09-30T00:41:19Z) and its guard
follow-up **PR #48** (01:12:54Z), both open, both awaiting an independent
reviewer. The only new work in this dispatch is the provider correction above,
posted as a comment on #47.

### What did not change

No threshold, guard, retry or episode logic touched. The 6,000-word render floor
in `voice.py` was never reached — the run aborted at pass 1, before a script
existed — and stays exactly where it is. `generate-episode.sh` and `or_writer.py`
on `main` are byte-unchanged; no daemon restart is needed.

**Still true after the correction, and worth not re-deciding tonight:** the only
remedies left are a money call (fund Google AI Studio prepay, and/or OpenRouter)
or a design call (point the writer at a lane measured alive — `groq`, `local`,
`mistral`, `opencode` are the only ones — with the 09-28 New Hire single-pass
result as the quality warning: local `muse-glimmer:30b-mlx` produced 1,648 spoken
words against the 2-pass control's 9,596 and failed QC). Wiring one in is a
pipeline change, not a threshold fix.
