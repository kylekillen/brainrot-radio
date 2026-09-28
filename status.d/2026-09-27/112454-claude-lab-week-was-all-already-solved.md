### 2026-09-27 05:24 — This week's 3 leading claude_lab pitches all turned out to be already-solved-elsewhere, in more robust form

Verified against the fleet's actual state (not just against "does Kyle already do a
version of this"): Cole Medin's rate-limit multi-model-mixing video is superseded by
`external-model-routing.md`'s RIGOR-TIER/free-lane system *and* this repo's own
`gemini_episode.py`/`or_writer.py`/`router_writer.py`; IndyDevDan's self-compact-pi-agent
is superseded by `observer-system/scripts/role-hooks`' PreCompact→HANDOFF.md pattern,
which has already survived and patched a real Claude Code CLI regression
(`test_checkpoint_compaction_handoff.py`, 2026-09-19); Cole Medin's "mine your past
sessions to improve CLAUDE.md" is superseded by the `claudeception` skill +
observer-system's whole premise. Worth outliving the session because it's a repeatable
verification pattern for this beat: before treating a claude_lab video as a build gap,
grep for the mechanism by its *problem*, not just its name — all three looked novel
until traced to an existing fix built under incident pressure (credit crunch, a live
CLI bug) rather than in response to a trend video.
