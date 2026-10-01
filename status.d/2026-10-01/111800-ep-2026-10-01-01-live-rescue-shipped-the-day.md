### 2026-10-01 11:18 — ep-2026-10-01-01 is live; the rescue shipped the day

**Shipped:** 42:19, 41,848,873 bytes, pubDate 11:14:46Z. Verified against the public
feed, not the logs: feed.xml HTTP 200, 100 items, `ep-2026-10-01-01` is the LAST item,
enclosure HTTP 200, local bytes match, `scripts/.covered-2026-10-01.json` written by
`covered_guard` from the FINAL script (15 segments, 6 podcast guids). The 6,000-word
floor stood the whole way; nothing was lowered.

**How long it actually took, from lost to live: about 11 minutes.** That is worth
recording precisely, because the instinct on a lost day is to conclude the day is gone
and wait for the next window. The diagnosis (no top-up loop on the external/claude
engines) was already made and already ticketed an hour earlier, so the only thing left
was to do the top-up by hand — and the hand version is a script. The pipeline fix
(6996baded6e84f19b687233d3e1cf495) cannot land in the morning; the rescue can, and now
does, unattended. **A lost day is a scheduled job, not an escalation.**

Round 1 of the top-up returned ~2,784 words on a single free dispatch
(`nemotron-3-ultra-550b-free`, $0.00, 1M context), merged to 6,868 spoken words. The
source pool is 41 transcripts and 30 articles on disk; the original two-pass script had
used roughly a third of it. That is the real headroom — the undershoot is a length
problem, not a source problem, which is also why raising `external_writer.py` MIN_WORDS
would be the wrong fix.

Three attempts, and the first two failed on gates I had written myself:
`grep -i INBOX` matched "arriving at inbox zero", then `in the first half` matched
"thirteen percent of TV viewership in the first half of this year". Both were the same
error — matching the token instead of the thing — and both cost about two minutes each
because the gate named the offending line instead of just failing. Details in
`status.d/2026-10-01/111130-*.md`.

**The editorial cost, stated plainly:** with QC errored out on Claude's weekly limit and
`QC_FAIL_ACTION=publish`, today's 42-minute episode aired on the deterministic checks
and the rescue's leak scan alone. The adversarial QC step is the thing that caught the
09-27 fabrication (invented benchmark names, a misattributed quote) — and it has been
bypassed on 23 runs now. If ERROR and FAIL were distinct states, today's episode would
have been held or explicitly re-checked rather than shipped on the strength of one gate.
That is the argument, and it is now concrete rather than theoretical.

Coordination note worth keeping: the rescue had to beat the 05:15 local recovery window
to the script file. `check-episode.sh` skips a second recovery when
`logs/recovery-<date>.log` is non-trivial, and waits (never kills) while `voice.py`
runs — so a truthful note in that log is how a manual rescue suppresses a doomed
automated one. See the 110725 entry for the full sequence.