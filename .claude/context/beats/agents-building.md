# Beat: Agents & Building With AI — FEATURED BEAT (2026-06-09)

This is the **headline beat**, sharing the front half of the show with AI/Tech.
Cover how people are actually running their agents: personalized harness
structures, CLAUDE.md / context engineering, subagents and multi-agent
orchestration, project organization, evals, MCP and tooling, dev-loop
optimization.

Frame every story through **"what can WE steal for our own multi-agent setup"** —
Kyle is building a team of delegated AIs and wants to optimize that system. Be
practitioner-level and specific: quote the actual techniques and configs, not
vibes.

**Sources:** Claude Code releases, Latent Space, Simon Willison, One Useful
Thing, AI and I, The Cognitive Revolution, No Priors, a16z, Dwarkesh, Karpathy.

**Target:** 2-3 segments, ~3500-4500 words.

## Editorial principles
- The point of this beat is for Kyle AND the hosts to LEARN how to run a better
  multi-agent system. Treat every item as "is there a technique here we should
  adopt?"
- Get concrete. "They use subagents" is useless; "they spawn one reviewer agent
  per PR with a three-gate rubric and never let it merge its own work" is the
  good version. Extract the actual mechanism — the prompt structure, the file
  layout, the orchestration pattern, the eval loop.
- Topics that belong here: harness/CLAUDE.md design, context engineering, memory
  and state outside the context window, subagent and multi-agent orchestration,
  project organization for AI work, evals and quality gates, MCP/tooling,
  delegation patterns, what's new in Claude Code and rival agent frameworks.
- When two sources describe the same practice, synthesize the strongest version
  and note who's doing it. Name names — listeners want to know whose setup to
  copy.
- Connect to Kyle's own stack when it's genuine: the observer-system, the COS,
  the dispatcher/PR-reviewer loop, this very podcast pipeline. "Here's how we
  could apply this to our setup" is exactly the payoff.

## Build Pitch of the Day (slots inside this block)
If `.tmp/build-pitches.md` exists AND its first line is not `NO_VERIFIED_PITCH`,
give the top verified pitch its own dedicated exchange (~400-700 words): what the
technique is, who's doing it (name the source), the evidence it's real, and
exactly how it would upgrade Kyle's setup. Then have a host say plainly that it's
logged in the build-pitches folder so Kyle can point an agent at it and greenlight
the build. If the file is missing or says NO_VERIFIED_PITCH, skip — do NOT invent
a pitch. See `claude-lab.md` for how that pitch gets produced.
