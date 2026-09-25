#!/usr/bin/env python3
"""covered_guard.py — write scripts/.covered-DATE.json from the FINAL, QC'd script.

Why (2026-09-25): the writers saved the covered ledger from their own draft, BEFORE
QC. QC then cut or rewrote the script, and the ledger kept listing stories that never
aired (72 entries; the final script had ~15 topics; 13 podcast guids, 9 of them for
episodes nobody read). The next morning's ingest hard-excludes every listed guid and
story, so a rejected draft silently suppressed fresh material.

Fix, in two halves:
  * generate-episode.sh exports COVERED_DEFER=1, so ingest.save_covered_stories() parks
    the writers' claim in .tmp/covered-pending-DATE.json (audit only) instead of the
    real ledger.
  * After the episode has actually been rendered and published, `commit` REPLACES
    today's ledger with what the final script provably contains:
      - segments: derived deterministically from the script's own text (no model call,
        so nothing can be invented);
      - podcast_guids: only transcripts the script demonstrably drew from (>= MIN_SHARED
        four-word phrases in common), never a guid the writer merely claimed.

    python3 covered_guard.py commit SCRIPT [--date YYYY-MM-DD]      # replace the ledger
    python3 covered_guard.py derive SCRIPT [--date YYYY-MM-DD]      # print, don't write
"""
import argparse
import json
import re
import sys
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = ROOT / "scripts"
TRANSCRIPT_DIRS = [ROOT / ".tmp" / "transcripts", ROOT / ".tmp" / "used"]

SHINGLE = 4
MIN_SHARED = 10          # 4-word phrases in common => the script used this transcript
                         # (measured 09-25: used episodes 22-87, unused <= 5)
RECENT_HOURS = 48        # .tmp/used holds old transcripts; only consider fresh ones
CHUNK_WORDS = 260        # one ledger entry per ~this many words of script

_TAG_RE = re.compile(r"^\[(BASIL|BROOKE|TRANSITION)\]\s*", re.MULTILINE)
_STOP = frozenset("""about after again also because been before being between both could
does doing during each even every from have having here into just like made make many more
most much only other over really same should since some still such than that their them
then there these they thing things this those through very want well were what when where
which while will with would your""".split())


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", s.lower())


def _shingles(words: list[str]) -> set[tuple]:
    return {tuple(words[i:i + SHINGLE]) for i in range(len(words) - SHINGLE + 1)}


def _segments(script_text: str) -> list[str]:
    """Spoken text in ~CHUNK_WORDS chunks, breaking at [TRANSITION] and block edges."""
    chunks, cur, n = [], [], 0
    for raw in re.split(r"\n\s*\n", script_text):
        raw = raw.strip()
        if not raw:
            continue
        if raw == "[TRANSITION]":
            if cur:
                chunks.append(" ".join(cur))
                cur, n = [], 0
            continue
        text = " ".join(_TAG_RE.sub("", raw, count=1).split())
        cur.append(text)
        n += len(text.split())
        if n >= CHUNK_WORDS:
            chunks.append(" ".join(cur))
            cur, n = [], 0
    if cur:
        chunks.append(" ".join(cur))
    return [c for c in chunks if len(c.split()) >= 30]


def _key_terms(chunk: str, k: int = 8) -> list[str]:
    """Most frequent proper nouns / numbers in the chunk — what a later writer should
    recognise as 'already said'. Sentence-initial words are ignored as proper nouns."""
    counts = Counter()
    for sent in re.split(r"(?<=[.!?])\s+", chunk):
        toks = sent.split()
        for i, t in enumerate(toks):
            t = t.strip(".,;:!?\"'()[]—-")
            if not t:
                continue
            if re.search(r"\d", t) or (i > 0 and t[0].isupper() and t.lower() not in _STOP):
                counts[t] += 1
    return [t for t, _ in counts.most_common(k)]


def _slug(terms: list[str], day: str, i: int) -> str:
    base = "-".join(re.sub(r"[^a-z0-9]+", "", t.lower()) for t in terms[:3] if t) or "segment"
    return f"{day}-s{i:02d}-{base}"[:80]


def derive_segments(script_text: str, day: str) -> dict:
    segs = {}
    for i, chunk in enumerate(_segments(script_text), 1):
        terms = _key_terms(chunk)
        opener = chunk[:230].rsplit(" ", 1)[0]
        segs[_slug(terms, day, i)] = f"{opener}... [terms: {', '.join(terms)}]"
    return segs


def used_guids(script_text: str, transcript_dirs=None, now: float | None = None) -> list[str]:
    """Guids of fresh transcripts the script demonstrably drew from."""
    dirs = TRANSCRIPT_DIRS if transcript_dirs is None else transcript_dirs
    now = time.time() if now is None else now
    script_sh = _shingles(_words(script_text))
    guids = []
    for d in dirs:
        for f in sorted(Path(d).glob("podcast_*.txt")):
            try:
                if now - f.stat().st_mtime > RECENT_HOURS * 3600:
                    continue
                shared = len(script_sh & _shingles(_words(f.read_text(errors="replace"))))
            except OSError:
                continue
            if shared >= MIN_SHARED:
                guids.append(f.stem[len("podcast_"):])
    return sorted(set(guids))


def derive(script_text: str, day: str, transcript_dirs=None) -> dict:
    segments = derive_segments(script_text, day)
    return {
        "stories": sorted(segments),
        "segments": segments,
        "podcast_guids": used_guids(script_text, transcript_dirs),
        "last_episode": datetime.now(timezone.utc).isoformat(),
        "derived_from": "final-script",
    }


def commit(script_path: Path, day: str, scripts_dir: Path = SCRIPTS_DIR, transcript_dirs=None) -> dict:
    """REPLACE the day's ledger with what the final script contains. Returns the data."""
    data = derive(Path(script_path).read_text(errors="replace"), day, transcript_dirs)
    out = Path(scripts_dir) / f".covered-{day}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(out)  # atomic: a reader never sees a half-written ledger
    return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["commit", "derive"])
    ap.add_argument("script")
    ap.add_argument("--date", default=date.today().isoformat())
    a = ap.parse_args(argv)
    if a.cmd == "derive":
        print(json.dumps(derive(Path(a.script).read_text(errors="replace"), a.date), indent=2))
        return 0
    data = commit(Path(a.script), a.date)
    print(f"covered_guard: wrote .covered-{a.date}.json from final script "
          f"({len(data['segments'])} segments, {len(data['podcast_guids'])} podcast guids)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
