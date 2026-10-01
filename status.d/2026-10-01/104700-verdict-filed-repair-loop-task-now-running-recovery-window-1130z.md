### 2026-10-01 10:55 — Alarm 20261001T041500 re-dispatched; the repair loop is no longer just ticketed, a worker is on it

The 10:35 note (`103500-external-writer-undershot-4th-time-three-lane-diagnosis-stale.md`,
commit `6e2bce9`) investigated this alarm but the verdict file was never written, so the
alarm came back at 10:49Z. Nothing about the diagnosis changed. This note carries only
what is new: independent re-verification, the fix task's live state, and the exact
recovery clock.

**Re-verified from scratch, not inherited.** Ran `voice.py`'s own `parse_script()`
against `scripts/killen-time-2026-10-01.txt`: 40 segments, 33 speech, **4,084 words**
— matches the alarm's number exactly. `voice.py:218` refuses below `MIN_WORD_COUNT`,
which is still `6000` at `config.py:55`. The guard is correct and untouched.

**Counts taken over whole files, not tails** (`grep -l` across all 259
`logs/generate-2026*.log`, because a tail understates every one of these): `SCRIPT TOO
SHORT` in **13** files; `external_writer: pass 1 wrote` in **21**; intersection — free-lane
runs that wrote a script and then died at the floor — **7** (09-20, 09-22, 09-25 ×2,
09-27 ×2, 10-01). `publishing anyway` (the QC-fail path) in **23**.
`output/killen-time-2026-09-28.mp3` is still the newest audio: three consecutive lost
days, 09-29 / 09-30 / 10-01.

**The fix is being built right now, not queued.** Task
`6996baded6e84f19b687233d3e1cf495` ("give the external and claude writer engines the
top-up loop Gemini already has") was claimed at **10:26:29Z** and is `status: running`,
worker PID 41092, `space-bunny-free`. At 10:35 it was `ready`. So the gap is owned and in
flight; do not re-file it. It cannot merge before today's recovery windows, so today's
run still re-rolls the dice.

**The recovery clock, read off the plists rather than assumed.**
`~/Library/LaunchAgents/com.mojo.brainrot-check.plist` runs `check-episode.sh` at
**05:15 and 05:45 local** — `11:15Z` and `11:45Z` — with `QC_MAX_ATTEMPTS=1`. Its
verdict lands in `logs/check-episode.log` (`OK: Episode published (N words)` vs
`FAIL: No episode for 2026-10-01 and nothing running`), and the run it fires writes to
`logs/recovery-20261001.log`, which does not exist yet. Prior recoveries took ~12
minutes, so the first confirmable observation is ~11:30Z. That is why this alarm is
RECOVERY-PENDING and not FIXED: every piece of evidence about recovery is still in the
future.

**One thing worth Kyle's attention, carried in the task body and not blocking this
alarm.** Today QC never ran — it printed `You've hit your weekly limit` and exited 1 —
yet `QC_MAX_ATTEMPTS=1` plus `QC_FAIL_ACTION=publish` logged `publishing anyway`. The
word floor was the only thing between the fleet and shipping a 4,084-word episode that
no skeptic ever read, and 22 of those 23 QC-fail runs shipped. A QC step that ERRORED
and one that ran and returned FAIL are different states and the pipeline treats them
identically. That is a fail-open call, not a threshold I should change unattended.

**Nothing changed in this repo by this pass.** No code, no thresholds, no daemon
restart needed. `main` is in sync with `origin/main` at `6e2bce9`.