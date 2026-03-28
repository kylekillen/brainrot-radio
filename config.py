"""Brainrot Radio v0.2 — Configuration."""

from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).parent
SCRIPTS_DIR = PROJECT_DIR / "scripts"
ASSETS_DIR = PROJECT_DIR / "assets"
OUTPUT_DIR = PROJECT_DIR / "output"
LOGS_DIR = PROJECT_DIR / "logs"
TEMP_DIR = PROJECT_DIR / ".tmp"
DATA_DIR = PROJECT_DIR / "data"

FEEDS_JSON = PROJECT_DIR / "feeds.json"
BEATS_JSON = PROJECT_DIR / "beats.json"
PROFILE_JSON = PROJECT_DIR / "profile.json"

# ── Voice Config ───────────────────────────────────────────────────
# TTS engine: "kokoro" (local MLX, higher quality) or "edge" (Microsoft Edge TTS, fallback)
TTS_ENGINE = "kokoro"

# Kokoro voice config (mlx-audio, local)
KOKORO_VOICES = {
    "BASIL": {
        "voice": "bm_daniel",
        "lang_code": "a",
        "description": "Anchor — confident, leads segments",
    },
    "BROOKE": {
        "voice": "af_heart",
        "lang_code": "a",
        "description": "Commentator — analytical, adds perspective",
    },
}

# Edge TTS voice config (fallback)
VOICES = {
    "BASIL": {
        "voice": "en-US-GuyNeural",
        "rate": "+25%",
        "pitch": "-2Hz",
        "description": "Anchor — confident, leads segments",
    },
    "BROOKE": {
        "voice": "en-US-AriaNeural",
        "rate": "+20%",
        "pitch": "+1Hz",
        "description": "Commentator — analytical, adds perspective",
    },
}

# ── Show Config ────────────────────────────────────────────────────
TARGET_DURATION_MIN = 60  # v0.4: 60 minutes for comprehensive coverage
TARGET_WORD_COUNT = 16000  # v0.4: ~14000-18000 words for 60-min episodes
MIN_WORD_COUNT = 6000  # Hard floor — voice.py refuses to render below this (~25 min)
TOP_STORIES = 40  # expanded for comprehensive coverage across all feeds
SHOW_NAME = "Killen Time"

# ── Transcription Config ──────────────────────────────────────────
WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
DEFAULT_MAX_AUDIO_MINUTES = 30
TRANSCRIPT_SUMMARY_CHARS = 4000  # Chars included in topic brief scoring

# ── Scoring ────────────────────────────────────────────────────────
# Per-feed and per-topic weights are read from feeds.json at runtime.
# These keyword boosts apply on top of those weights.
# Keyword boosts are MINOR tiebreakers within the same recency tier.
# Recency is king — newest content always surfaces first.
# These just nudge coverage depth for topics Kyle cares about most.
KEYWORD_BOOSTS = {
    "Claude": 1.15,
    "Anthropic": 1.15,
    "Claude Code": 1.2,
    "MCP": 1.1,
    "AI safety": 1.1,
    "prediction market": 1.15,
    "Kalshi": 1.15,
    "Polymarket": 1.1,
    "forecasting": 1.1,
    "OpenAI": 1.1,
    "GPT": 1.05,
    "Gemini": 1.05,
    "AI agents": 1.15,
    "LLM": 1.05,
    "NBA trade": 1.1,
    "longevity": 1.05,
    "Formula 1": 1.0,
}

RECENCY_HALF_LIFE_HOURS = 6

# ── Publishing ─────────────────────────────────────────────────────
GITHUB_REPO = "kylekillen/killen-time-podcast"
FEED_URL = "https://kylekillen.github.io/killen-time-podcast/feed.xml"
ARTWORK_URL = "https://kylekillen.github.io/killen-time-podcast/artwork.jpg"
SITE_URL = "https://kylekillen.github.io/killen-time-podcast"

# ── FFmpeg ─────────────────────────────────────────────────────────
FFMPEG = "/opt/homebrew/bin/ffmpeg"
LOUDNORM_PARAMS = "loudnorm=I=-16:TP=-1.5:LRA=11"
