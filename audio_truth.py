#!/usr/bin/env python3
"""Does this MP3 actually contain audio a listener can hear?

WHY (2026-10-01): every health surface in this repo has always asked "does the
file exist", never "does the file have audio in it". check-episode.sh reported
`OK: Episode published (6937 words)` by reading a word count off the SCRIPT and
confirming an MP3 path; watch-episode.sh stood down on `[ -f mp3 ]`. A mix that
produced silence, a truncated concat, or an empty upload therefore read green
everywhere, and the only signal it could ever produce was the pipeline's exit
code — which the launchd-exit alarm dedupes as "already reported".

This module answers the question those surfaces were really asking. It is
deliberately small and has two halves so the decision is testable without ffmpeg:

    assess(size, duration, mean_db)  -> pure. No I/O, no binaries.
    probe(mp3_path)                  -> measures with ffprobe + ffmpeg, then assess().

`assess` is where the thresholds live and it is what the tests exercise; `probe`
is the thin shell around it. CI (ubuntu-latest) has no ffmpeg, so nothing in the
test suite may require one.

Three independent failure modes, each of which has read as healthy until now:
  MISSING   — no file at all.
  EMPTY     — a file, but no audio frames: silent mix, empty upload.
  TRUNCATED — real audio, but far shorter than the script that produced it.

CLI:  python3 audio_truth.py FILE.mp3   -> exit 0 healthy, 1 not, prints verdict.
Kill switch: AUDIO_TRUTH_CHECK=0 makes the CLI (and `probe_ok()`) pass without
measuring, for the rare case where ffmpeg is missing on a box that is otherwise fine.
"""
import os
import re
import subprocess
import sys

from config import FFMPEG

FFPROBE = "/opt/homebrew/bin/ffprobe"

# A show is long: MIN_WORD_COUNT words at ~150 wpm is ~40 minutes. These floors
# sit far BELOW a real episode on purpose — this gate exists to catch silence and
# truncation, not to grade length. A false block here costs Kyle an episode, so
# every threshold has a wide margin to the nearest real value (the 2026-10-01
# rescue measured 41.8 MB / 2539 s / -16.8 dB).
MIN_BYTES = 1_000_000        # a real episode is ~40 MB; 1 MB is ~25 seconds
MIN_SECONDS = 600            # 10 minutes; the floor script is ~40
SILENCE_DB = -60.0           # digital silence measures -91 dB; speech ~-17 dB

# ffmpeg prints volume like "mean_volume: -16.8 dB" / "mean_volume: -91.0 dB".
_VOLUME_RE = re.compile(r"mean_volume:\s*(-?[\d.]+|-\w+)\s*dB")


def assess(size_bytes, duration_secs, mean_db):
    """Decide whether a measured MP3 is worth publishing. Pure function.

    Returns (ok: bool, reason: str, detail: str). Each reason names the failure
    class so a caller can distinguish "nothing rendered" from "rendered but
    silent" without parsing prose.
    """
    if size_bytes is None or duration_secs is None or mean_db is None:
        return False, "UNPROBEABLE", "could not measure the file (ffprobe/ffmpeg missing or failed)"
    if size_bytes < MIN_BYTES:
        return False, "EMPTY", f"{size_bytes:,} bytes is under the {MIN_BYTES:,}-byte floor — audio frames are missing"
    if duration_secs < MIN_SECONDS:
        return False, "TRUNCATED", f"{duration_secs:.0f}s is under the {MIN_SECONDS}s floor — the render or the mix cut off early"
    if mean_db < SILENCE_DB:
        return False, "SILENT", f"mean volume {mean_db:.1f} dB is at or below the {SILENCE_DB} dB floor — the file is inaudible"
    return True, "OK", f"{size_bytes:,} bytes, {duration_secs:.0f}s, mean {mean_db:.1f} dB"


def _duration(path):
    try:
        out = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30,
        )
        return float(out.stdout.strip())
    except Exception:
        return None


def _mean_db(path):
    """Mean volume over the whole file. ~3s for a 42-minute episode.

    Whole file, not a head sample: the failure this catches is a mix that
    concatenated some segments and not others, which a head-only probe reads as
    healthy because the head is fine.
    """
    try:
        out = subprocess.run(
            [FFMPEG, "-hide_banner", "-nostats", "-i", path,
             "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True, timeout=300,
        )
        m = _VOLUME_RE.search(out.stderr)
        if not m:
            return None
        raw = m.group(1)
        # ffmpeg writes "-inf dB" for true digital silence.
        return float("-inf") if raw in ("-inf", "-infinity") else float(raw)
    except Exception:
        return None


def probe(mp3_path):
    """Measure an MP3 and return assess()'s (ok, reason, detail)."""
    if not mp3_path or not os.path.isfile(mp3_path):
        return False, "MISSING", f"no file at {mp3_path}"
    try:
        size = os.path.getsize(mp3_path)
    except OSError as e:
        return False, "UNPROBEABLE", f"cannot stat {mp3_path}: {e}"
    return assess(size, _duration(mp3_path), _mean_db(mp3_path))


def probe_ok(mp3_path):
    """probe() as a boolean, honoring the AUDIO_TRUTH_CHECK=0 kill switch."""
    if os.getenv("AUDIO_TRUTH_CHECK") == "0":
        return True
    return probe(mp3_path)[0]


def main():
    if len(sys.argv) != 2:
        print("usage: audio_truth.py FILE.mp3", file=sys.stderr)
        return 2
    if os.getenv("AUDIO_TRUTH_CHECK") == "0":
        print("audio-truth: SKIPPED — AUDIO_TRUTH_CHECK=0, audio not measured")
        return 0
    ok, reason, detail = probe(sys.argv[1])
    print(f"audio-truth: {reason} — {detail}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
