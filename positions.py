#!/usr/bin/env python3
"""Brainrot Radio v0.2 — Kalshi Position Change Tracker.

Tracks prediction market positions for notable traders (Locksy, Foster, etc.)
and diffs against previous snapshots to surface new/changed/closed positions.

State stored in data/positions-{username}.json.

Usage:
    python3 positions.py --user locksy          # Diff against last snapshot
    python3 positions.py --user locksy --save   # Save current as new baseline
    python3 positions.py --user locksy --show   # Show current positions
    python3 positions.py --changes              # Show all users' recent changes
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from config import PROJECT_DIR

# ── Constants ─────────────────────────────────────────────────────
DATA_DIR = PROJECT_DIR / "data"
TRACKED_USERS = ["locksy", "foster"]


def load_previous(username):
    """Load the last saved position snapshot for a user."""
    filepath = DATA_DIR / f"positions-{username}.json"
    if not filepath.exists():
        return {"positions": [], "scraped_at": None}

    with open(filepath) as f:
        return json.load(f)


def save_snapshot(username, data):
    """Save current positions as the new baseline."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    filepath = DATA_DIR / f"positions-{username}.json"

    data["scraped_at"] = datetime.now(timezone.utc).isoformat()

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Saved snapshot: {filepath} ({len(data.get('positions', []))} positions)", file=sys.stderr)


def diff_positions(current, previous):
    """Compare current positions against previous snapshot.

    Returns dict with:
        added: positions in current but not previous
        removed: positions in previous but not current
        changed: positions where direction, size, or P&L changed significantly
        unchanged: same positions
    """
    prev_by_ticker = {p["ticker"]: p for p in previous.get("positions", [])}
    curr_by_ticker = {p["ticker"]: p for p in current.get("positions", [])}

    prev_tickers = set(prev_by_ticker.keys())
    curr_tickers = set(curr_by_ticker.keys())

    added = [curr_by_ticker[t] for t in (curr_tickers - prev_tickers)]
    removed = [prev_by_ticker[t] for t in (prev_tickers - curr_tickers)]

    changed = []
    unchanged = []
    for ticker in (curr_tickers & prev_tickers):
        curr_pos = curr_by_ticker[ticker]
        prev_pos = prev_by_ticker[ticker]

        # Check for meaningful changes
        changes = []
        if curr_pos.get("direction") != prev_pos.get("direction"):
            changes.append(f"direction: {prev_pos.get('direction')} → {curr_pos.get('direction')}")
        if curr_pos.get("size") != prev_pos.get("size"):
            changes.append(f"size: {prev_pos.get('size')} → {curr_pos.get('size')}")
        if curr_pos.get("avg_price") != prev_pos.get("avg_price"):
            changes.append(f"avg_price: {prev_pos.get('avg_price')} → {curr_pos.get('avg_price')}")

        # P&L change > $10 or > 5%
        curr_pnl = curr_pos.get("pnl", 0) or 0
        prev_pnl = prev_pos.get("pnl", 0) or 0
        pnl_delta = curr_pnl - prev_pnl
        if abs(pnl_delta) > 10:
            changes.append(f"P&L: ${prev_pnl:.0f} → ${curr_pnl:.0f} (Δ${pnl_delta:+.0f})")

        if changes:
            changed.append({
                "position": curr_pos,
                "previous": prev_pos,
                "changes": changes,
            })
        else:
            unchanged.append(curr_pos)

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": unchanged,
        "prev_scraped_at": previous.get("scraped_at"),
        "curr_scraped_at": current.get("scraped_at"),
    }


def format_changes(diff, username=""):
    """Format position changes as human-readable text for show scripts."""
    lines = []
    header = f"Position Changes for {username}" if username else "Position Changes"
    lines.append(f"### {header}")

    if diff.get("prev_scraped_at"):
        lines.append(f"Comparing: {diff['prev_scraped_at']} → {diff.get('curr_scraped_at', 'now')}")
    lines.append("")

    # New positions — most interesting
    if diff["added"]:
        lines.append(f"**NEW POSITIONS ({len(diff['added'])}):**")
        for pos in diff["added"]:
            ticker = pos.get("ticker", "?")
            direction = pos.get("direction", "?")
            size = pos.get("size", "?")
            avg_price = pos.get("avg_price", "?")
            market = pos.get("market_name", ticker)
            lines.append(f"  + {market} — {direction} {size} @ {avg_price}c")
        lines.append("")

    # Closed positions
    if diff["removed"]:
        lines.append(f"**CLOSED POSITIONS ({len(diff['removed'])}):**")
        for pos in diff["removed"]:
            ticker = pos.get("ticker", "?")
            market = pos.get("market_name", ticker)
            pnl = pos.get("pnl", 0)
            lines.append(f"  - {market} — closed (P&L: ${pnl:+.0f})" if pnl else f"  - {market} — closed")
        lines.append("")

    # Changed positions
    if diff["changed"]:
        lines.append(f"**MODIFIED POSITIONS ({len(diff['changed'])}):**")
        for item in diff["changed"]:
            pos = item["position"]
            market = pos.get("market_name", pos.get("ticker", "?"))
            lines.append(f"  ~ {market}")
            for change in item["changes"]:
                lines.append(f"    {change}")
        lines.append("")

    if not diff["added"] and not diff["removed"] and not diff["changed"]:
        lines.append("No changes detected since last snapshot.")
        lines.append("")

    total = len(diff.get("unchanged", []))
    lines.append(f"({total} positions unchanged)")

    return "\n".join(lines)


def create_manual_snapshot(username, positions_data):
    """Create a snapshot from manually provided position data.

    positions_data should be a list of dicts with:
        ticker, market_name, direction (YES/NO), size, avg_price, pnl
    """
    snapshot = {
        "username": username,
        "positions": positions_data,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "manual",
    }
    return snapshot


def main():
    parser = argparse.ArgumentParser(description="Brainrot Radio — Position Tracker")
    parser.add_argument("--user", help="Username to track")
    parser.add_argument("--save", action="store_true", help="Save current data as new baseline")
    parser.add_argument("--show", action="store_true", help="Show current saved positions")
    parser.add_argument("--changes", action="store_true", help="Show all users' recent changes")
    parser.add_argument("--import-json", help="Import positions from JSON file")
    args = parser.parse_args()

    if args.changes:
        for username in TRACKED_USERS:
            prev = load_previous(username)
            if prev.get("positions"):
                print(f"\n{'='*60}")
                print(f" {username} — {len(prev['positions'])} positions")
                print(f" Last scraped: {prev.get('scraped_at', 'never')}")
                print(f"{'='*60}\n")
                for pos in prev["positions"]:
                    market = pos.get("market_name", pos.get("ticker", "?"))
                    direction = pos.get("direction", "?")
                    size = pos.get("size", "?")
                    pnl = pos.get("pnl")
                    pnl_str = f" (P&L: ${pnl:+.0f})" if pnl else ""
                    print(f"  {direction} {size} — {market}{pnl_str}")
            else:
                print(f"\n{username}: No saved positions")
        return

    if not args.user:
        print("Specify --user <username> or --changes", file=sys.stderr)
        sys.exit(1)

    if args.show:
        prev = load_previous(args.user)
        positions = prev.get("positions", [])
        print(f"\n{args.user} — {len(positions)} positions (scraped: {prev.get('scraped_at', 'never')})\n")
        for pos in positions:
            market = pos.get("market_name", pos.get("ticker", "?"))
            direction = pos.get("direction", "?")
            size = pos.get("size", "?")
            avg_price = pos.get("avg_price", "?")
            pnl = pos.get("pnl")
            pnl_str = f" P&L: ${pnl:+.0f}" if pnl else ""
            print(f"  {direction} {size} @ {avg_price}c — {market}{pnl_str}")
        return

    if args.import_json:
        with open(args.import_json) as f:
            positions_data = json.load(f)
        if isinstance(positions_data, dict) and "positions" in positions_data:
            snapshot = positions_data
        else:
            snapshot = create_manual_snapshot(args.user, positions_data)

        # Diff against previous
        prev = load_previous(args.user)
        diff = diff_positions(snapshot, prev)
        print(format_changes(diff, args.user))

        if args.save:
            save_snapshot(args.user, snapshot)
        return

    # Default: show diff info
    prev = load_previous(args.user)
    if not prev.get("positions"):
        print(f"No saved positions for {args.user}. Use --import-json to load initial data.")
    else:
        print(f"{args.user}: {len(prev['positions'])} positions saved (scraped: {prev.get('scraped_at')})")
        print("Use --import-json <file> to compare against new data")
        print("Use --show to display current positions")


if __name__ == "__main__":
    main()
