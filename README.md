# Brainrot Radio

**Fully automated, AI-generated daily podcast.** Claude Code writes the script, Kokoro renders the voices, and the whole thing publishes to a podcast RSS feed — zero human intervention.

Built for [Killen Time](https://kylekillen.github.io/killen-time-podcast/), a daily news show covering AI, prediction markets, NBA, entertainment, and economics/culture. Two AI hosts (Basil and Brooke) discuss the day's stories with editorial depth, pulling from 40+ RSS feeds, 30+ podcasts, and 25+ Substacks.

## How It Works

```
launchd (daily 5:30 AM)
  └── generate-episode.sh
        ├── Step 1: Ingest (RSS + podcasts + Substacks + YouTube + Twitch)
        ├── Step 2a: Claude writes first half (AI/tech + prediction markets)
        ├── Step 2b: Claude writes second half (NBA + entertainment + economics)
        ├── Step 3: Claude QC reviews the combined script
        └── Step 4: Render voices → mix audio → publish to RSS feed
```

Each step runs as a separate `claude -p` call with its own timeout. If one step fails, the logs show exactly where.

**Cost per episode: $0.** Script via Claude Code (included in Claude subscription), TTS via Kokoro (local), hosting via GitHub Pages.

## Setup

### Prerequisites

- macOS with Apple Silicon (for MLX-based TTS and Whisper)
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- Python 3.11+
- ffmpeg (`brew install ffmpeg`)

### Install

```bash
git clone https://github.com/kylekillen/brainrot-radio.git
cd brainrot-radio
python3 -m venv venv
source venv/bin/activate
pip install mlx-audio edge-tts mlx-whisper feedgen yt-dlp
```

### Configure Your Sources

Edit `feeds.json` to add your RSS feeds, podcasts, Substacks, YouTube channels, and Twitch streams. Each entry looks like:

```json
{
  "id": "techmeme",
  "name": "Techmeme",
  "url": "https://www.techmeme.com/feed.xml",
  "type": "rss",
  "topic": "ai_and_tech",
  "weight": 2.0
}
```

Supported types: `rss`, `podcast` (auto-transcribes episodes), `substack` (fetches full articles), `youtube`, `twitch`.

Edit `beats.json` to define your show's topic beats (which sources map to which segments).

Edit `config.py` to set your show name, target duration, voices, publishing config, and keyword boosts.

### Configure Publishing

The default publishes to GitHub Releases + GitHub Pages RSS feed. Update these in `config.py`:

```python
GITHUB_REPO = "youruser/your-podcast-repo"
FEED_URL = "https://youruser.github.io/your-podcast-repo/feed.xml"
ARTWORK_URL = "https://youruser.github.io/your-podcast-repo/artwork.jpg"
SITE_URL = "https://youruser.github.io/your-podcast-repo"
```

You'll need a separate GitHub repo for the podcast feed (with GitHub Pages enabled) and `gh` CLI authenticated.

### Run Manually

```bash
source venv/bin/activate
bash generate-episode.sh
```

### Schedule Daily

Create a launchd plist (macOS) to run `generate-episode.sh` on a schedule:

```bash
# Example: daily at 5:30 AM
cat > ~/Library/LaunchAgents/com.brainrot-radio.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.brainrot-radio</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/path/to/brainrot-radio/generate-episode.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>5</integer>
        <key>Minute</key>
        <integer>30</integer>
    </dict>
    <key>WorkingDirectory</key>
    <string>/path/to/brainrot-radio</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>/Users/yourusername</string>
    </dict>
    <key>StandardOutPath</key>
    <string>/path/to/brainrot-radio/logs/launchd-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/brainrot-radio/logs/launchd-stderr.log</string>
</dict>
</plist>
EOF

launchctl load ~/Library/LaunchAgents/com.brainrot-radio.plist
```

## Architecture

| File | Purpose |
|------|---------|
| `generate-episode.sh` | Pipeline orchestrator — runs all steps with individual timeouts |
| `ingest.py` | Fetches RSS, podcasts, Substacks, YouTube, Twitch; scores and ranks stories |
| `substack.py` | Substack full-article extraction pipeline |
| `podcast.py` | Podcast RSS download + Whisper transcription |
| `twitch.py` | Twitch VOD download + transcription |
| `youtube.py` | YouTube transcript pipeline |
| `transcribe.py` | MLX-Whisper transcription engine |
| `voice.py` | Kokoro TTS rendering (2 voices), with Edge TTS fallback |
| `mixer.py` | FFmpeg concat + loudness normalization |
| `publish.py` | Upload MP3 to GitHub Releases, generate RSS feed |
| `artwork.py` | Episode cover art generation |
| `song_of_the_day.py` | Instrumental closer via ACE-Step (optional) |
| `config.py` | All constants, paths, voices, publishing config |
| `feeds.json` | Your source feeds — RSS, podcasts, Substacks, YouTube, Twitch |
| `beats.json` | Beat reporter definitions (topic groupings for the show) |
| `CLAUDE.md` | Editorial guidelines that Claude reads when writing scripts |

## How the Two-Pass Script Writing Works

A single `claude -p` call reliably produces ~8-10K words. For a 60-minute episode (14-18K words), the pipeline uses two passes:

1. **Pass 1**: Writes the intro + AI/Tech segments + Prediction Markets segments (~7-9K words)
2. **Pass 2**: Reads Pass 1's output, then appends NBA + Entertainment + Economics/Culture + outro (~7-9K words)

Pass 2 reads the script from Pass 1 before writing, so there's no topic duplication. A QC step then checks for seam issues between the halves.

## Customization

This is designed to be forked and customized. To make your own show:

1. **Replace `feeds.json`** with your own sources (any RSS feed, podcast, Substack, YouTube channel, or Twitch stream)
2. **Edit `beats.json`** to define your show's topic beats
3. **Edit `CLAUDE.md`** to set your show's editorial voice and guidelines
4. **Edit `config.py`** to change the show name, voices, duration target, and keyword boosts
5. **Update `generate-episode.sh`** prompts if you want a different show structure

The editorial guidelines in `CLAUDE.md` are what give the show its personality. That's where you define how opinionated the hosts should be, what topics to prioritize, and what the show's perspective is.

## Dedup System

The biggest quality challenge is preventing repeated content across episodes. The pipeline handles this with:

- **Covered-stories JSON files** (`scripts/.covered-*.json`) track every story, quote, and talking point used in previous episodes
- **Source archival** — used transcripts and articles move to `.tmp/used/` so the next episode never sees them
- **Script dedup** — each writing pass reads the last 3 episodes before generating new content
- **Podcast GUID tracking** — once a podcast episode is used, it's never re-transcribed

## License

MIT
