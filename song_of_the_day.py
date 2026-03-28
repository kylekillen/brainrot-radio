#!/usr/bin/env python3
"""Killen Time — Song of the Day Generator.

Generates a unique instrumental track via ACE-Step API to close each episode.
Tracks that hit become seeds for real music production.

Usage:
    python3 song_of_the_day.py                         # Generate today's song
    python3 song_of_the_day.py --date 2026-03-18       # Specific date
    python3 song_of_the_day.py --genre "jazz"           # Force a genre
    python3 song_of_the_day.py --duration 90            # Custom duration (seconds)

Requires: ACE-Step API running at http://127.0.0.1:8001
"""

import argparse
import hashlib
import json
import sys
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path

from config import ASSETS_DIR

ACESTEP_API = "http://127.0.0.1:42003"
SONG_DIR = ASSETS_DIR / "music" / "song-of-the-day"
DEFAULT_DURATION = 120  # 2 minutes — long enough to be a real piece

# Genre palette — deterministic-random pick per date, or manual override.
# Each entry: (caption for ACE-Step, human-readable name)
GENRE_PALETTE = [
    ("chill lo-fi hip hop instrumental, warm vinyl crackle, mellow piano chords, dusty drum breaks, soft bass, late night vibes", "lo-fi hip hop"),
    ("smooth jazz instrumental, walking bass, brushed drums, warm saxophone melody, muted trumpet, evening lounge atmosphere", "smooth jazz"),
    ("ambient electronic instrumental, lush synth pads, gentle arpeggios, subtle percussion, ethereal textures, deep space atmosphere", "ambient electronic"),
    ("cinematic orchestral instrumental, sweeping strings, french horn melody, gentle timpani, epic but intimate, sunrise feeling", "cinematic orchestral"),
    ("neo soul instrumental, rhodes piano, warm bass guitar, crisp drums, subtle wah guitar, golden hour vibes", "neo soul"),
    ("acoustic folk instrumental, fingerpicked guitar, upright bass, gentle mandolin, open air feeling, morning coffee", "acoustic folk"),
    ("synthwave instrumental, retro analog synths, driving bass, electronic drums, neon nostalgia, midnight drive", "synthwave"),
    ("bossa nova instrumental, nylon guitar, soft brush drums, gentle bass, tropical warmth, afternoon breeze", "bossa nova"),
    ("minimal piano instrumental, sparse contemporary classical, gentle reverb, emotional melody, rain on windows, reflective mood", "minimal piano"),
    ("funk instrumental, slap bass, tight drums, wah guitar, brass stabs, head-nodding groove, saturday night energy", "funk"),
    ("trip hop instrumental, downtempo beats, atmospheric samples, deep bass, mysterious textures, urban night", "trip hop"),
    ("blues rock instrumental, overdriven guitar, shuffling drums, walking bass, raw and honest, smoky room", "blues rock"),
]


def pick_genre(show_date: str) -> tuple[str, str]:
    """Deterministic-random genre pick based on date."""
    idx = int(hashlib.md5(f"song-of-the-day-{show_date}".encode()).hexdigest(), 16) % len(GENRE_PALETTE)
    return GENRE_PALETTE[idx]


def check_api() -> bool:
    """Check if ACE-Step API is reachable."""
    try:
        req = urllib.request.Request(f"{ACESTEP_API}/v1/models", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def generate_song(caption: str, duration: int = DEFAULT_DURATION, batch_size: int = 2) -> list[Path]:
    """Generate music via ACE-Step Gradio API.

    Uses the /generation_wrapper endpoint with proper Gradio API format.
    Returns list of generated audio file paths.
    """
    # Build Gradio API call to /generation_wrapper
    # Parameters map to the UI fields (see /gradio_api/info for full list)
    payload = json.dumps({
        "data": [
            caption,          # Music Caption
            "",               # Lyrics (empty for instrumental)
            "",               # BPM (auto)
            "",               # Key (auto)
            "",               # Time Signature (auto)
            "en",             # Vocal Language
            8,                # DiT Inference Steps (turbo default)
            7.0,              # DiT Guidance Scale
            True,             # Random Seed
            -1,               # Seed (-1 = random)
            None,             # Reference Audio
            duration,         # Audio Duration (seconds)
            batch_size,       # Batch Size
            None,             # Source Audio
            None,             # LM Codes Hints
            0,                # Repainting Start
            0,                # Repainting End
            "",               # Instruction
            1.0,              # LM Codes Strength
            0.5,              # Cover Strength
            "text2music",     # task_type
            False,            # Use ADG
            0.0,              # CFG Interval Start
            1.0,              # CFG Interval End
            3.0,              # Shift
            "euler",          # Inference Method
            "",               # Custom Timesteps
            "mp3",            # Audio Format
            0.9,              # LM Temperature
            True,             # Think (chain-of-thought)
            1.0,              # LM CFG Scale
            250,              # LM Top-K
            0.95,             # LM Top-P
            "",               # LM Negative Prompt
            True,             # CoT Metas
            True,             # CaptionRewrite
            True,             # CoT Language
            False,            # Constrained Decoding Debug
            False,            # ParallelThinking
            False,            # Auto Score
            False,            # Auto LRC
            0.5,              # Quality Score Sensitivity
            1,                # LM Batch Chunk Size
            "",               # Track Name
            "",               # Track Names
            True,             # Enable Normalization
            -1.0,             # Target Peak (dB)
            0.0,              # Latent Shift
            1.0,              # Latent Rescale
            False,            # AutoGen
        ]
    }).encode()

    req = urllib.request.Request(
        f"{ACESTEP_API}/gradio_api/call/generation_wrapper",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        print(f"  Submitting generation ({duration}s, {batch_size} variants)...", file=sys.stderr)
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            event_id = result.get("event_id")
            if not event_id:
                print(f"  [ERROR] No event_id: {result}", file=sys.stderr)
                return []
    except (urllib.error.URLError, OSError) as e:
        print(f"  [ERROR] Submit failed: {e}", file=sys.stderr)
        return []

    # Poll for result via SSE stream
    print(f"  Generation started (event {event_id}), waiting...", file=sys.stderr)
    try:
        poll_req = urllib.request.Request(
            f"{ACESTEP_API}/gradio_api/call/generation_wrapper/{event_id}",
            method="GET",
        )
        with urllib.request.urlopen(poll_req, timeout=600) as resp:
            # SSE stream — read line by line
            data_lines = []
            for raw_line in resp:
                line = raw_line.decode().strip()
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    if data_str:
                        data_lines.append(data_str)
                        # Check for progress updates
                        try:
                            parsed = json.loads(data_str)
                            if isinstance(parsed, list):
                                # Final result — extract audio file paths
                                return _extract_audio_paths(parsed)
                        except json.JSONDecodeError:
                            pass

            # Try the last data line as the result
            if data_lines:
                try:
                    parsed = json.loads(data_lines[-1])
                    if isinstance(parsed, list):
                        return _extract_audio_paths(parsed)
                except json.JSONDecodeError:
                    pass

    except (urllib.error.URLError, OSError) as e:
        print(f"  [ERROR] Polling failed: {e}", file=sys.stderr)

    return []


def _extract_audio_paths(result_data: list) -> list[Path]:
    """Extract audio file paths from Gradio result data.

    Gradio returns results as a list where audio outputs are dicts with 'path' keys
    or tuples with file paths.
    """
    paths = []
    for item in result_data:
        if isinstance(item, dict) and "path" in item:
            p = Path(item["path"])
            if p.exists() and p.suffix in (".mp3", ".wav", ".flac"):
                paths.append(p)
        elif isinstance(item, (tuple, list)):
            for sub in item:
                if isinstance(sub, dict) and "path" in sub:
                    p = Path(sub["path"])
                    if p.exists() and p.suffix in (".mp3", ".wav", ".flac"):
                        paths.append(p)
                elif isinstance(sub, str) and Path(sub).exists():
                    p = Path(sub)
                    if p.suffix in (".mp3", ".wav", ".flac"):
                        paths.append(p)
        elif isinstance(item, str) and Path(item).exists():
            p = Path(item)
            if p.suffix in (".mp3", ".wav", ".flac"):
                paths.append(p)
    return paths


def save_audio_from_paths(source_paths: list[Path], output_dir: Path, show_date: str) -> list[Path]:
    """Copy generated audio files to our song-of-the-day directory."""
    import shutil
    output_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for i, src in enumerate(source_paths):
        dst = output_dir / f"sotd-{show_date}-v{i+1}{src.suffix}"
        shutil.copy2(str(src), str(dst))
        saved.append(dst)
        print(f"  Saved variant {i+1}: {dst.name}", file=sys.stderr)
    return saved


def generate_song_of_the_day(show_date: str = None, genre_override: str = None,
                              duration: int = DEFAULT_DURATION) -> Path | None:
    """Main entry: generate today's song of the day.

    Returns path to the best variant, or None on failure.
    """
    show_date = show_date or date.today().isoformat()

    # Check if already generated today
    existing = list(SONG_DIR.glob(f"sotd-{show_date}-*.mp3"))
    if existing:
        best = existing[0]  # Use first variant (or implement selection later)
        print(f"  Song of the day already exists: {best.name}", file=sys.stderr)
        return best

    # Check API
    if not check_api():
        print("  [ERROR] ACE-Step API not reachable at " + ACESTEP_API, file=sys.stderr)
        print("  Start ACE-Step in Pinokio first.", file=sys.stderr)
        return None

    # Pick genre
    if genre_override:
        # Find matching genre or use as raw caption
        matched = [(c, n) for c, n in GENRE_PALETTE if genre_override.lower() in n.lower()]
        if matched:
            caption, genre_name = matched[0]
        else:
            caption = f"{genre_override} instrumental, rich arrangement, professional production"
            genre_name = genre_override
    else:
        caption, genre_name = pick_genre(show_date)

    print(f"  Genre: {genre_name}", file=sys.stderr)
    print(f"  Caption: {caption[:80]}...", file=sys.stderr)

    # Generate
    audio_paths = generate_song(caption, duration=duration, batch_size=2)
    if not audio_paths:
        print("  [ERROR] No audio generated", file=sys.stderr)
        return None

    # Copy to our directory
    saved = save_audio_from_paths(audio_paths, SONG_DIR, show_date)
    if not saved:
        print("  [ERROR] No audio files saved", file=sys.stderr)
        return None

    # Save metadata
    meta = {
        "date": show_date,
        "genre": genre_name,
        "caption": caption,
        "duration_requested": duration,
        "variants": [str(p.name) for p in saved],
    }
    meta_path = SONG_DIR / f"sotd-{show_date}-meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))

    best = saved[0]
    print(f"  Song of the day: {best.name} ({genre_name})", file=sys.stderr)
    return best


def main():
    parser = argparse.ArgumentParser(description="Killen Time — Song of the Day Generator")
    parser.add_argument("--date", help="Show date (YYYY-MM-DD)")
    parser.add_argument("--genre", help="Force a genre (e.g., 'jazz', 'synthwave')")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION, help="Duration in seconds (default: 120)")
    args = parser.parse_args()

    result = generate_song_of_the_day(
        show_date=args.date,
        genre_override=args.genre,
        duration=args.duration,
    )

    if result:
        print(f"OUTPUT: {result}")
    else:
        print("FAILED: No song generated", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
