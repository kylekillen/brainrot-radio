# Gemini Managed Agent — Killen Time experiment (staged, unrun)

The real test from Kyle's Gemini thread: hand a **Gemini Managed Agent** (the
Antigravity agent announced at Google I/O 2026) our blueprint and let *it* spin
up a sandbox, browse our sources, and build a finished ~1-hour Killen Time
episode — then we download it and publish. This is **not** NotebookLM; it's the
new Interactions API where Google runs a team of agent steps in an ephemeral
Linux box and hands back the artifact.

## Files
- `BRIEF.md` — the blueprint we hand the agent (sources, show shape, length, RSS
  conventions, output contract). This is the whole "tell it what we want" payload.
- `run.py` — launches the agent with the brief, streams its steps, captures the
  `environment_id`, and downloads the finished sandbox as a tar.

## The one blocker: billing
As of 2026-05-21 the Managed Agents endpoint returns **HTTP 429 "not enough
quota"** on our only Google key (the nanobanana free-tier key). The *basic*
Gemini endpoint works on that same key — so this is purely a paid-tier gate, not
a broken key. Managed Agents is a billed preview (per-token at Gemini 3.5 Flash
rates).

To run it:
1. In Google AI Studio / Cloud console, enable **billing** on the project behind
   a Gemini key (or make a fresh key in a billing-enabled project).
2. `export GOOGLE_AI_API_KEY=AIza...`
3. `python3 run.py`

It streams progress, then downloads `pulled/env-<id>.tar`. Extract it, listen to
`output/killen-time.mp3`, and publish with the existing `../publish.py`.

## Note on the output contract
The agent does **not** push to our live feed — it has no GitHub creds and
shouldn't. It produces the MP3 + cover + script + show notes in its sandbox; we
pull them and run our own `publish.py`. That keeps Google's sandbox away from our
subscriber feed while still getting "finished product in, episode out."
