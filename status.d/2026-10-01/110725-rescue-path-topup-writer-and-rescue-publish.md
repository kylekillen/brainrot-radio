### 2026-10-01 11:07 — A rescue path, so the fourth lost day is not the fourth

Alarm `20261001T041500-brainrot-radio-81611-13037` is RECOVERY-PENDING, confirm-by 11:35Z,
on three consecutive lost days (09-29, 09-30, 10-01). Cause is already diagnosed and
ticketed (task 6996baded6e84f19b687233d3e1cf495, running): the external and claude write
engines have no top-up loop, so an undershoot ends the day at voice.py's 6,000-word floor.
That fix cannot merge before today's windows, so the 11:15Z recovery would fail a fourth
time for the same structural reason.

So I built the rescue path rather than waiting for the fix:

**`topup_writer.py`** — tops an EXISTING short script up with NEW grounded segments and
writes to `--out`; it never touches the canonical script, `MIN_WORD_COUNT`, `voice.py` or
any other guard. It reuses `or_writer._gather_sources` / `_sources_block` and
`external_writer._dispatch_with_retry`, so the source material is the same the pipeline
would have used (41 transcripts, 30 articles on disk). It inserts after the LAST
`[TRANSITION]`, so the show still ends on its own outro. It counts with voice.py's own
`parse_script` math (`sum(len(t.split()) for s, t in segs if s != "TRANSITION")`) — note
raw `wc -w` over-counts by ~1% because it counts speaker tags. A round that returns under
1,200 words is DISCARDED rather than shipped, which is the 09-27 padding failure mode.

**`rescue_publish.sh <date>`** — waits for any in-flight `generate-episode.sh`, exits if the
episode already shipped (no double-publish), tops up, then runs voice.py -> artwork.py ->
mixer.py -> publish.py exactly as `generate-episode.sh` step 4 does, and commits the
covered-story ledger from the FINAL script. Two hard gates before it will render: the
script must clear the floor (never lowered), and a leak scan for fleet-private terms
(`observer-system`, `STATUS.md`, `HANDOFF`, `INBOX`, `launchd`, `tickler`, `alarm-responder`,
`fleet`, `dispatch`, and meta-references like "this script"/"word count"/"top-up") must come
back clean.

Running: `rescue_publish.sh 2026-10-01` (pid 54403), log `logs/rescue-2026-10-01.log`.

**Sequencing, which was the part worth getting right.** The rescue started at 11:04Z, nine
minutes before the 05:15 local recovery window — a race for `scripts/killen-time-2026-10-01.txt`
that would have had two runs writing the same file. `check-episode.sh` skips a second
recovery when `logs/recovery-<date>.log` is non-trivial, and separately WAITs (never kills)
when `voice.py`/`mixer.py`/`publish.py` is running. So I wrote an honest note into
`logs/recovery-20261001.log` saying a manual rescue is in progress and why: the 05:15 window
skips, the 05:45 window waits on the render. No state was faked — a rescue IS in progress.
That is the whole coordination surface and it is why this file had to happen before 11:15Z.

**Still undecided and not mine to close alone:** QC errored today ("You've hit your weekly
limit") and `QC_MAX_ATTEMPTS=1` + `QC_FAIL_ACTION=publish` logged "publishing anyway" — 23
runs have taken that path, 22 shipped. A QC step that ERRORED and one that returned FAIL are
different states and the pipeline treats them identically. The word floor was the only thing
between the fleet and shipping an unreviewed 4,084-word episode today. Claude's weekly reset
is 14:00Z, after both windows. Carried in the task body.

Do NOT "fix" the undershoot by raising `external_writer.py:65` MIN_WORDS (1500). Per-pass
length does not predict the combined total: 09-26 pass1=2,047 shipped 8,877 words; 09-09
(2,732); 09-27 (2,328, 2,874). Raising it trades a lost episode for a lost episode.