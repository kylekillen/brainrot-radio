#!/usr/bin/env python3
"""Brainrot Radio v0.3 — TTS Voice Rendering (Kokoro MLX + Edge TTS fallback).

Usage:
    python3 voice.py scripts/killen-time-2026-03-03.txt
    python3 voice.py scripts/killen-time-2026-03-03.txt --engine edge
    python3 voice.py scripts/killen-time-2026-03-03.txt --output-dir .tmp/segments
"""

import argparse
import asyncio
import re
import subprocess
import sys
from pathlib import Path

from config import FFMPEG, KOKORO_VOICES, MIN_WORD_COUNT, TARGET_WORD_COUNT, TEMP_DIR, TTS_ENGINE, VOICES


def parse_script(script_path):
    """Parse a show script into [(speaker, text)] segments.

    Format:
        [BASIL] Hey everyone, welcome to Killen Time.
        [BROOKE] Today we're covering the latest in AI.
        [TRANSITION]
        [BASIL] Our first story...
    """
    segments = []
    current_speaker = None
    current_lines = []

    with open(script_path) as f:
        for line in f:
            line = line.rstrip()

            # Match speaker tags: [BASIL], [BROOKE], [TRANSITION]
            match = re.match(r"^\[(\w+)\]\s*(.*)", line)
            if match:
                # Save previous segment
                if current_speaker and current_lines:
                    text = " ".join(current_lines).strip()
                    if text:
                        segments.append((current_speaker, text))

                tag = match.group(1).upper()
                rest = match.group(2).strip()

                if tag == "TRANSITION":
                    segments.append(("TRANSITION", ""))
                    current_speaker = None
                    current_lines = []
                else:
                    current_speaker = tag
                    current_lines = [rest] if rest else []
            elif current_speaker and line.strip():
                current_lines.append(line.strip())

    # Don't forget the last segment
    if current_speaker and current_lines:
        text = " ".join(current_lines).strip()
        if text:
            segments.append((current_speaker, text))

    return segments


# ── Kokoro TTS (local MLX) ─────────────────────────────────────────

_kokoro_model = None


def _get_kokoro_model():
    """Lazy-load Kokoro model (only imported when needed)."""
    global _kokoro_model
    if _kokoro_model is None:
        from mlx_audio.tts.utils import load_model
        print("  Loading Kokoro TTS model...", file=sys.stderr)
        _kokoro_model = load_model("mlx-community/Kokoro-82M-bf16")
    return _kokoro_model


def render_segment_kokoro(speaker, text, output_path):
    """Render a single text segment to WAV using Kokoro, then convert to MP3."""
    import numpy as np
    import soundfile as sf

    model = _get_kokoro_model()
    cfg = KOKORO_VOICES[speaker]

    wav_path = output_path.with_suffix(".wav")

    # Kokoro generates in chunks — collect ALL chunks and concatenate
    audio_chunks = []
    sample_rate = None
    for result in model.generate(text, voice=cfg["voice"], lang_code=cfg["lang_code"]):
        audio_chunks.append(result.audio)
        sample_rate = result.sample_rate

    if not audio_chunks:
        print(f"  [WARN] No audio generated for segment", file=sys.stderr)
        return

    full_audio = np.concatenate(audio_chunks)
    sf.write(str(wav_path), full_audio, sample_rate)

    # Convert WAV to MP3
    subprocess.run(
        [
            FFMPEG, "-y",
            "-i", str(wav_path),
            "-c:a", "libmp3lame", "-b:a", "128k",
            str(output_path),
        ],
        capture_output=True,
        check=True,
    )
    wav_path.unlink(missing_ok=True)


def render_all_kokoro(segments, output_dir):
    """Render all segments using Kokoro TTS."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Clean out stale segments
    for old_file in output_dir.glob("seg_*.mp3"):
        old_file.unlink()

    segment_files = []
    segment_idx = 0

    for speaker, text in segments:
        if speaker == "TRANSITION":
            segment_files.append(("TRANSITION", None))
            continue

        if speaker not in KOKORO_VOICES:
            print(f"  [WARN] Unknown speaker '{speaker}', skipping segment", file=sys.stderr)
            continue

        filename = f"seg_{segment_idx:03d}_{speaker.lower()}.mp3"
        output_path = output_dir / filename
        print(f"  Rendering {filename} ({len(text)} chars)...", file=sys.stderr)

        render_segment_kokoro(speaker, text, output_path)
        segment_files.append((speaker, output_path))
        segment_idx += 1

    return segment_files


# ── Edge TTS (fallback) ───────────────────────────────────────────

async def render_segment_edge(speaker, text, output_path, voice_config):
    """Render a single text segment to MP3 using Edge TTS."""
    import edge_tts

    cfg = voice_config[speaker]
    communicate = edge_tts.Communicate(
        text,
        voice=cfg["voice"],
        rate=cfg["rate"],
        pitch=cfg["pitch"],
    )
    await communicate.save(str(output_path))


async def render_all_edge(segments, output_dir, voice_config):
    """Render all segments to individual MP3 files using Edge TTS."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Clean out stale segments
    for old_file in output_dir.glob("seg_*.mp3"):
        old_file.unlink()

    segment_files = []
    segment_idx = 0

    for speaker, text in segments:
        if speaker == "TRANSITION":
            segment_files.append(("TRANSITION", None))
            continue

        if speaker not in voice_config:
            print(f"  [WARN] Unknown speaker '{speaker}', skipping segment", file=sys.stderr)
            continue

        filename = f"seg_{segment_idx:03d}_{speaker.lower()}.mp3"
        output_path = output_dir / filename
        print(f"  Rendering {filename} ({len(text)} chars)...", file=sys.stderr)

        await render_segment_edge(speaker, text, output_path, voice_config)
        segment_files.append((speaker, output_path))
        segment_idx += 1

    return segment_files


# ── Main entry point ─────────────────────────────────────────────

def render_script(script_path, output_dir=None, engine=None):
    """Main entry point: parse script and render all segments."""
    engine = engine or TTS_ENGINE

    segments = parse_script(script_path)
    if not segments:
        print("No segments found in script.", file=sys.stderr)
        return []

    speech_segments = [(s, t) for s, t in segments if s != "TRANSITION"]
    word_count = sum(len(t.split()) for _, t in speech_segments)
    print(f"Parsed {len(segments)} segments ({len(speech_segments)} speech, ~{word_count} words)", file=sys.stderr)
    print(f"TTS engine: {engine}", file=sys.stderr)

    # Hard gate: refuse to render scripts that are too short
    if word_count < MIN_WORD_COUNT:
        est_minutes = round(word_count / 150)
        target_minutes = round(TARGET_WORD_COUNT / 150)
        print(
            f"\n{'='*60}\n"
            f"SCRIPT TOO SHORT — RENDERING BLOCKED\n"
            f"  Word count: {word_count:,} (minimum: {MIN_WORD_COUNT:,})\n"
            f"  Estimated duration: ~{est_minutes} min (target: ~{target_minutes} min)\n"
            f"  Shortfall: {MIN_WORD_COUNT - word_count:,} words\n"
            f"\n"
            f"  Expand the script before rendering. Add more stories,\n"
            f"  deeper analysis, or additional transcript coverage.\n"
            f"{'='*60}",
            file=sys.stderr,
        )
        sys.exit(1)

    if output_dir is None:
        output_dir = TEMP_DIR / "segments"

    if engine == "kokoro":
        segment_files = render_all_kokoro(segments, output_dir)
    else:
        segment_files = asyncio.run(render_all_edge(segments, output_dir, VOICES))

    speech_rendered = sum(1 for s, _ in segment_files if s != "TRANSITION")
    print(f"Rendered {speech_rendered} audio files.", file=sys.stderr)

    # Archive all source files after successful render so they can't
    # feed the next episode — works regardless of invocation method
    try:
        from ingest import archive_all_sources
        archived = archive_all_sources()
        if archived:
            print(f"Post-render: archived {archived} source files.", file=sys.stderr)
    except Exception as e:
        print(f"  [WARN] Source archiving failed: {e}", file=sys.stderr)

    return segment_files


def main():
    parser = argparse.ArgumentParser(description="Killen Time TTS Renderer")
    parser.add_argument("script", help="Path to show script (.txt)")
    parser.add_argument("--output-dir", help="Directory for segment MP3s")
    parser.add_argument("--engine", choices=["kokoro", "edge"], help="TTS engine (default: from config)")
    args = parser.parse_args()

    if not Path(args.script).exists():
        print(f"Script not found: {args.script}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir) if args.output_dir else None
    segment_files = render_script(args.script, output_dir, engine=args.engine)

    # Print manifest
    for speaker, path in segment_files:
        if speaker == "TRANSITION":
            print("TRANSITION")
        else:
            print(f"{speaker}: {path}")


if __name__ == "__main__":
    main()
