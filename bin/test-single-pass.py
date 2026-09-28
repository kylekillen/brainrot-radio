#!/usr/bin/env python3
"""
New Hire Test: single-pass (~3,500 word) vs current two-pass (~6,000 words)
Same-day sources, quality + token comparison.

Usage:
  python3 bin/test-single-pass.py --date YYYY-MM-DD [--engine claude|gemini|external]

Generates:
  - test-runs/YYYY-MM-DD-single-pass.md (single-pass variant)
  - test-runs/YYYY-MM-DD-two-pass.md (current variant) if needed
  - Comparison and metrics to STATUS

NOT integrated into daily pipeline — manual test only.
"""

import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
TEST_DIR = REPO_ROOT / "test-runs"

def setup_test():
    """Create test directory and log setup."""
    TEST_DIR.mkdir(exist_ok=True)
    (TEST_DIR / "README.md").write_text("""# Test Runs

Manual episode tests for quality comparison (single-pass vs two-pass, etc.).

Each test run produces:
- `YYYY-MM-DD-{variant}.md` — Final episode script
- Metrics JSON with token usage, segments, quality signals
- STATUS entry with comparison report

Tests are NOT published to the feed.
""")

def run_single_pass_test(date, engine="claude"):
    """Run a single-pass episode and capture metrics."""
    print(f"Single-pass test setup for {date} on {engine}")
    print(f"Next steps (manual):")
    print(f"  1. Source ingest: python3 ingest.py --report -n 40 > /tmp/single-pass-brief.txt")
    print(f"  2. Generate single-pass script: claude -p --model sonnet << 'EOF'")
    print(f"     (use single-pass prompt from .claude/commands/single-pass-prompt.md)")
    print(f"  3. Render audio from {TEST_DIR}/{date}-single-pass.txt")
    print(f"  4. Compare metrics with current two-pass episode")

def log_test_result(date, variant, script_path, metrics):
    """Log test results to STATUS."""
    status_dir = REPO_ROOT / "status.d" / date
    status_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.utcnow().strftime("%H%M%S")
    status_file = status_dir / f"{ts}-new-hire-test-{variant}.md"

    content = f"""### {date} {ts.replace('Z', '')} — New Hire test: {variant} variant

**Metrics:**
- Word count: {metrics.get('words', 'N/A')}
- Segments: {metrics.get('segments', 'N/A')}
- Tokens (est.): {metrics.get('tokens', 'N/A')}
- Quality signals: {metrics.get('quality', 'N/A')}
- Time to render: {metrics.get('render_time', 'N/A')}

**Script:** {script_path}
"""
    status_file.write_text(content)
    print(f"✓ Logged to {status_file}")

def main():
    parser = argparse.ArgumentParser(description="New Hire test harness")
    parser.add_argument("--date", default=datetime.utcnow().strftime("%Y-%m-%d"))
    parser.add_argument("--engine", choices=["claude", "gemini", "external"], default="claude")
    parser.add_argument("--run-both", action="store_true", help="Run both single and two-pass")
    args = parser.parse_args()

    setup_test()
    run_single_pass_test(args.date, args.engine)

    if args.run_both:
        print(f"\nTwo-pass variant (current): run daily generate-episode.sh for {args.date}")

if __name__ == "__main__":
    main()
