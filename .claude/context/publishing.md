# Publishing & Distribution

Episodes publish to a podcast RSS feed via GitHub Pages + GitHub Releases.

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

## Render → Mix → Publish (the direct steps)
```bash
# Render TTS (2 voices; Kokoro primary, --engine edge fallback)
python3 voice.py scripts/killen-time-YYYY-MM-DD.txt

# Mix (FFmpeg concat + loudness normalization; optional --artwork)
python3 mixer.py --output output/killen-time-YYYY-MM-DD.mp3

# Publish (upload MP3, generate RSS, push to Pages)
python3 publish.py output/killen-time-YYYY-MM-DD.mp3 \
  --title "Killen Time — YYYY-MM-DD" --description "Brief summary"
```

## Automated schedule
launchd runs `generate-episode.sh` daily (the production entrypoint). It runs in
discrete steps (ingest → build-pitch reporter → write script (2 passes) → QC →
render → mix → publish → archive), each with its own timeout. Each episode should
comprehensively cover everything that dropped since the last episode — podcasts,
Substacks, breaking news. The goal: a listener does NOT need to go listen to the
underlying podcasts.

Three launchd jobs run together:
- `com.mojo.brainrot-radio` — episode generator
- `com.mojo.brainrot-ingest` — ingest
- `com.mojo.brainrot-check` — health checker (recovery re-run)

If you disable one for testing, note which and re-enable it.
