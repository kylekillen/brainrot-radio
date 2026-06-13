# Killen Time as a Product Template

## Vision

Turn the Killen Time pipeline into a configurable template that anyone can use to generate a personalized AI podcast from their own interests, feeds, and editorial preferences.

## What's Already Parameterized

The current architecture is surprisingly close to template-ready. Most personalization already lives in config files:

| Component | File | What It Controls |
|-----------|------|-----------------|
| Feed sources | `feeds.json` | RSS, Substacks, podcasts, YouTube, Twitch channels |
| Interest profile | `profile.json` | Topic weights derived from social follows |
| Topic scoring | `feeds.json` → `topic_weights` | How much weight each topic area gets |
| Keyword boosts | `config.py` → `KEYWORD_BOOSTS` | Fine-grained keyword relevance |
| Voices | `config.py` → `KOKORO_VOICES` / `VOICES` | Host names, TTS voices, personality |
| Show format | `CLAUDE.md` | Editorial voice, segment structure, show length |
| Publishing | `config.py` → publishing section | GitHub repo, feed URL, artwork |
| Scheduling | launchd plist | How often episodes are generated |

## What Needs Abstraction

### 1. User Profile Onboarding
- **Current:** Kyle's feeds.json was hand-curated from his X follows and Spotify subscriptions
- **Template:** Need a setup wizard that:
  - Accepts a list of RSS/podcast URLs (or imports from OPML)
  - Optionally imports from X following list, Spotify podcast subscriptions
  - Auto-categorizes feeds into topics
  - Generates initial topic_weights based on feed distribution
  - Creates beats.json with logical beat groupings

### 2. Editorial Voice Configuration
- **Current:** CLAUDE.md has Kyle-specific editorial guidance (prediction market sophistication, screenwriter perspective, NBA coverage requirements)
- **Template:** Need a `voice-config.md` or similar that captures:
  - Host names and personalities
  - Domain expertise level per topic ("expert" vs "enthusiast" vs "casual")
  - Editorial tone (analytical, conversational, irreverent, formal)
  - Show length preference (15min / 30min / 60min)
  - Connection style (how much to link stories vs. treat independently)

### 3. Infrastructure Per-User
- **Current:** Single GitHub Pages repo for RSS feed hosting
- **Template options:**
  - Self-hosted: user provides their own GitHub repo (or S3 bucket)
  - Managed: we host the RSS feed and MP3s (requires backend)
  - Hybrid: user runs locally, we provide the podcast hosting

### 4. TTS Voice Selection
- **Current:** Kokoro MLX (requires Apple Silicon) with Edge TTS fallback
- **Template:** Need to handle:
  - Users without Apple Silicon → Edge TTS or cloud TTS
  - Voice selection UI (preview voices, pick host voices)
  - Custom voice names (not everyone wants Basil and Brooke)

## Minimum Viable Template

### Phase 1: "Fork and Configure" (Lowest effort)
- Clean up the repo for public consumption
- Replace Kyle-specific content with placeholder/example config
- Write a setup guide: "Edit these 3 files to make it yours"
- Ship as a GitHub template repository
- **Target user:** Technical person who can run Python scripts and edit JSON

### Phase 2: "Setup Wizard" (Medium effort)
- `python3 setup.py` interactive CLI that:
  - Asks for name, interests, existing podcast/RSS subscriptions
  - Imports OPML files
  - Generates feeds.json, profile.json, beats.json
  - Configures voice preferences
  - Sets up GitHub Pages publishing
  - Creates the launchd schedule
- **Target user:** Semi-technical person comfortable with terminal

### Phase 3: "Hosted Service" (Full product)
- Web UI for feed management and show configuration
- Cloud-based episode generation (no local compute needed)
- Managed podcast hosting with RSS feed
- Dashboard showing episode history, listener stats
- Subscription model: free tier (1 episode/day, 15min) → paid (unlimited, 60min)
- **Target user:** Anyone

## Revenue Model Considerations

| Model | Pros | Cons |
|-------|------|------|
| Open source + hosting fee | Community builds it, we monetize infra | Race to bottom on hosting |
| Freemium SaaS | Recurring revenue, low barrier | Compute costs scale with users |
| One-time template sale | Simple, no ongoing support | Limited revenue ceiling |
| API/minute pricing | Usage-aligned | Complex billing, unpredictable for users |

**Recommended:** Open source the pipeline (builds community, trust), charge for managed hosting + premium voices + longer episodes. The Claude API cost per episode is $0 (runs in Claude Code session), but TTS compute and MP3 hosting have real costs at scale.

## Key Technical Decisions

1. **Claude Code dependency:** Currently requires Claude Code CLI for episode generation. A hosted version would need the Claude API directly, which changes the cost model significantly.

2. **Local vs. cloud TTS:** Kokoro MLX is free but requires Apple Silicon. Cloud TTS (ElevenLabs, Play.ht) costs $0.15-0.30/minute but works everywhere. At 60min episodes, that's $9-18/episode in TTS costs alone.

3. **Feed infrastructure:** Each user needs their own RSS feed URL. GitHub Pages is free but requires a GitHub account. S3 + CloudFront would be ~$0.50/month per user.

4. **Dedup state:** The covered-stories tracking is per-show. Multi-user means per-user state management.

## Next Steps

1. Audit the codebase for Kyle-specific hardcoding vs. config-driven behavior
2. Extract CLAUDE.md editorial guidelines into a template with fill-in-the-blank sections
3. Build the Phase 1 template repo as a proof of concept
4. Test with 2-3 beta users who have different interest profiles
