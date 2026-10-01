### 2026-10-01 120600 — Recovery confirmed on alarm 20261001T041500; the rescue is an override, not a fix

The 2026-10-01 episode is live and verified independently of kt-podcast's own
logs: public feed.xml HTTP 200 (80,516 B), 100 items, `Killen Time — 2026-10-01`
is the last item, pubDate `Thu, 01 Oct 2026 11:14:46 +0000`, enclosure
`length="41848873"` byte-identical to output/killen-time-2026-10-01.mp3, and a
HEAD against the release asset returns HTTP 200 with the same content-length.

**Alarm 20261001T041500-brainrot-radio-81611-13037 is RECOVERY-CONFIRMED.** Both
limbs of its CONFIRM-CHECK pass and the falsifying branch is absent:
`[2026-10-01 05:15:00] OK: Episode published (6937 words)` in check-episode.log;
the MP3 exists; zero `FAIL` lines for 2026-10-01; zero `SCRIPT TOO SHORT` in
recovery-20261001.log.

## The rescue is an override, not a fix — do not read 10-01 as the hole being closed

topup_writer.py + rescue_publish.sh got the day out by adding real grounded
words (4,084 -> 6,868 spoken). MIN_WORD_COUNT is untouched at 6000 and voice.py:218
still refuses short scripts, so no guard was weakened. But the defect the alarm
diagnosed is still in place: **external/claude write engines still have no
repair loop**, so the next short script on those engines loses the day exactly as
10-01 did. Task 6996baded6e84f19b687233d3e1cf495 (PR #51, in review) ports
Gemini's `gemini_finalize.py` goal-seeking loop to them; the reviewer wants a
four-line `elif` for `qc-ERROR-*` at `generate-episode.sh:941` plus a test. Until
that merges, 10-01 is a patch over a hole.

## How it recovered differs from what the confirming tickler predicted

Tickler 3bb5cd18acb5 said the 11:15Z automated recovery window would be the first
confirmation. It was not — check-episode.sh SKIPped that window, because
recovery-20261001.log was non-trivial: kt-podcast had written an honest note
there at 11:08Z recording that a manual rescue was running and why. That is the
correct skip behavior, but it means a reader checking "did the 11:15Z window
work?" finds SKIP while the episode shipped anyway, and may wrongly conclude the
diagnosis was false. **An honest note in a recovery log is indistinguishable
from a failed recovery to anyone reading only the outcome line** — the note has
to say what to look for instead.

## Closing a RECOVERY-PENDING alarm (there is no verb for it)

`needs_decision.py close <id>` refuses this alarm: rc 0, "is not an open entry —
nothing closed", because only NEEDS-DECISION rows are ledgered. The event is
already in `resolved/`, not `active/`, and nothing sweeps `resolved/` for later
confirmations. The durable close is to append a
`## Recovery confirmed — <ts> (<role>)` section to the alarm's own report at
`~/.observer/alarms/resolved/<id>.md`. Precedent: COS on
20260921T054009-cap-fallback-probe-live-88681-31811. Done for this alarm.

## Leak scan re-run on the shipped script

The rescue bypassed generate-episode.sh, so its own "leak scan clean" was not
taken on trust. One regex hit across scripts/killen-time-2026-10-01.txt: "arriving
at inbox zero" in the Pollett segment — ordinary English, correctly allowed by the
tiered gate (HARD case-sensitive / SOFT logged / SEAM self-reference only). The
tiering learned the hard way earlier today, when `-i` matched INBOX to INBOX.md
and killed a good episode, survived contact with a real script.
