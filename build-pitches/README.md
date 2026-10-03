# Build Pitches — Killen Time "Claude Lab" Reporter

This folder is the durable record of **verified upgrade pitches** produced by
the Build-Pitch Reporter beat (`claude_lab` in `beats.json`).

## What this is

Every episode, a dedicated reporter agent scans recent YouTube transcripts from
Claude-technique channels (IndyDevDan, Cole Medin, AI Jason, GosuCoder, Matthew
Berman, Anthropic — see `feeds.json` → `youtube_channels`, topic `claude_lab`)
plus targeted keyword searches, looking for concrete techniques about:

- **Claude technique** (prompting, context priming, CLAUDE.md / harness design)
- **Running agents** (subagents, multi-agent orchestration, delegation patterns)
- **System upgrades** (new Claude Code / model features and how to use them)
- **Optimization** (dev-loop tuning, evals, cost/latency, memory & state)

The reporter does **not** just summarize videos. For anything interesting it
**researches and verifies** first — cross-checking against other sources trying
the same or similar thing, and confirming there's real evidence it works (not a
demo or hype). That evidence bar is the one thing that never relaxes.

**Overlap is not a disqualifier.** "We already do this" is a strange default
posture (Kyle, 2026-09-27) — 1% better every day compounds. When a technique
overlaps something Kyle already runs, the pitch is the **delta**: the check, the
default, the cheaper model, the missing loop their version has and his likely
doesn't. A fresh delta on a topic he already covers is a new pitch, not a repeat.
Only what clears the verification bar becomes a pitch.

## The loop (why this exists)

1. A verified technique gets pitched **on the podcast** as a "Build Pitch of the Day."
2. Kyle hears it. If it sounds worth doing, he **points an agent at the episode
   or at the dated file in this folder** and says *"build this."*
3. The pitch file already contains the verification, the source links, the map
   onto Kyle's stack, and a concrete build sketch — so the building agent has
   everything it needs to start.

Think of it as the show pitching upgrades, and Kyle okaying the work after
hearing about it.

## File format

One file per day: `YYYY-MM-DD.md`. Each verified pitch contains:

- **Technique** — what it is, in one or two sentences.
- **Who's doing it** — the specific video(s) + any corroborating sources (links).
- **Evidence it's real** — what was cross-checked and why it's believed to work.
- **Delta vs Kyle's current setup** — what their version does that his likely
  doesn't. This is the pitch, not a comparison that can fail.
- **Need it serves** — which fleet pain, and which of Kyle's priorities 1–3
  (screenwriting / multi-agent business / resilience) it moves.
- **Whole-fleet leverage** — one line the Fleet Optimizer can rank on.
- **Build sketch** — concrete first steps an agent could take to implement it.
- **More takeaways** — up to 4 smaller one-line improvements, each citing its source.
- **Status** — `pitched` (on the show, awaiting Kyle), or `money — discuss first`.
  Once an agent takes a pitch up, its lifecycle belongs on the task board and in its
  implementation PR; the dated pitch remains the original record.

If nothing survives verification on a given day, the file says so explicitly. The
reporter never fabricates a pitch.
