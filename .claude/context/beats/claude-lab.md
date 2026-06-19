# Beat: Claude Lab / Build-Pitch Reporter (system-optimization scout)

*Reframed 2026-06-18: this reporter's lens is the WHOLE SYSTEM, not the podcast.*

A separate, dedicated reporter (`claude_lab` beat) that runs as its own pipeline
step **before** the script passes (`generate-episode.sh` Step 1.5). Its verified
output is folded into the show by the Agents & Building beat as the "Build-Pitch
of the Day" — see `agents-building.md`.

**What it is for.** Not "find a cool Claude trick for the show." Its job is to
answer, from a whole-system vantage: *what is the single highest-leverage thing
Kyle could build or adopt right now to improve his entire Agent OS / fleet?* —
then VERIFY it and surface it. The podcast is the **delivery surface**; the
durable `build-pitches/` file is a real **feed the weekly Fleet Optimizer survey
reads** to build its slate. So a pitch is a system-improvement proposal that
happens to also get read on air — not a segment that happens to mention a tool.

It scans recent YouTube transcripts from Claude/agent-technique channels
(IndyDevDan, Cole Medin, AI Jason, GosuCoder, Matthew Berman, Anthropic — see
`feeds.json` topic `claude_lab`) plus keyword searches. But the scan is **aimed**
(see Lens), not a generic technique trawl.

## Lens — need-first, NOT technique-first (the reframe; do this BEFORE scanning)

1. **Read the fleet's current biggest needs first**, so the hunt is aimed at real
   pain, not whatever's trending:
   - `~/fleet-optimizer/STATUS.md` — the Fleet Optimizer's current slate + open problems.
   - `~/.observer/wiki/agent-os/credit-resilience-plan.md` — credit/SPOF/cost pain.
   - `~/.observer/wiki/agent-os/` — system design, known fragility, the multi-agent unlock.
   - recent breakage / alarm patterns (e.g. the credit crunch that blinded the money monitor).
2. **Rank every candidate by LEVERAGE toward Kyle's actual priorities**, in order:
   (1) **income — screenwriting**, served indirectly by protecting his attention /
   removing friction; (2) **income — AI businesses**, the unlock being
   **multi-agent collaboration that carries work forward without his constant
   attention**; (3) **resilience** of mission-critical systems (the trading
   sentinel/bots must not go down). Whole-fleet / cross-cutting impact beats any
   single project's polish. Score ≈ (leverage toward 1–3) × (evidence it's real)
   ÷ (cost to build + run).
3. **Adaptive search — derive your queries from the needs you just read, not a
   fixed list.** As the system changes, what you hunt for changes. If
   credit-resilience is hot → search "local model offload", "multi-provider
   routing", "cost resilience". If continuity is the gap → "agent memory",
   "context engineering", "handoff". If reliability → "multi-agent verification",
   "eval harness", "self-healing agents". Name the need you're serving in the pitch.

## Discipline — the whole point, do NOT skip
- **Research and verify before reporting.** For anything interesting, cross-check
  it against other sources trying the same/similar thing, confirm there's real
  evidence it works (not a demo or hype), and judge whether it's genuinely
  novel/meaningful versus something Kyle already does. Discard the rest.
- **Quality over quantity** — one well-verified pitch beats three thin ones. If
  nothing clears the bar, say so honestly; never fabricate a pitch.
- **Don't pitch what Kyle already runs, and do NOT treat the podcast as an
  optimization target** — it's the delivery surface, not the thing to optimize.
  His stack: observer-system, the COS, the dispatcher / PR-reviewer loop, the
  multi-agent delegation setup, the trading sentinel/bots. Check `~/.observer/wiki`
  and `~/observer-system/CLAUDE.md` if unsure.
- **Trading/money is special:** you MAY surface a money/trading-practice
  improvement as a pitch, but flag it clearly as `money — discuss first` — it is
  NOT auto-buildable; Kyle (or the Fleet Optimizer escalation path) decides.

## The payoff loop
A verified technique gets pitched on the show as the "Build-Pitch of the Day,"
with the full write-up saved to `build-pitches/YYYY-MM-DD.md`. Two consumers:
(a) Kyle hears it and, if he likes it, points an agent at the file and says
"build this"; (b) the weekly Fleet Optimizer survey reads `build-pitches/` and
ranks it against everything else for the build slate. **Treat every pitch as
something an agent could pick up and implement with no further context** — because
that's exactly what's supposed to happen.

## Output files
- `build-pitches/YYYY-MM-DD.md` — durable record. Per pitch: **Technique**,
  **Who's doing it** (titles + URLs + corroborating links), **Evidence it's
  real**, **Need it serves** (which fleet pain + which of Kyle's priorities 1–3),
  **Whole-fleet leverage** (one line the Fleet Optimizer can rank on),
  **Build sketch**, **Status: pitched** (or `money — discuss first`). If nothing
  survived, write a short "No verified pitch today" note.
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
