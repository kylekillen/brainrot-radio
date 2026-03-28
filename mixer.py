#!/usr/bin/env python3
"""Brainrot Radio v0.2 — Audio Mixing & Normalization.

Usage:
    python3 mixer.py                          # Mix today's segments
    python3 mixer.py --date 2026-03-02        # Mix a specific date
    python3 mixer.py --segments-dir .tmp/segments --output test.mp3
    python3 mixer.py --artwork assets/episode-artwork/artwork-2026-03-03.jpg
"""

import argparse
import hashlib
import subprocess
import sys
from datetime import date
from pathlib import Path

from config import ASSETS_DIR, FFMPEG, LOUDNORM_PARAMS, OUTPUT_DIR, SHOW_NAME, TEMP_DIR

MUSIC_DIR = ASSETS_DIR / "music"


def generate_silence(duration_ms, output_path):
    """Generate a silence MP3 of given duration."""
    subprocess.run(
        [
            FFMPEG, "-y", "-f", "lavfi",
            "-i", f"anullsrc=r=24000:cl=mono",
            "-t", str(duration_ms / 1000),
            "-c:a", "libmp3lame", "-b:a", "48k",
            str(output_path),
        ],
        capture_output=True,
        check=True,
    )


def _pick_clip(category: str, seed: str) -> Path | None:
    """Pick a deterministic-random clip from assets/music/{category}/."""
    clip_dir = MUSIC_DIR / category
    if not clip_dir.exists():
        return None
    clips = sorted(clip_dir.glob("*.mp3"))
    if not clips:
        return None
    idx = int(hashlib.md5(f"{seed}-{category}".encode()).hexdigest(), 16) % len(clips)
    return clips[idx]


def ensure_assets():
    """Generate silence fallbacks if music library is missing."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    transition = ASSETS_DIR / "transition.mp3"
    if not transition.exists():
        print("  Generating transition stinger (0.8s silence)...", file=sys.stderr)
        generate_silence(800, transition)

    intro_silence = ASSETS_DIR / "intro_pad.mp3"
    if not intro_silence.exists():
        print("  Generating intro pad (0.5s silence)...", file=sys.stderr)
        generate_silence(500, intro_silence)

    outro_silence = ASSETS_DIR / "outro_pad.mp3"
    if not outro_silence.exists():
        print("  Generating outro pad (1s silence)...", file=sys.stderr)
        generate_silence(1000, outro_silence)


def build_concat_list(segment_files, concat_file_path, show_date=None):
    """Write FFmpeg concat demuxer file from segment list.

    Transition stingers go between segments via concat.
    Intro/outro music is handled separately with crossfading in mix_segments().
    """
    ensure_assets()

    transition_clip = _pick_clip("transition", show_date or date.today().isoformat()) or ASSETS_DIR / "transition.mp3"
    gap_pad = ASSETS_DIR / "intro_pad.mp3"  # 0.5s silence between speech segments

    with open(concat_file_path, "w") as f:
        for i, (speaker, path) in enumerate(segment_files):
            if speaker == "TRANSITION":
                f.write(f"file '{transition_clip}'\n")
            elif path and path.exists():
                f.write(f"file '{path}'\n")
                # Add tiny gap between consecutive speech segments
                if i + 1 < len(segment_files) and segment_files[i + 1][0] != "TRANSITION":
                    f.write(f"file '{gap_pad}'\n")


def _get_duration(path):
    """Get audio duration in seconds."""
    probe = subprocess.run(
        [FFMPEG, "-i", str(path), "-hide_banner"],
        capture_output=True, text=True,
    )
    duration_lines = [l for l in probe.stderr.split("\n") if "Duration:" in l]
    if not duration_lines:
        return 0
    parts = duration_lines[0].strip().split(",")[0].replace("Duration: ", "").split(":")
    return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])


def _crossfade_intro(speech_path, intro_clip, output_path):
    """Overlay intro music under the beginning of speech, fading music out.

    Music plays alone for 2 seconds, then speech fades in over 1 second.
    Music fades out smoothly over its last 3 seconds (or half its duration if short).
    """
    music_dur = _get_duration(intro_clip)
    if music_dur <= 0:
        return False

    # Music plays alone for 2s, then speech starts
    speech_delay_ms = 2000
    # Fade out music over last 3s (or half the clip if it's very short)
    fade_dur = min(3.0, music_dur * 0.5)
    fade_start = max(0, music_dur - fade_dur)

    result = subprocess.run(
        [
            FFMPEG, "-y",
            "-i", str(speech_path),   # input 0: speech
            "-i", str(intro_clip),    # input 1: intro music
            "-filter_complex",
            # Music: duck volume, fade out smoothly before it ends
            f"[1:a]volume=0.20,afade=t=out:st={fade_start:.1f}:d={fade_dur:.1f}[music];"
            # Speech: delay start by 2s so music plays alone first
            f"[0:a]adelay={speech_delay_ms}|{speech_delay_ms}[speech];"
            # Mix with normalize=0 so speech stays at full volume
            "[speech][music]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0[out]",
            "-map", "[out]",
            "-c:a", "libmp3lame", "-b:a", "128k",
            str(output_path),
        ],
        capture_output=True,
    )
    return result.returncode == 0


def _crossfade_outro(speech_path, outro_clip, output_path):
    """Fade outro music in under the end of speech, then let it play out."""
    speech_dur = _get_duration(speech_path)
    if speech_dur <= 0:
        return False

    # Start outro music 5 seconds before speech ends, fade in over 3s
    music_start = max(0, speech_dur - 5)
    result = subprocess.run(
        [
            FFMPEG, "-y",
            "-i", str(speech_path),   # input 0: speech
            "-i", str(outro_clip),    # input 1: outro music
            "-filter_complex",
            # Delay music to start near end of speech, fade in, then play full
            f"[1:a]volume=0.25,afade=t=in:st=0:d=3,adelay={int(music_start*1000)}|{int(music_start*1000)}[music];"
            # Mix: let it run for speech duration + outro music duration
            "[0:a][music]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0[out]",
            "-map", "[out]",
            "-c:a", "libmp3lame", "-b:a", "128k",
            str(output_path),
        ],
        capture_output=True,
    )
    return result.returncode == 0


def mix_segments(segment_files, output_path, show_date=None, artwork_path=None, song_of_the_day=None):
    """Concatenate segments with music, normalize loudness, optionally embed artwork.

    Music handling:
    - Intro: lo-fi music plays under the first few seconds of speech, fading out
    - Transitions: stinger clips between segments (via concat)
    - Outro: lo-fi music fades in under last 5s of speech, then plays out
    - Song of the Day: featured instrumental appended after outro (full volume)
    """
    if not segment_files:
        print("No segments to mix.", file=sys.stderr)
        return False

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    seed = show_date or date.today().isoformat()
    intro_clip = _pick_clip("intro", seed)
    outro_clip = _pick_clip("outro", seed)

    concat_file = TEMP_DIR / "concat.txt"
    raw_concat = TEMP_DIR / "raw_concat.mp3"

    if intro_clip or outro_clip:
        print(f"  Music: intro={intro_clip.name if intro_clip else 'none'}, "
              f"outro={outro_clip.name if outro_clip else 'none'}", file=sys.stderr)

    # Build concat list (speech + transition stingers only)
    build_concat_list(segment_files, concat_file, show_date)

    # Step 1: Concatenate speech + transitions
    print("  Concatenating segments...", file=sys.stderr)
    result = subprocess.run(
        [
            FFMPEG, "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c:a", "libmp3lame", "-b:a", "128k",
            str(raw_concat),
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        print(f"  [ERROR] Concat failed: {result.stderr.decode()[-500:]}", file=sys.stderr)
        return False

    # Step 2: Crossfade intro music under beginning of speech
    current = raw_concat
    if intro_clip:
        intro_mixed = TEMP_DIR / "intro_mixed.mp3"
        print("  Crossfading intro music...", file=sys.stderr)
        if _crossfade_intro(current, intro_clip, intro_mixed):
            current = intro_mixed
        else:
            print("  [WARN] Intro crossfade failed, continuing without", file=sys.stderr)

    # Step 3: Crossfade outro music under end of speech
    if outro_clip:
        outro_mixed = TEMP_DIR / "outro_mixed.mp3"
        print("  Crossfading outro music...", file=sys.stderr)
        if _crossfade_outro(current, outro_clip, outro_mixed):
            current = outro_mixed
        else:
            print("  [WARN] Outro crossfade failed, continuing without", file=sys.stderr)

    # Step 4: Append Song of the Day (featured instrumental closer)
    if song_of_the_day and Path(song_of_the_day).exists():
        print(f"  Appending Song of the Day: {Path(song_of_the_day).name}", file=sys.stderr)
        sotd_mixed = TEMP_DIR / "with_sotd.mp3"
        # Add 2s silence gap, then the song at full volume
        result = subprocess.run(
            [
                FFMPEG, "-y",
                "-i", str(current),
                "-i", str(song_of_the_day),
                "-filter_complex",
                # 2-second silence gap between show and song
                "[0:a]apad=pad_dur=2[show];"
                "[show][1:a]concat=n=2:v=0:a=1[out]",
                "-map", "[out]",
                "-c:a", "libmp3lame", "-b:a", "128k",
                str(sotd_mixed),
            ],
            capture_output=True,
        )
        if result.returncode == 0:
            current = sotd_mixed
        else:
            print(f"  [WARN] Song of the Day append failed, continuing without", file=sys.stderr)

    # Step 5: Loudness normalization + ID3 metadata
    show_date = show_date or date.today().isoformat()
    title = f"{SHOW_NAME} — {show_date}"

    print("  Normalizing loudness...", file=sys.stderr)
    result = subprocess.run(
        [
            FFMPEG, "-y",
            "-i", str(current),
            "-af", LOUDNORM_PARAMS,
            "-c:a", "libmp3lame", "-b:a", "128k",
            "-metadata", f"title={title}",
            "-metadata", f"artist={SHOW_NAME}",
            "-metadata", f"date={show_date}",
            "-metadata", f"album={SHOW_NAME}",
            str(output_path),
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        print(f"  [ERROR] Normalize failed: {result.stderr.decode()[-500:]}", file=sys.stderr)
        return False

    # Step 3: Embed artwork in ID3 if provided
    if artwork_path and Path(artwork_path).exists():
        print(f"  Embedding artwork: {artwork_path}", file=sys.stderr)
        artwork_output = TEMP_DIR / "with_artwork.mp3"
        result = subprocess.run(
            [
                FFMPEG, "-y",
                "-i", str(output_path),
                "-i", str(artwork_path),
                "-map", "0:a", "-map", "1",
                "-c", "copy",
                "-id3v2_version", "3",
                "-metadata:s:v", "title=Album cover",
                "-metadata:s:v", "comment=Cover (front)",
                str(artwork_output),
            ],
            capture_output=True,
        )
        if result.returncode == 0:
            artwork_output.replace(output_path)
        else:
            print(f"  [WARN] Artwork embedding failed, continuing without it", file=sys.stderr)
            artwork_output.unlink(missing_ok=True)

    # Get duration
    probe = subprocess.run(
        [
            FFMPEG, "-i", str(output_path),
            "-hide_banner",
        ],
        capture_output=True,
        text=True,
    )
    duration_line = [l for l in probe.stderr.split("\n") if "Duration:" in l]
    duration = duration_line[0].strip().split(",")[0] if duration_line else "unknown"

    print(f"  Output: {output_path} ({duration})", file=sys.stderr)

    # Cleanup temp files
    for tmp in [raw_concat, TEMP_DIR / "intro_mixed.mp3", TEMP_DIR / "outro_mixed.mp3", TEMP_DIR / "with_sotd.mp3"]:
        tmp.unlink(missing_ok=True)

    return True


def main():
    parser = argparse.ArgumentParser(description="Brainrot Radio Audio Mixer")
    parser.add_argument("--segments-dir", help="Directory containing segment MP3s")
    parser.add_argument("--output", "-o", help="Output MP3 path")
    parser.add_argument("--date", help="Show date (YYYY-MM-DD)")
    parser.add_argument("--artwork", help="Path to artwork JPG to embed in MP3 ID3 tags")
    parser.add_argument("--song-of-the-day", help="Path to instrumental MP3 to append as featured closer")
    args = parser.parse_args()

    segments_dir = Path(args.segments_dir) if args.segments_dir else TEMP_DIR / "segments"
    if not segments_dir.exists():
        print(f"Segments directory not found: {segments_dir}", file=sys.stderr)
        sys.exit(1)

    # Discover segment files in order
    segment_files = []
    for mp3 in sorted(segments_dir.glob("seg_*.mp3")):
        # Extract speaker from filename: seg_000_alex.mp3
        speaker = mp3.stem.split("_")[-1].upper()
        segment_files.append((speaker, mp3))

    if not segment_files:
        print("No segment files found.", file=sys.stderr)
        sys.exit(1)

    show_date = args.date or date.today().isoformat()
    output_path = Path(args.output) if args.output else OUTPUT_DIR / f"killen-time-{show_date}.mp3"

    success = mix_segments(segment_files, output_path, show_date, artwork_path=args.artwork,
                           song_of_the_day=args.song_of_the_day)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
