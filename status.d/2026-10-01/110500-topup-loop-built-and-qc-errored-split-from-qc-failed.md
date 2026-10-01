### 2026-10-01 11:05 — The top-up loop is BUILT for the external/claude engines, and "QC errored" is finally a different state from "QC ran and said FAIL"

Closes the gap logged four times since 09-25 (`status.d/2026-09-25/173500-*`,
`2026-09-27/042755-*`, `113800-*`, `123334-*`) and the fourth occurrence logged this
morning (`2026-10-01/103500-*`). Task `6996baded6e84f19b687233d3e1cf495`.

**What was missing.** `generate-episode.sh` gave the Gemini engine a goal-seeking
loop — verify against `MIN_WORD_COUNT`, repair while unmet, re-verify, bounded, then
escalate (`generate-episode.sh:651` → `gemini_finalize.py`). The external and claude
engines had none: write once, QC once, render, and if the script came out under
voice.py's floor the run aborted and the day was lost.

**What shipped.**

1. `topup_writer.py` — the same loop for the other two engines. It measures with
   `voice.parse_script()` (**not** `wc -w`, which overcounts the speaker tags by ~70-100
   and is how a 5,968-word script looked like it had cleared a 6,000 floor — see
   `2026-09-27/121042-*`), and while short dispatches an expansion pass told the exact
   shortfall, fed sources today's write passes never inlined (`.tmp/transcripts` /
   `.tmp/articles` beyond or_writer's 16/6 cap — 10 transcripts + 5 articles were
   available on 10-01), appended on exactly one `[TRANSITION]`. Reused, not reinvented:
   `or_writer._gather_sources()` / `_sources_block` / `SYSTEM`, and
   `external_writer._dispatch_with_retry`, so the external engine stays $0. Bounded by
   `TOPUP_MAX_ATTEMPTS` (default 2); on exhaustion it writes
   `logs/topup-FAIL-<RUN_ID>.flag`, logs loudly, and exits non-zero — the same fail-loud
   outcome as today, but after actually trying to repair. Anti-shrink: a "repair" that
   comes back shorter is discarded (the 06-21 Gemini outage was exactly that).
2. Wired in at **two** points: after the two write passes (so QC also reviews the
   top-up material) and again **after QC** — because QC's own fixes cut scripts, which is
   how 09-25 died at 4,948 words with a writer that had produced enough. `TOPUP_ENABLED=0`
   is the kill-switch. A script already over the floor spends nothing.
3. **QC errored ≠ QC failed.** Previously both collapsed to `QC_VERDICT: none` and
   `QC_FAIL_ACTION=publish` logged "publishing anyway". Now `QC_RAN` tracks whether any
   attempt actually produced a verdict; if none did, the gate takes a separate branch with
   its own flag file (`logs/qc-ERROR-<RUN_ID>.flag` vs `qc-FAIL-…`), its own log line
   ("QC NEVER RAN … UNREVIEWED") and its own knob `QC_ERROR_ACTION`.
4. **Both states reach the fleet signal stream.** Code review caught that splitting the
   flag file left the post-publish signals block emitting only for `qc-FAIL-*`, so the new
   unreviewed ship was *quieter* than the reviewed-and-rejected ship it replaced — the
   opposite of the point of the split. `qc-ERROR-*` now emits its own signal under its own
   category (`flag`, not `gap`), and a test runs the real signals block for both names so
   they cannot drift apart again.

**Not changed, on purpose.** `config.MIN_WORD_COUNT` (6,000) and
`external_writer.MIN_WORDS` (1,500) are both untouched. The per-pass floor looks like the
loose guard that let 1,920 through, but per-pass length does not predict the combined
total — 09-26 (pass1=2,047 → 8,877 speech words), 09-09 (2,732) and 09-27 (2,328 /
2,874) all aired from a short pass 1. Raising it trades a lost episode for a lost episode.

**Open decision for Kyle.** `QC_ERROR_ACTION` defaults to `publish` — today's behaviour,
so nothing changes overnight, but the state is now visible and separately controllable.
Whether an episode that **no skeptic ever read** should ship at all is a policy call, not
a bug fix; flipping it is `QC_ERROR_ACTION=abort` in
`~/Library/LaunchAgents/com.mojo.brainrot-radio.plist`. Today's context for that call: the
render floor was the only thing between the fleet and an unreviewed 4,084-word episode,
and 23 runs have taken the QC-fail-then-publish-anyway path (22 shipped).

**Verified.** 22 new tests (`tests/test_topup_loop.py`, `tests/test_topup_shell.py`) —
the loop's measure/anti-shrink/unused-sources/boundedness properties, and the real
`run_topup_loop` function and QC gate extracted out of `generate-episode.sh` and run
under bash. Full suite 135 passed. Replayed against the real 10-01 script (4,084 words):
the loop offers 10 transcripts + 5 articles, names the 1,916-word shortfall, and clears
the floor. Nothing was dispatched live; no daemon touched.