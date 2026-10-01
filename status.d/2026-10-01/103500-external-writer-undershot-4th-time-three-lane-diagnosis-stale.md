### 2026-10-01 10:35 — Alarm response: free writer undershot to 4,084 words, floor blocked it; the 09-29/30 "three lanes dead" diagnosis is now STALE, and the real gap is a repair loop that has been asked for since 09-25

Alarm `20261001T041500-brainrot-radio-81611-13037` (run `20261001-040002`,
exit 1, no episode). Verdict: RECOVERY-PENDING, CONFIRM-BY 12:15Z. Fix
enqueued as task `6996baded6e84f19b687233d3e1cf495`.

**The guard is not the bug and was not touched.** `voice.py:218`
(`if word_count < MIN_WORD_COUNT:`) refused a 4,084-word script against the
6,000 floor (`config.py:55`), printed the shortfall, and exited 1. Correct
behaviour. `MIN_WORD_COUNT` stays exactly where it is.

**What actually wrote the episode.** `~/.observer/pause-flags/podcast.pause`
still stands (burn_monitor, 2026-09-28T18:14:45Z), so `generate-episode.sh:22-24`
forced `PODCAST_ENGINE=external` and both passes went to
`nemotron-3-ultra-550b-free`. From `logs/generate-20261001-040002.log`:

```
external_writer: pass 1 wrote 1920 words to scripts/killen-time-2026-10-01.txt
external_writer: pass 2 wrote 2204 words to scripts/killen-time-2026-10-01.txt
[2026-10-01 04:14:49] Combined script: 4124 words
Parsed 40 segments (33 speech, ~4084 words)
```

1,920 + 2,204 against a prompt asking 7,000–9,000 per half
(`or_writer.py:220,271`). Verified independently with `voice.py`'s own
`parse_script()`, not `wc -w`: **4,084** speech words, 33 speech segments,
shortfall 1,916.

**Two corrections to the standing diagnosis.**

1. **The 09-29/09-30 three-lane outage is over, and re-running it would be
   wrong.** `status.d/2026-09-29/103200-*` and `status.d/2026-09-30/113500-*`
   blamed all three lanes dying together (free bucket 429 /
   `free-models-per-day-high-balance`, Claude weekly cap, offload 402). Today
   the free lane dispatched **twice, both OK** (`write-pass1 dispatch OK`,
   `write-pass2 dispatch OK`). The OpenRouter free daily bucket reset was
   `2026-10-01T00:00:00Z`, in the PAST relative to this 10:00Z run — the race
   those notes measured did not recur. `git log --since="2026-10-01T10:15:00Z"`
   is empty: nothing changed on `main` between the diagnosis and now. Today's
   loss is a short script, not an outage.
2. **QC never ran, and the floor is the only reason an unreviewed episode did
   not ship.** The QC step printed `You've hit your weekly limit · resets 8am
   (America/Denver)` and errored. `QC_MAX_ATTEMPTS=1` — set in both
   `~/Library/LaunchAgents/com.mojo.brainrot-radio.plist` and
   `com.mojo.brainrot-check.plist` — produced `QC_VERDICT: none`, and
   `QC_FAIL_ACTION=publish` (`generate-episode.sh:633`) logged `publishing
   anyway`. **A 4,084-word episode that no skeptic ever read was one floor
   check away from going out.** Counted, not tailed: 23 runs across all logs
   have taken the QC-fail-then-publish-anyway path, and 22 of them shipped. A
   QC step that *errored* is not the same state as one that ran and returned
   FAIL, and the pipeline treats them identically. Claude's weekly reset is
   `1790863200` = **2026-10-01T14:00:00Z**, after both recovery windows (11:15Z
   / 11:45Z), so QC is unavailable for both today.

**Counted over whole files** — `grep -l` across all 259 `logs/generate-2026*.log`,
because a tail would have understated all of this. `SCRIPT TOO SHORT` appears
in **13** files; `external_writer: pass 1 wrote` in **21**; the intersection —
free-lane runs that produced a script and *then* died at the floor — is **7**:
09-20, 09-22, 09-25 ×2, 09-27 ×2, 10-01. Roughly a third of free-lane runs
end here. `output/*.mp3` was last written **2026-09-28 04:26**: three
consecutive lost days.

**The structural gap, fourth occurrence.** `generate-episode.sh` gives the
**Gemini** engine a goal-seeking repair loop (`generate-episode.sh:651` →
`gemini_finalize.py`): verify against `MIN_WORD_COUNT`, repair
constructively while unmet, re-verify, bounded, then escalate. The
**external and claude** engines have none — write once, QC once, render, floor
aborts. Logged and left open four times: `status.d/2026-09-25/173500-*`
("no top-up loop for a QC-shortened script (Gemini engine has one; claude/
external do not)"), `status.d/2026-09-27/042755-*`, `2026-09-27/113800-*`,
`2026-09-27/123334-*` — the last of which says it is "worth turning into an
actual engineering decision/ticket rather than a fourth status.d note." Six
days on, it is neither built nor ticketed. It is now task
`6996baded6e84f19b687233d3e1cf495`.

**The tempting threshold fix is unsafe, and I checked rather than assumed.**
`external_writer.py:65` has `MIN_WORDS = 1500`, which looks like the loose
guard that let a 1,920-word pass 1 through. Per-pass length does not predict
the combined total, because pass 2 supplies the rest. Runs with pass 1 under
3,000 that produced aired episodes: **09-26** (pass1=2,047 → 8,877 speech
words), **09-09** (2,732), **09-27** (2,328 and 2,874). Raising that floor
would trade a lost episode for a lost episode. Recorded in the task body so
whoever picks it up does not rediscover it the expensive way.

**What did not change.** No threshold, guard, retry, provider or episode logic
touched. `voice.py`, `config.py`, `external_writer.py` and `generate-episode.sh`
on `main` are byte-unchanged by this investigation; no daemon restart needed.

**Recovery, honestly stated.** The 05:15 MDT (11:15Z) recovery run is the
earliest thing that can confirm or falsify this, and it has not fired yet — so
this is not FIXED, only pending. Its odds are genuinely unknown: the same
free lane produced 8,911 combined words on the 09-25 05:15 recovery (cleared
after a manual top-up) and 4,462 on 09-27's (died at 2,627 after QC). Unused
source material exists for a real top-up if one is needed — 34 transcripts
>2KB and 30 articles >2KB still in `.tmp/`.