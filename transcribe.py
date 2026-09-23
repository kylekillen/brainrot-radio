#!/usr/bin/env python3
"""Brainrot Radio v0.2 — Audio Transcription Module.

Shared local transcription engine for podcast.py, twitch.py, and Code Voice.
Parakeet TDT is the primary engine; Whisper remains a deliberately kept
fallback for unusual audio and for environments where Parakeet cannot load.

Usage:
    python3 transcribe.py audio.mp3                # Transcribe file
    python3 transcribe.py audio.mp3 --max-minutes 30  # Truncate first
"""

import argparse
import hashlib
import subprocess
import sys
import threading
from pathlib import Path

from config import FFMPEG, TEMP_DIR

# ── Constants ─────────────────────────────────────────────────────
PRIMARY_MODEL = "mlx-community/parakeet-tdt-0.6b-v3"
FALLBACK_MODEL = "mlx-community/whisper-large-v3-turbo"
# Keep MODEL as the public/default name for existing callers and the CLI.
MODEL = PRIMARY_MODEL
CACHE_DIR = TEMP_DIR / "transcripts"

# Both MLX runtimes keep mutable model state. Serialize inference and model
# loading across the podcast workers and the resident Code Voice server.
_INFERENCE_LOCK = threading.Lock()
_MODEL_CACHE = {}


def audio_hash(audio_path):
    """Fast hash of audio file for cache keying."""
    h = hashlib.sha256()
    path = Path(audio_path)
    # Hash first 1MB + file size for speed
    with open(path, "rb") as f:
        h.update(f.read(1024 * 1024))
    h.update(str(path.stat().st_size).encode())
    return h.hexdigest()[:16]


def truncate_audio(audio_path, max_minutes, output_path=None):
    """Truncate audio to first N minutes using ffmpeg. Returns output path."""
    audio_path = Path(audio_path)
    if output_path is None:
        output_path = audio_path.with_suffix(f".trunc{max_minutes}m.mp3")
    output_path = Path(output_path)

    if output_path.exists():
        return output_path

    duration_secs = max_minutes * 60
    cmd = [
        FFMPEG, "-y",
        "-i", str(audio_path),
        "-t", str(duration_secs),
        "-acodec", "libmp3lame",
        "-ar", "16000",       # Whisper expects 16kHz
        "-ac", "1",           # Mono
        "-q:a", "5",          # Reasonable quality
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"  [WARN] ffmpeg truncation failed: {result.stderr[:200]}", file=sys.stderr)
        return audio_path  # Fall back to full file

    return output_path


def _result_text(result):
    """Return plain text from either supported MLX result shape.

    Whisper returns a mapping with ``text``/``segments``; Parakeet returns
    ``AlignedResult`` with ``text``/``sentences``. Keeping this adapter in one
    place prevents callers from having to know which engine ran.
    """
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, dict):
        return (result.get("text") or "").strip()
    return (getattr(result, "text", "") or "").strip()


def _load_model(model):
    """Load and retain one model per engine, under the shared MLX lock."""
    if model in _MODEL_CACHE:
        return _MODEL_CACHE[model]
    if model == PRIMARY_MODEL:
        from mlx_audio.stt import load
        loaded = load(model)
    else:
        # Import lazily so installations that only use the fallback do not pay
        # the Whisper import cost on the primary path.
        import mlx_whisper
        loaded = mlx_whisper
    _MODEL_CACHE[model] = loaded
    return loaded


def _run_model(audio_path, model):
    """Run one engine and normalize its result to text."""
    audio_path = str(audio_path)
    if model == PRIMARY_MODEL:
        engine = _load_model(model)
        result = engine.generate(audio_path, chunk_duration=30.0)
    else:
        engine = _load_model(model)
        result = engine.transcribe(
            audio_path,
            path_or_hf_repo=model,
            language="en",
        )
    return _result_text(result)


def transcribe(audio_path, model=MODEL):
    """Transcribe an audio file locally, with Whisper as a safety fallback.

    Parakeet is the primary path. A failure to load or run it is logged and
    retried once with the already-cached Whisper model; a failure of both is
    raised rather than silently returning an empty transcript.
    """
    audio_path = str(audio_path)
    with _INFERENCE_LOCK:
        if model == PRIMARY_MODEL:
            print(f"  Transcribing with Parakeet ({model})...", file=sys.stderr)
            try:
                text = _run_model(audio_path, model)
            except Exception as exc:  # noqa: BLE001
                print(
                    f"  [WARN] Parakeet failed ({exc}); falling back to Whisper",
                    file=sys.stderr,
                )
                text = _run_model(audio_path, FALLBACK_MODEL)
        else:
            print(f"  Transcribing with Whisper ({model})...", file=sys.stderr)
            text = _run_model(audio_path, model)

    print(f"  → {len(text)} chars transcribed", file=sys.stderr)
    return text


def cached_transcribe(audio_path, cache_key=None, max_minutes=None, model=MODEL):
    """Transcribe with filesystem cache. Returns cached text if available.

    Args:
        audio_path: Path to audio file
        cache_key: Optional cache key (defaults to file hash)
        max_minutes: If set, truncate audio before transcription
        model: Whisper model to use
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if cache_key is None:
        cache_key = audio_hash(audio_path)

    cache_file = CACHE_DIR / f"{cache_key}.txt"

    # Return cached if exists
    if cache_file.exists():
        text = cache_file.read_text(encoding="utf-8").strip()
        if text:
            print(f"  Cache hit: {cache_key} ({len(text)} chars)", file=sys.stderr)
            return text

    # Truncate if needed
    work_path = Path(audio_path)
    if max_minutes:
        trunc_dir = TEMP_DIR / "truncated"
        trunc_dir.mkdir(parents=True, exist_ok=True)
        trunc_path = trunc_dir / f"{cache_key}.mp3"
        work_path = truncate_audio(audio_path, max_minutes, trunc_path)

    # Transcribe
    text = transcribe(work_path, model=model)

    # Cache result
    if text:
        cache_file.write_text(text, encoding="utf-8")

    return text


def main():
    parser = argparse.ArgumentParser(description="Brainrot Radio — Audio Transcription")
    parser.add_argument("audio", help="Path to audio file")
    parser.add_argument("--max-minutes", type=int, help="Truncate to first N minutes")
    parser.add_argument(
        "--model",
        default=MODEL,
        help=f"Parakeet/Whisper model (default: {MODEL}; fallback: {FALLBACK_MODEL})",
    )
    parser.add_argument("--no-cache", action="store_true", help="Skip cache")
    args = parser.parse_args()

    audio_path = Path(args.audio)
    if not audio_path.exists():
        print(f"File not found: {audio_path}", file=sys.stderr)
        sys.exit(1)

    if args.no_cache:
        text = transcribe(audio_path, model=args.model)
    else:
        text = cached_transcribe(
            audio_path,
            max_minutes=args.max_minutes,
            model=args.model,
        )

    if text:
        print(text)
    else:
        print("No transcription produced.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
