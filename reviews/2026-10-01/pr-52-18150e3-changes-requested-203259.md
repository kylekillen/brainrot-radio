### 2026-10-01 20:32 — PR #52 review: changes requested

Reviewed on space-bunny-free
Reviewed head: `18150e319fa274de71e70cce4a0b3625e002e1ff`.

Decision: changes requested. The gate itself is well built — the thresholds are
measured, the verdict classes are distinct, and the mutation checks in the PR
body are real. Two defects block, both small.

- **Correctness: fails**, on two counts.
  1. `check-episode.sh:31` — the healthy path no longer runs
     `bin/verify-pitches.py`. On `origin/main` that call (now
     `check-episode.sh:41`) sat *above* `exit 0`, so it ran on every successful
     check. This diff moved `exit 0` inside the OK branch, which strands the
     verify-pitches line: the non-fatal build-pitch verdict status is now
     recorded only when the episode FAILS. Reproduced in a sandbox — healthy
     episode, `audio_truth.py` stubbed to return OK: exit 0, log holds only the
     `OK:` line, verify-pitches never invoked. Nothing parses verify-pitches
     programmatically (its output goes to `check-episode.log` for a human), so
     the blast radius is one diagnostic — but it is an unannounced behaviour
     change on the common path, and it is not part of the audio gate.
     Smallest fix: keep the `if`/`else`, set a status variable in each arm, let
     both fall through to the shared `python3 .../bin/verify-pitches.py` line,
     then `exit "$rc"`.
  2. `audio_truth.py:128` — the documented kill switch does not work on any
     surface this PR wires up. `main()` calls `probe()`, not `probe_ok()`, and
     every caller invokes the CLI (`check-episode.sh:29`, `watch-episode.sh:34`,
     the `generate-episode.sh` gate). `probe_ok()` (`audio_truth.py:117-121`) has
     no production caller anywhere in the repo — grep finds only its own test.
     Reproduced: `AUDIO_TRUTH_CHECK=0 python3 audio_truth.py /tmp/nope.mp3`
     prints `audio-truth: MISSING` and exits 1, while the same env var makes
     `probe_ok()` return `True`. So the one advertised remedy for "a box whose
     ffmpeg is missing" — precisely the case where the gate fails closed
     (UNPROBEABLE → exit 1 → `generate-episode.sh` refuses to publish,
     `check-episode.sh` exits 1, `watch-episode.sh` alarms) — is a no-op. The
     claim is made in the PR body's Notes, at `audio_truth.py:28`, and at
     `status.d/2026-10-01/184500-a-published-episode-that-is-silent.md:80`.
     Smallest fix: honour the switch in `main()` (three lines, mirroring
     `probe_ok`), or drop the claim from all three places.
- **Coherence: fails** on dead code, otherwise consistent. `FFPROBE =
  "/opt/homebrew/bin/ffprobe"` matches the existing convention (`publish.py:18`,
  `render_report.py:46`, `publish_private.py:43`), and making `check-episode.sh`'s
  `BRAINROT_DIR`/`CHECK_TODAY` env-overridable follows `watch-episode.sh`. The
  MISSING/EMPTY/TRUNCATED/SILENT/UNPROBEABLE split is the right call, and the
  `test_run_guard.py` stub is a fair, documented accommodation rather than a
  weakened guard. Dead bits to sweep: `audio_truth.py:36` imports
  `MIN_WORD_COUNT` and never uses it (only the comment at line 40 mentions it),
  and `tests/test_audio_truth.py:20` imports `pytest` unused.
- **Smallness: fails** on finding 1 — the only unrelated behaviour change in the
  diff. Otherwise the change is scoped to the stated hole, with no dependency or
  formatting churn. `tests/test_audio_truth.py:220` (`tmp = os.path.dirname(ROOT)
  + "/__probe"`) is a dead assignment.
- **Hosted CI:** green on the reviewed head — `pytest`, 2 completed successful
  check-runs, both on `18150e31`. `merge_gate_check.py --head 18150e31...`
  reports the CI lane clear, no protected paths touched, red-team lane not
  applicable, and the PR carries no existing comments or reviews. Local:
  `tests/test_audio_truth.py` + `tests/test_run_guard.py` = 30 passed. The local
  full suite cannot collect unrelated modules under the system Python 3.9
  (no `feedgen`; 3.10 union syntax elsewhere), so hosted CI stays the
  authoritative gate.
