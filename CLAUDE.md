# Killen Time

Personalized news show generator — two AI hosts discuss the top stories from a profile-driven feed list. Multiple episodes per day. Companion to Kyle's Killen Time Substack.

## Architecture (v0.2 — Beat Reporter Model)

```
                    ┌─────────────────────┐
                    │   EDITOR (main)     │
                    │  assembles show     │
                    └─────────┬───────────┘
                              │
           ┌──────────┬───────┴────────┬──────────┐
           ▼          ▼                ▼          ▼
    ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
    │ AI/Tech    │ │ Agents &   │ │ NBA/Sports │ │ Entertain. │
    │ Beat Agent │ │ Building★  │ │ Beat Agent │ │ Beat Agent │
    └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
          │              │              │              │
    RSS + YouTube   Claude Code +  Podcast RSS    RSS + pods
    + blog fetches  builder pods   + RSS + trades  + Twitch
                    + newsletters
    (★ featured beat — prediction markets demoted to a quick-hit)
```

**Plus a pre-step reporter (2026-06-11):** the **Claude Lab Build-Pitch Reporter** runs after ingest and before the script passes. It scans Claude-technique YouTube transcripts, verifies findings against other sources, and writes a verified upgrade pitch to `build-pitches/YYYY-MM-DD.md` (+ `.tmp/build-pitches.md`) that Pass 1 folds into the show as the "Build-Pitch of the Day." Sports has also shifted to **NFL-led** as the NBA season winds down.

**Cost per episode: $0.00** — script written in Claude Code session, TTS and mixing are free.

## Pipeline (MUST follow this order)

```bash
cd ~/brainrot-radio
source venv/bin/activate

# Step 1: Ingest — get topic brief (now includes podcasts + Twitch)
python3 ingest.py --report -n 15

# Step 2: Research — WebFetch full articles for top stories
# Don't write from RSS summaries alone. Pull the actual source.
# For podcast/twitch items with transcripts, use those directly.

# Step 3: Beat Reporter Agents (NEW in v0.2)
# Launch 4 parallel agents — one per beat (see beats.json)
# Each agent receives: its beat's articles + transcripts, covered-story list, editorial guidelines
# Each returns: 1-3 [BASIL]/[BROOKE] segments with specific source quotes

# Step 4: Assemble — Editor (main session) orders segments, writes intro/outro, adds transitions

# Step 5: QC REVIEW (MANDATORY — see below)
# Launch an agent to read the script and check for problems.
# Fix ALL issues before proceeding.

# Step 6: Render
python3 voice.py scripts/killen-time-YYYY-MM-DD.txt

# Step 7: Mix
python3 mixer.py

# Step 8: Publish (upload MP3, update RSS feed, push to GitHub Pages)
python3 publish.py output/killen-time-YYYY-MM-DD-NN.mp3 --title "Killen Time — YYYY-MM-DD #N" --description "Brief summary"
```

### Beat Reporter Agent Pattern

When generating an episode, launch 4 parallel `general-purpose` agents:

```
Each beat agent receives:
1. Beat definition from beats.json (sources, target_segments, editorial_notes)
2. Relevant articles from ingest.py topic brief (filtered by beat)
3. Full transcripts for podcast/twitch items in its beat (from .tmp/transcripts/ cache)
4. Covered-story list from scripts/.covered-YYYY-MM-DD.json
5. Editorial guidelines (from Content Direction below)

Each beat agent returns:
- 1-3 written [BASIL]/[BROOKE] segments with specific quotes
- Source citations for every claim
- Story slugs for covered-story tracking
```

Editor (main session) then:
- Orders segments for best flow (strongest story first, varied pacing)
- Writes intro (cold open with biggest story) and outro
- Adds [TRANSITION] markers between beat changes
- Validates all dates and freshness
- Runs QC agent

## Quality Control (MANDATORY)

**ALWAYS run a QC agent after writing the script, BEFORE rendering.** The agent should:

1. Read the complete script file
2. Check for:
   - Orphaned/duplicated content from previous drafts
   - Segments out of logical order
   - Repeated signoffs or intro phrases
   - Segments that reference stories not introduced yet
   - Incorrect day of week (verify against the actual date)
   - Missing topic coverage promised in the intro
   - Content that editorializes beyond source material without grounding
   - **Stories presented as "breaking" that are >48h old** (check age_label)
   - **Stories covered in earlier episodes today** (check .covered file)
   - **Missing source quotes** — each segment should cite at least one source
3. Suggest specific line-level fixes
4. Verify the script reads as a coherent single episode, not a mashup

Do NOT render until QC passes clean.

## Content Direction

**Show target: 60 minutes (~14,000-18,000 words). Cover everything — at minimum, hit highlights of every story.**

**Editorial voice is critical.** This is a conversation, not a news ticker. Hosts should:
- Dig deeper into implications, offer counterpoints
- Be opinionated but grounded — editorial must be rooted in source material
- "Here's what this means" = good. "Here's what I imagine despite no evidence" = bad
- Connect stories when the connection is genuinely there — same company, same regulation, direct cause and effect. But don't force connections between unrelated stories. If an AI story and an NBA story don't naturally relate, just move on. One good connection per episode is plenty; don't repeat the same linking move multiple times.
- The outro can briefly recap what was covered and highlight the most interesting thread, but keep it short and don't try to weave every story into a single thesis. A quick sign-off beats a forced synthesis.
- **Include at least one direct quote per segment** from a podcast transcript, article, or stream

**Topic balance per episode — ENFORCE DIVERSITY:**
- Every episode should touch at least 4 different topic areas
- **Agents & Building With AI (FEATURED BEAT — 2026-06-09):** This is now the headline beat, sharing the front half of the show with AI/Tech. Cover how people are actually running their agents: personalized harness structures, CLAUDE.md / context engineering, subagents and multi-agent orchestration, project organization, evals, MCP and tooling, dev-loop optimization. Frame every story through "what can WE steal for our own multi-agent setup" — Kyle is building a team of delegated AIs and wants to optimize that system. Be practitioner-level and specific: quote the actual techniques and configs, not vibes. Sources: Claude Code releases, Latent Space, Simon Willison, One Useful Thing, AI and I, The Cognitive Revolution, No Priors, a16z, Dwarkesh, Karpathy.
- **Prediction markets (DE-EMPHASIZED — 2026-06-09):** Kyle's focus has moved off prediction markets. Demote to at most ONE short quick-hit, and only when there's genuinely notable movement (a big position change, a market resolving, a real edge worth flagging). Otherwise skip the beat entirely. No full multi-segment trading block anymore. The detailed "prediction market editorial principles" below still apply *if* you do include a quick-hit, but the default is brevity or omission.
- **AI/Tech (FOCUS ON HIGH-SIGNAL AI — 2026-06-11):** Anchor the AI block on two shows — the **AI Daily Brief** (Nathaniel Whittemore) and **Moonshots** (Peter Diamandis). When a fresh episode of either exists, lead with its framing and actual arguments/quotes and give it real airtime; use RSS news headlines (Techmeme, TechCrunch, Ars) as context around that discussion, not as the spine. After the anchors, feature high-signal essays (Dean Ball, Ethan Mollick, Zvi) getting discussion in circles Kyle follows. Skip generic news-summary filler. Hand off agent-harness / how-to-build material to the Agents & Building beat, and Claude-technique findings to the Build-Pitch Reporter.
- **Claude Lab / Build-Pitch of the Day (NEW — 2026-06-11):** A dedicated reporter (`claude_lab` beat) runs BEFORE the script passes and writes a verified pitch to `.tmp/build-pitches.md` + `build-pitches/YYYY-MM-DD.md`. In Pass 1, if that summary exists and its first line isn't `NO_VERIFIED_PITCH`, give the top pitch its own exchange inside the Agents & Building block and say on-air that it's logged for Kyle to greenlight. See "Build-Pitch Reporter principles" below.
- **NFL & NBA sports (RAMP NFL AS NBA WINDS DOWN — 2026-06-11):** Football is now the growing half of the sports beat. Lead sports with NFL — build around the **Ringer Fantasy Football Show** (Kyle's named anchor), plus Fantasy Footballers and Bill Barnwell: rankings, values/busts, roster strategy, roster moves, league trends, with specific analyst quotes from transcripts. Keep NBA tighter — only genuinely notable storylines (Finals, draft, major trades/free agency). As the calendar moves toward NFL training camp and the season, keep shifting weight from NBA to NFL. **Pull specific quotes from the podcast transcripts.**
- Entertainment/Film/TV: Kyle is a screenwriter/producer. Industry news, deals, greenlights, box office. Should appear regularly.
- Economics/Culture: Include when there's something genuinely interesting from the rationalist/policy blogosphere.

**Podcasts and Substacks are the backbone of this show.** Generic RSS news feeds (Techmeme, TechCrunch, Verge, etc.) provide awareness of what's happening, but the DEPTH comes from podcast transcripts and Substack essays. When building segments:
- **Lead with podcast/Substack material.** If you have a podcast transcript discussing a topic AND a news headline about the same topic, build the segment around the podcast discussion (quotes, arguments, analysis) and use the news headline as context, not the other way around.
- **Allocate at least 60% of episode time to podcast and Substack content.** News headlines get brief mentions unless there's no podcast/Substack coverage of the topic.
- **Every podcast transcript you received should be covered.** If a transcript was provided, it's there because it scored high enough — give it airtime. Don't mention it in passing; extract the interesting arguments and quotes.

**Substack deep coverage:** Full articles from 25+ Substacks are saved to `.tmp/articles/`. These are the RICHEST material — Zvi's AI roundups, Dean Ball's policy analysis, Scott Alexander's prediction markets coverage, Noah Smith on economics. When an article appears in the topic brief with `Type: substack (full text, N words)`, read the full article from `.tmp/articles/` and integrate key insights, arguments, and quotes into the segment. This is a core service — listeners get the important takeaways without reading 10,000+ word posts.

**Signal detection:** When the same story appears across multiple high-weight feeds AND is getting discussion on X (visible in Techmeme cross-references or HN comment counts), that's a signal to FEATURE it, not just mention it. The Dean Ball essay pattern: high engagement across circles Kyle follows = lead segment material.

**Agents & Building editorial principles (FEATURED BEAT):**
- The point of this beat is for Kyle AND the hosts to LEARN how to run a better multi-agent system. Treat every item as "is there a technique here we should adopt?"
- Get concrete. "They use subagents" is useless; "they spawn one reviewer agent per PR with a three-gate rubric and never let it merge its own work" is the good version. Extract the actual mechanism — the prompt structure, the file layout, the orchestration pattern, the eval loop.
- Topics that belong here: harness/CLAUDE.md design, context engineering, memory and state outside the context window, subagent and multi-agent orchestration, project organization for AI work, evals and quality gates, MCP/tooling, delegation patterns, what's new in Claude Code and rival agent frameworks.
- When two sources describe the same practice, synthesize the strongest version and note who's doing it. Name names — listeners want to know whose setup to copy.
- Connect to Kyle's own stack when it's genuine: the observer-system, the COS, the dispatcher/PR-reviewer loop, this very podcast pipeline. "Here's how we could apply this to our setup" is exactly the payoff.

**Build-Pitch Reporter principles (Claude Lab — NEW 2026-06-11):**
- This is a separate, dedicated reporter (`claude_lab` beat) that runs as its own pipeline step before the script passes (`generate-episode.sh` Step 1.5). It scans recent YouTube transcripts from Claude-technique channels (IndyDevDan, Cole Medin, AI Jason, GosuCoder, Matthew Berman, Anthropic — see `feeds.json` topic `claude_lab`) plus keyword searches, looking for concrete technique on Claude prompting/harness design, running agents, system upgrades, and optimization.
- **It must research and verify before reporting.** For anything interesting, cross-check it against other sources trying the same/similar thing, confirm there's real evidence it works (not a demo or hype), and judge whether it's genuinely novel/meaningful versus something Kyle already does. Discard the rest. Quality over quantity — one well-verified pitch beats three thin ones. If nothing clears the bar, say so honestly; never fabricate a pitch.
- **The payoff loop:** a verified technique gets pitched on the show as the "Build-Pitch of the Day," with the full write-up (technique, sources, evidence, stack-fit, build sketch) saved to `build-pitches/YYYY-MM-DD.md`. Kyle hears it and, if he likes it, points an agent at the episode or that file and says "build this." Treat every pitch as something an agent could pick up and implement with no further context — because that's exactly what's supposed to happen.

**Prediction market editorial principles** (DE-EMPHASIZED 2026-06-09 — these apply only on the rare day you include a prediction-markets quick-hit; the default is to skip the beat):
- Kyle is a sophisticated prediction market trader. Don't reach for shallow takes.
- Regulatory tail risk ≠ getting caught holding positions. Markets refund/adjust on regulatory change. The real risk is PLATFORMS shutting down entirely.
- Prediction markets exist to surface crowd wisdom. The community has argued FOR insider trading (it improves information accuracy). Markets are considered dangerous to military operations because they incentivize premature information release. That's the INTERESTING discussion — not "it looks bad."
- When covering prediction market stories, engage with the sophisticated arguments the community actually makes, not the surface-level media framing.
- If a regulatory story has a trading implication, spell it out: which contracts, which platforms, what action.
- **Locksy/Foster position changes** — when positions.py shows new trades, discuss WHY they might have entered. What's the thesis?

**General editorial principle:** Don't reach for easy/shallow framing when a more informed, more interesting perspective exists. The audience for this show has deep domain knowledge. Engage at that level.

**Time-of-day awareness:** The episode prompt includes a TIME OF DAY line telling you whether this is a morning, afternoon, or evening episode. Use appropriate greetings ("good morning" / "good afternoon" / "good evening"). NEVER say "tonight's episode" for a morning show or "this morning's episode" for an evening show. Match the greeting to the actual production time.

**Show naming:** "The Killen Time Update for [Day], [Month] [Date], [Year]"
- Get the day of week RIGHT. Use Python: `from datetime import date; date(2026, 3, 2).strftime('%A')` → "Monday"
- Episode files: `killen-time-YYYY-MM-DD.txt` (add `-02` suffix for second daily episode)

## Multi-Episode Dedup

**This is the most critical quality issue.** Repeated content across episodes destroys listener trust.

### Rules (MANDATORY):
1. **Read ALL scripts from the last 48 hours** before writing. Not just the most recent — ALL of them.
2. **If a podcast episode was used in ANY previous script, SKIP IT.** Do not extract different quotes from the same episode. It has been consumed.
3. **If a topic was covered in ANY previous script, SKIP IT.** A different author writing about the same event is NOT a new development. A new Nate Silver article about an election result that was already covered via Event Horizon is the SAME TOPIC. New developments means: a price moved, a deal closed, someone resigned, new data was released. A new TAKE on the same facts is NOT new. Read the "segments" dict in the covered JSON — if the underlying facts were already stated on-air, skip the topic entirely.
4. **Save covered stories IMMEDIATELY after writing the script** (before rendering). This ensures the next episode knows what was covered even if the current one hasn't finished publishing yet.
5. **Archive used source files** after writing. Move used transcripts and articles to `.tmp/used/` so the next episode's writer doesn't even see them.
6. **Content summaries are mandatory.** When saving covered stories, include the specific talking points, quotes, and arguments used — not just a slug. This tells the next writer exactly what was already said.

### How to save (do this RIGHT AFTER writing the script):
```python
from ingest import save_covered_stories, archive_used_sources

# Save what was covered with detailed summaries
save_covered_stories(
    ["story-slug-1", "story-slug-2"],
    {
        "story-slug-1": "Covered Cursor hitting $2B ARR, Thieblot quote about tech Twitter, 60% corporate stat",
        "story-slug-2": "Covered Dort-Jokic incident via Raja Bell physical/reckless/dirty framework from Real Ones pod"
    },
    podcast_guids=["guid-1", "guid-2"]
)

# Archive used source files so next episode doesn't re-read them
archive_used_sources(
    used_transcript_guids=["guid-1", "guid-2"],
    used_article_paths=[".tmp/articles/slow_boring_solar-lead.txt"]
)
```

## Files

| File | Purpose |
|------|---------|
| `brainrot.py` | Main orchestrator |
| `ingest.py` | RSS + YouTube + podcast + Twitch fetch, score, rank, deduplicate |
| `transcribe.py` | mlx-whisper transcription engine (shared by podcast.py + twitch.py) |
| `substack.py` | Substack full-article pipeline — extracts content:encoded, saves to .tmp/articles/ |
| `podcast.py` | Podcast RSS download + transcription pipeline |
| `twitch.py` | Twitch VOD download + transcription pipeline |
| `positions.py` | Kalshi position change tracker (Locksy, Foster) |
| `youtube.py` | YouTube transcript pipeline |
| `voice.py` | Edge TTS rendering (2 voices), cleans stale segments |
| `mixer.py` | FFmpeg concat + loudness normalization |
| `config.py` | All constants, paths, voice assignments, publishing config |
| `publish.py` | Upload MP3 to GitHub Releases, generate RSS feed, push to Pages |
| `generate-episode.sh` | Full pipeline orchestrator (ingest → Claude → render → mix → publish) |
| `feeds.json` | Profile-driven feed list + podcast configs + twitch channels |
| `beats.json` | Beat reporter definitions for parallel agents |
| `profile.json` | Interest graph derived from X follows + Spotify podcasts |
| `scripts/` | Archived show scripts + covered-story tracking |
| `data/` | Position snapshots for change tracking |
| `output/` | Final MP3s |
| `.tmp/` | Cached transcripts, downloaded audio, truncated files |

## Voices

- **BASIL** (Kokoro `bm_daniel`) — Anchor, confident, leads segments
- **BROOKE** (Kokoro `af_heart`) — Commentator, analytical, adds perspective

TTS engine: Kokoro (local MLX, `mlx-community/Kokoro-82M-bf16`). Fallback: Edge TTS (`--engine edge`).

## Scoring Algorithm

`score = recency × feed_weight × topic_weight × keyword_boost`

- Recency: exponential decay, 6-hour half-life
- Feed weights: per-feed in feeds.json (Event Horizon 3.0, Techmeme 2.0, etc.)
- Topic weights: agentic_systems=2.5, ai_and_tech=2.0, economics=1.5, …, prediction_markets=1.0 (demoted 2026-06-09)
- Keyword boosts: Claude Code / agent harness / subagents / multi-agent / context engineering (~1.25-1.3); prediction-market terms dropped to 1.0 (no longer boosted)
- Dedup: >40% title word overlap → merge (keep higher score)
- Topic diversity: at least 1 story per active topic guaranteed in brief
- **Age labels: today/yesterday/this week/older — articles >48h marked NOT BREAKING**

## Dependencies

- Python 3.13 (venv at `./venv/`)
- `mlx-audio` — Kokoro TTS (local MLX, Apple Silicon optimized, primary TTS)
- `edge-tts` — Microsoft Edge TTS (free, async, fallback)
- `mlx-whisper` — Apple Silicon optimized Whisper transcription
- `yt-dlp` — YouTube transcripts + Twitch VOD downloads
- `ffmpeg` — Audio truncation, concatenation, normalization (`/opt/homebrew/bin/ffmpeg`)

## Known Issues

- Anthropic blog RSS returns 404
- The Diff (Substack) returns 400
- The Economist returns 403 (paywall)
- The Free Press returns empty (may need different feed URL)
- Edge TTS voices are staccato — need SSML, longer segments, rate tuning
- No intro/outro music yet (only silence pads)
- HiveLive content (X Spaces) not yet capturable — monitoring X feed only

## Publishing & Distribution

Episodes publish to a podcast RSS feed via GitHub Pages + GitHub Releases:

- **Feed URL:** `https://kylekillen.github.io/killen-time-podcast/feed.xml`
- **GitHub Repo:** `kylekillen/killen-time-podcast`
- **MP3 Hosting:** GitHub Releases (one release per episode)
- **Spotify:** Submitted via Spotify for Podcasters — auto-polls the feed

```bash
# Publish an episode
python3 publish.py output/killen-time-2026-03-02-03.mp3

# Check podcast feed health
python3 podcast.py --check-feeds
```

**Automated schedule:** launchd runs `generate-episode.sh` daily at 5:30 AM MT.
The script runs in discrete steps (ingest → write script → QC → render/publish), each with its own timeout.
Each episode should comprehensively cover everything that dropped since the last episode — podcasts, Substacks, breaking news. The goal is that a listener does NOT need to go listen to the underlying podcasts.

## Future (v0.3+)

- Per-episode generated artwork via local image model
- Google Trends integration for general awareness
- SSML markup for more natural voice flow
- Intro/outro music stingers
- NotebookLM pipeline (PDF → upload → video)
- HiveLive X Spaces full transcript capture
- Browser-based Kalshi position scraping for Locksy/Foster
