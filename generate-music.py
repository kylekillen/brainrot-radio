#!/usr/bin/env python3
"""
generate-music.py — One-time MusicGen MLX library generator for Killen Time.

Generates intro, transition, and outro music clips using MusicGen (MLX).
Run once to populate assets/music/, then clips are reused across episodes.

Usage:
    python3 generate-music.py                   # Generate full library
    python3 generate-music.py --type intro      # Only generate intros
    python3 generate-music.py --count 3         # 3 clips per category
    python3 generate-music.py --model facebook/musicgen-small  # Use small model
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

# MusicGen MLX lives in the vendored module
sys.path.insert(0, str(Path(__file__).parent / "musicgen_mlx"))

FFMPEG = "/opt/homebrew/bin/ffmpeg"
ASSETS_MUSIC = Path(__file__).parent / "assets" / "music"

# ── Clip Definitions ─────────────────────────────────────────────────────

CLIP_TYPES = {
    "intro": {
        "dir": "intro",
        "prompts": [
            "Lo-fi hip hop instrumental, warm vinyl crackle, mellow piano chords, soft boom bap drums, jazzy Rhodes, chill podcast intro, 10 seconds",
            "Chill lo-fi beat, dusty vinyl texture, smooth jazz piano, laid-back drums, warm bass, podcast background music, 12 seconds",
            "Lo-fi hip hop, relaxing jazzy chords, gentle kick and snare, vinyl hiss, mellow keys, podcast opener, 10 seconds",
            "Smooth lo-fi instrumental, warm analog synth pads, soft hip hop drums, jazz guitar sample, cozy vibes, 11 seconds",
            "Lo-fi chill hop, mellow Rhodes piano, tape saturation, relaxed boom bap beat, warm sub bass, podcast music, 10 seconds",
        ],
        "max_steps": 300,  # ~10-15 seconds at 32kHz / 50 tokens per sec
        "description": "10-15 second intro (lo-fi hip hop)",
    },
    "transition": {
        "dir": "transition",
        "prompts": [
            "Short lo-fi transition, soft vinyl crackle, gentle piano note, podcast break, 2 seconds",
            "Quick lo-fi beat drop, mellow drum fill, warm tape stop effect, clean, 3 seconds",
            "Soft jazzy chord stab, lo-fi texture, gentle podcast transition, 2 seconds",
            "Short lo-fi hip hop fill, vinyl noise, soft Rhodes chord, podcast segment break, 2 seconds",
            "Quick mellow transition, lo-fi crackle into soft piano, clean podcast break, 3 seconds",
        ],
        "max_steps": 100,  # ~2-4 seconds
        "description": "2-4 second transition stingers (lo-fi)",
    },
    "outro": {
        "dir": "outro",
        "prompts": [
            "Lo-fi hip hop outro, warm jazzy chords, gentle boom bap drums, vinyl crackle, slowly fading out, podcast ending, 12 seconds",
            "Chill lo-fi instrumental, mellow piano melody, soft drums fading, tape hiss, relaxing podcast close, 10 seconds",
            "Lo-fi hip hop, dreamy Rhodes chords, gentle bass, vinyl texture, winding down, fade to silence, 12 seconds",
            "Smooth lo-fi beat, warm analog pads, soft jazz piano, drums fading out, cozy podcast outro, 11 seconds",
            "Mellow lo-fi chill hop, jazzy guitar loop, gentle kick, vinyl warmth, podcast ending, fade out, 10 seconds",
        ],
        "max_steps": 300,  # ~10-15 seconds
        "description": "10-15 second outro music (lo-fi hip hop)",
    },
}


def wav_to_mp3(wav_path: Path, mp3_path: Path):
    """Convert WAV to MP3 at 128kbps."""
    subprocess.run(
        [FFMPEG, "-y", "-i", str(wav_path), "-c:a", "libmp3lame", "-b:a", "128k", str(mp3_path)],
        capture_output=True,
        check=True,
    )
    wav_path.unlink()


def generate_library(model_name: str, clip_type: str = None, count: int = 5):
    """Generate music clips using MusicGen MLX."""
    from musicgen import MusicGen
    from utils import save_audio

    print(f"Loading MusicGen model: {model_name}")
    t0 = time.time()
    model = MusicGen.from_pretrained(model_name)
    print(f"  Model loaded in {time.time() - t0:.1f}s")

    types_to_generate = [clip_type] if clip_type else list(CLIP_TYPES.keys())

    for ctype in types_to_generate:
        cfg = CLIP_TYPES[ctype]
        out_dir = ASSETS_MUSIC / cfg["dir"]
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n{'='*60}")
        print(f"Generating {ctype} clips ({cfg['description']})")
        print(f"  Output: {out_dir}")
        print(f"  Max steps: {cfg['max_steps']}")
        print(f"{'='*60}")

        prompts = cfg["prompts"][:count]
        for i, prompt in enumerate(prompts, 1):
            prefix = {"intro": "intro", "transition": "trans", "outro": "outro"}[ctype]
            wav_path = out_dir / f"{prefix}-{i:02d}.wav"
            mp3_path = out_dir / f"{prefix}-{i:02d}.mp3"

            if mp3_path.exists():
                print(f"  [{i}/{count}] {mp3_path.name} already exists, skipping")
                continue

            print(f"  [{i}/{count}] Generating {mp3_path.name}...")
            print(f"    Prompt: {prompt[:80]}...")
            t1 = time.time()

            audio = model.generate(prompt, max_steps=cfg["max_steps"])
            save_audio(str(wav_path), audio, model.sampling_rate)

            elapsed = time.time() - t1
            print(f"    Generated in {elapsed:.1f}s")

            # Convert to MP3
            wav_to_mp3(wav_path, mp3_path)
            print(f"    Saved: {mp3_path.name}")

    # Summary
    print(f"\n{'='*60}")
    print("Music library generation complete!")
    for ctype in types_to_generate:
        cfg = CLIP_TYPES[ctype]
        out_dir = ASSETS_MUSIC / cfg["dir"]
        clips = list(out_dir.glob("*.mp3"))
        print(f"  {ctype}: {len(clips)} clips in {out_dir}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Generate Killen Time music library")
    parser.add_argument("--model", default="facebook/musicgen-medium",
                        help="MusicGen model (default: facebook/musicgen-medium)")
    parser.add_argument("--type", choices=["intro", "transition", "outro"],
                        help="Only generate a specific clip type")
    parser.add_argument("--count", type=int, default=5,
                        help="Number of clips per category (default: 5)")
    args = parser.parse_args()

    generate_library(args.model, args.type, args.count)


if __name__ == "__main__":
    main()
