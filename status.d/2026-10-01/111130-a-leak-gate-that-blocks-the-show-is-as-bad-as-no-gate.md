### 2026-10-01 11:11 — A leak gate that blocks the show is as bad as no gate at all

Two aborts in four minutes during the 10-01 rescue, both false positives, both on a
6,868-word script that was otherwise ready to render:

1. `grep -aiE '...|INBOX|...'` matched **"arriving at inbox zero"** in a segment about
   a personal assistant clearing the user's mail. `-i` made the fleet's `INBOX.md`
   marker match the ordinary English noun.
2. The first seam pattern, `in the first half`, matched **"thirteen percent of overall
   TV viewership in the first half of this year"** — about Warner-Paramount, nothing
   to do with the script's own structure.

Both are the same mistake in two costumes: matching a marker *string* instead of
matching the *thing the marker stands for*. A leak is not the token `INBOX`, it is this
production's private ledger being discussed on air; a two-pass seam is not the phrase
"first half", it is the show referring to itself as half of a two-part episode. Judging
"in the first half" in isolation cannot tell those apart. "Out of this half" in an outro
can.

The gates now run in three tiers, and only two of them can stop a show:

- **HARD, case-sensitive, blocks**: `observer-system`, `STATUS.md`, `HANDOFF`,
  `INBOX.md`, `launchd`, `tickler`, `alarm-responder`, `observerctl`, `task-worker`,
  `status.d`. Case-sensitivity is the point — these appear on air in a specific case,
  and the one case-insensitive pattern that mattered cost an episode.
- **SOFT, case-insensitive, logs and continues**: `fleet`, `dispatch*`, `this script`,
  `word count`, `top-up`. These are sometimes a leak and frequently ordinary English
  about agents. Loud in the log; a human decides.
- **SEAM, narrow, blocks**: only self-reference — `out of this half`, `in this first
  half`, `this second half`, `first/second half of the (show|episode)`.

Also fixed: the outro genuinely said "The thread worth carrying **out of this half**" —
the real defect the gate was built for, and the same seam flagged on the 09-27 episode.
Rewritten to "out of today's show" before render.

Two smaller things worth keeping. `topup_writer.py` now writes `--out` even when the
script is already at target, because `rescue_publish.sh` installs `--out`
unconditionally and an early `return 0` left it depending on a stale `/tmp` file — the
second run would have shipped whatever was left over. And never edit a shell script
that is executing: bash reads scripts incrementally by byte offset, so an in-place edit
mid-run can execute garbage. I got lucky; the honest rule is kill-and-relaunch.

The meta-lesson, and the one to carry: **a gate that is not precise enough will, sooner
or later, block the thing it was built to protect.** That is a false loss, and it is
indistinguishable from a real one unless the failure is loud. Both of these said
`RESCUE FAILED` and named the line — which is why they cost four minutes and not an
episode.