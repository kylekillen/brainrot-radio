### 2026-10-01 18:45 — An episode can be published, healthy on every surface, and silent

The 04:00 run on 10-01 lost the day: 4,084 speech words against a 6,000 floor,
`Voice render failed ... aborting`, exit 1. That part is well owned — PR #51
builds the top-up loop, and `rescue_publish.sh` shipped the day at 11:14.
This entry is about the part that was NOT owned, and it is not the word count.

**Nothing in this repo has ever asked whether the MP3 has audio in it.** Every
health surface asked the same weaker question — does the file exist:

- `check-episode.sh`: `if [ -f "$OUTPUT_FILE" ]; then log "OK: Episode
  published ($WORDS words)"` — and `$WORDS` came from `wc -w` on the **script**.
  A silent render reported a perfectly healthy word count off a file nobody
  listened to. It exited 0.
- `watch-episode.sh`: `[ -f .../killen-time-${TODAY}.mp3 ] && exit 0` — the
  watcher's entire stand-down condition was file existence.
- `generate-episode.sh`: mix returns, publish is called. mixer.py concatenates
  segments; a segment that rendered to an empty file still concatenates, and the
  result still gets uploaded.

So the failure mode the alarm dedupes as "already reported" — an exit code — was
the *only* instrument, and it cannot see a mix that succeeded. `SILENT` is not
`EXIT 1`. The run that produces one exits 0.

**Two corrections to the finding this came from**, both verified in the logs:

1. *The writer lanes did not all fail on 10-01.* The cascade in
   `logs/launchd-stderr.log` — external → Claude → OpenRouter/Kimi — is dated
   **09-29 and 09-30**. On 10-01 the external lane **succeeded**: one dispatch,
   04:03:05 → 04:14:49, 4,124 words. Nothing fell back. The day was lost because
   a lane that worked returned a script 1,916 words short, not because the
   fallbacks failed. That distinction matters for PR #51: it is already the right
   fix (repair the short script), and it is right for a different reason than
   stated.
2. *Nothing was published.* The run aborted at the render, before publish. So
   this was never "published with no audio" — it was a lost day, loudly, and the
   rescue fixed it. The silent-publish hole is real but is a **latent** one. It
   would have stayed invisible the first time mixer.py produced a zero-byte or
   truncated concat, which is why it is worth closing before it happens rather
   than after.

**What I built.** `audio_truth.py` — ffprobe for duration, ffmpeg `volumedetect`
for mean volume, and a pure `assess(size, duration, mean_db)` that holds the
thresholds and is testable without ffmpeg (CI is ubuntu-latest). Four verdicts,
each naming its own failure class because the remedies differ: `MISSING`,
`EMPTY` (frames absent), `TRUNCATED` (mix cut off), `SILENT` (inaudible),
plus `UNPROBEABLE` when ffprobe is missing — deliberately NOT reported as
"silent", since a tooling outage must not be read as a lost episode. Wired into
all three surfaces: the publish path aborts before `publish.py`, check-episode
exits 1 with a `FAIL:` line, and watch-episode falls through to its no-episode
alarm instead of standing down.

**Measured, not assumed.** Thresholds sit far from every real value, because a
false block here costs an episode — the same lesson as the leak gate that killed
a good episode twice on 10-01. All nine real episodes from 09-20 to 10-01 pass
with wide margin (36–89 MB / 2183–5496 s / −15.4 to −16.8 dB against floors of
1 MB / 600 s / −60 dB). Real broken files were synthesized and each is caught:
40 minutes of true digital silence → `SILENT` at −91.0 dB; 60 s of real audio →
`EMPTY`. `test_thresholds_sit_far_below_any_real_episode` fails if anyone tunes a
floor up into biting range.

**The gates are load-bearing, and I checked rather than claimed.** Reverting each
one out of the tree fails a specific test: watch-episode back to `[ -f mp3 ]` →
`test_watch_alarms_instead_of_standing_down_on_a_silent_mp3`; check-episode back
to unconditional OK → two failures; publish-path gate deleted → the mix test.
Full suite 103 passed. The one existing test that broke was
`test_watcher_is_quiet_once_the_episode_exists`, whose fixture is a 1-byte
stand-in MP3 — I stubbed the gate in that sandbox rather than weaken it, and the
gate's own behaviour is steered both ways in `test_audio_truth.py`.

**One thing I found by breaking it.** `check-episode.sh` hardcoded
`BRAINROT_DIR="/Users/kylekillen/brainrot-radio"`, so the first version of my
test suite appended its verdicts to Kyle's **live** `check-episode.log` and judged
the **live** `output/` directory. Two FAIL lines and one stray status file were
written; no audio was touched or deleted. `watch-episode.sh` was already
env-overridable and I followed that convention, plus a meta-test that asserts the
sandbox is sandboxed — without it, every other test in the file was quietly
testing Kyle's real show.

Kill switch: `AUDIO_TRUTH_CHECK=0` for a box whose ffmpeg is missing. The gate
does not delete a bad MP3 — it is the evidence, and its presence is what makes
`generate-episode.sh` stand down on a retry.