# Beat: Claude Lab / Build-Pitch Reporter (NEW 2026-06-11)

A separate, dedicated reporter (`claude_lab` beat) that runs as its own pipeline
step **before** the script passes (`generate-episode.sh` Step 1.5). Its verified
output is folded into the show by the Agents & Building beat as the "Build-Pitch
of the Day" — see `agents-building.md`.

It scans recent YouTube transcripts from Claude-technique channels (IndyDevDan,
Cole Medin, AI Jason, GosuCoder, Matthew Berman, Anthropic — see `feeds.json`
topic `claude_lab`) plus keyword searches, looking for concrete technique on
Claude prompting/harness design, running agents, system upgrades, and
optimization.

## Discipline — the whole point, do NOT skip
- **Research and verify before reporting.** For anything interesting, cross-check
  it against other sources trying the same/similar thing, confirm there's real
  evidence it works (not a demo or hype), and judge whether it's genuinely
  novel/meaningful versus something Kyle already does. Discard the rest.
- **Quality over quantity** — one well-verified pitch beats three thin ones. If
  nothing clears the bar, say so honestly; never fabricate a pitch.
- Kyle's existing stack (don't pitch what he already runs): observer-system, the
  COS, the dispatcher / PR-reviewer loop, this podcast pipeline, a multi-agent
  delegation setup. Check `~/.observer/wiki` and `~/observer-system/CLAUDE.md`
  if unsure.

## The payoff loop
A verified technique gets pitched on the show as the "Build-Pitch of the Day,"
with the full write-up (technique, sources, evidence, stack-fit, build sketch)
saved to `build-pitches/YYYY-MM-DD.md`. Kyle hears it and, if he likes it, points
an agent at the episode or that file and says "build this." **Treat every pitch
as something an agent could pick up and implement with no further context** —
because that's exactly what's supposed to happen.

## Output files
- `build-pitches/YYYY-MM-DD.md` — durable record. Per pitch: **Technique**,
  **Who's doing it** (titles + URLs + corroborating links), **Evidence it's
  real**, **Why it matters for us** (maps onto Kyle's stack), **Build sketch**,
  **Status: pitched**. If nothing survived, write a short "No verified pitch
  today" note.
- `.tmp/build-pitches.md` — tight 200-400 word summary the episode writer folds
  in. Lead with the single best pitch. End with "Logged in
  build-pitches/YYYY-MM-DD.md for Kyle to greenlight." If no verified pitch,
  write exactly `NO_VERIFIED_PITCH` on the first line + a one-sentence reason.

## Gotchas
- `youtube.py` truncates transcripts to 2000 chars (TRANSCRIPT_MAX_CHARS) and
  skips channels with no channel_id — that truncation is why this is a dedicated
  agent step that pulls FULL transcripts via the yt-search skill / yt-dlp rather
  than the ingest path. The `youtube.py --hours 168 --json` snippet is only a
  triage signal.
- `youtube.py --channel` filters by source id (e.g. `cole_medin_yt`), NOT by
  channel_id.
