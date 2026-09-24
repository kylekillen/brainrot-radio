### 2026-09-24 06:50 — 09-24 episode aired, but the Build-Pitch segment put Kyle's private system on air with a wrong count
The 09-24 episode (ep-2026-09-24-01, 16,456 words, 1:31:36) published at 11:02Z and is
the last item on the public feed. Verification by fetching the feed + HEAD of the
release asset; the check job logged OK at 05:15 and 05:45.

Line 87 of the script reads: "the fleet flipped its 'opus' alias to 5.5 yesterday.
When the build-pitch reporter checked, observer-system had twenty-seven places that
launch Claude with a model choice, only eight that pass an effort level, and the
dispatcher's worker runner passes none." Measured with `git grep` over
`scripts/ observer/ bin/` at commit 91dbb4d2 (the state before the 09-23 alias
flip): 48 `--model` occurrences, 9 `--effort`; run_task.sh passes no `--effort`.
The numbers on air were wrong AND the private setup should not have been public
(GUARDRAILS "Never include internal fleet state" row, 2026-06-28 — the Coherence
Skeptic never had a brief that mentioned it).

Fix in PR (branch `fix/kt-no-private-system-stats`): the pass-1 build-pitch prompt
now keeps the on-air explanation in general terms and forbids quoting the
listener's repos/roles/launchd/counts from the pitch file; the Coherence Skeptic
must treat private-system details and uncited private counts as MUST-FIX; a
GUARDRAILS row and a regression test lock it. Public correction to the feed item
via the new `correct_feed_description.py` once the PR merges.

Also today: AI Daily Brief transcript is stale show-notes and no Moonshots
transcript existed (see 102616 note); Ringer Fantasy + Barnwell transcripts came
through as 1-word files; Fantasy Footballers transcripts have no speaker labels
(103835 note). Build pitch 09-24: Opus 5.5 effort-default flip (two pitches, both
"measure first"; the 40%-cheaper and medium≥high claims are vendor-only).
