#!/usr/bin/env python3
"""
Verify build-pitch verdict status. Run daily from morning check (check-episode.sh).
Logs any pitches awaiting verdict for >48h to STATUS.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
VERDICTS_FILE = REPO_ROOT / "build-pitches" / "verdicts.jsonl"
STATUS_DIR = REPO_ROOT / "status.d"
TODAY = datetime.utcnow().date()
THRESHOLD_HOURS = 48

def read_verdicts():
    """Load all verdicts from verdicts.jsonl."""
    verdicts = []
    if not VERDICTS_FILE.exists():
        return verdicts

    with open(VERDICTS_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                verdicts.append(json.loads(line))
    return verdicts

def check_old_pending_pitches():
    """Find pitches awaiting verdict for >48h and log them."""
    verdicts = read_verdicts()
    old_pending = []

    for v in verdicts:
        if v.get("verdict_state") != "awaiting":
            continue

        pitch_date = datetime.strptime(v["date"], "%Y-%m-%d").date()
        age_hours = (TODAY - pitch_date).total_seconds() / 3600

        if age_hours > THRESHOLD_HOURS:
            old_pending.append({
                "date": v["date"],
                "pitch_id": v["pitch_id"],
                "title": v["title"],
                "age_hours": int(age_hours),
            })

    if not old_pending:
        return  # Nothing to report

    # Write to STATUS
    status_ts = datetime.utcnow().strftime("%Y-%m-%d/%H%M%S")
    status_dir = STATUS_DIR / status_ts.split("/")[0]
    status_dir.mkdir(parents=True, exist_ok=True)

    status_file = status_dir / f"{status_ts.split('/')[1]}-old-pending-pitches.md"

    lines = [f"### {status_ts.replace('/', ' ')} — Build pitches awaiting verdict >48h\n"]
    lines.append(f"Check run logged {len(old_pending)} pitch(es) awaiting verdict for >48h:\n")

    for p in old_pending:
        lines.append(f"- **{p['pitch_id']}**: {p['title']} ({p['age_hours']}h old)")

    lines.append("\nNext: add verdict to build-pitches/verdicts.jsonl when pitch is built, shelved, or cancelled.")

    with open(status_file, "w") as f:
        f.write("\n".join(lines))

    print(f"✓ Logged {len(old_pending)} old pending pitch(es) to {status_file}")
    return old_pending

if __name__ == "__main__":
    old_pending = check_old_pending_pitches()
    sys.exit(0 if not old_pending else 1)
