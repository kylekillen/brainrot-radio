#!/usr/bin/env python3
"""Gemini Build-Pitch Reporter — FAITHFUL port of the original Claude Step 1.5
methodology, model swapped to Gemini. Combs the actual claude_lab YouTube channels'
transcripts (youtube.py + full-transcript pulls), then has Gemini analyze + verify
them against the original brief, with Google Search grounding for cross-checking.
Zero Claude. Writes build-pitches/<today>.md + .tmp/build-pitches.md.
"""
import datetime
import json
import os
import pathlib
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
TODAY = datetime.date.today().isoformat()
MODEL = "gemini-flash-latest"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
PY = str(ROOT / "venv" / "bin" / "python3")
MAX_VIDEOS = 6          # full transcripts to comb (the original's "interesting ones")
PER_TRANSCRIPT_CAP = 9000


def _key() -> str:
    for line in (pathlib.Path.home() / ".config" / "personal-os" / "offload.env").read_text().splitlines():
        if line.startswith("OFFLOAD_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("no OFFLOAD_API_KEY")


def gather_claude_lab_transcripts():
    """Original methodology: claude_lab YouTube candidates, then FULL transcripts."""
    r = subprocess.run([PY, str(ROOT / "youtube.py"), "--hours", "168", "--json"],
                       capture_output=True, text=True, timeout=300, cwd=str(ROOT))
    try:
        items = json.loads(r.stdout)
    except Exception:
        return []
    cl = [x for x in items if "claude" in str(x.get("_topic", "")).lower()]
    import youtube  # for full transcripts (the snippet in --json is truncated triage)
    out = []
    for v in cl[:MAX_VIDEOS]:
        vid = v.get("video_id")
        full = youtube.fetch_transcript(vid) if vid else None
        text = (full or v.get("content") or v.get("transcript") or "")[:PER_TRANSCRIPT_CAP]
        if text.strip():
            out.append((v.get("title", "?"), v.get("url", ""), text))
    return out


def main():
    brief = ""
    bf = ROOT / ".claude" / "context" / "beats" / "claude-lab.md"
    if bf.exists():
        brief = bf.read_text()[:6000]
    # History: what we've ALREADY pitched (and what was rejected) the last several
    # days — so we don't re-surface it (the original reporter has this awareness).
    pitch_history = ""
    past = sorted((ROOT / "build-pitches").glob("[0-9]*.md"))[-6:]
    past = [p for p in past if p.stem != TODAY]
    if past:
        pitch_history = "\n\n".join(f"--- {p.name} ---\n{p.read_text()[:2500]}" for p in past)
    transcripts = gather_claude_lab_transcripts()
    if not transcripts:
        (ROOT / ".tmp").mkdir(exist_ok=True)
        (ROOT / ".tmp" / "build-pitches.md").write_text("NO_VERIFIED_PITCH\nNo claude_lab transcripts available.\n")
        print("no transcripts; wrote NO_VERIFIED_PITCH", file=sys.stderr)
        return
    tblock = "\n\n".join(f"=== TRANSCRIPT: {t} ({u}) ===\n{body}" for t, u, body in transcripts)
    prompt = f"""You are the Killen Time Build-Pitch Reporter. Your brief:
{brief}

Below are FULL transcripts pulled this week from the claude_lab YouTube channels
(IndyDevDan, Cole Medin, AI Jason, GosuCoder, Matthew Berman, Anthropic). Comb them
for the SINGLE highest-leverage, genuinely VERIFIED technique on Claude/agent
technique, multi-agent orchestration, Claude Code upgrades, or AI-system
optimization that would most improve Kyle's multi-agent fleet. Use Google Search to
CROSS-CHECK it (is anyone else doing it? real evidence, not a single hyped demo?).
Reject anything Kyle already runs (observer-system, COS, dispatcher + PR-reviewer
loop, /goal-bound delegation). One strong verified pitch beats three thin ones; if
nothing clears the bar that is a valid outcome.

=== ALREADY PITCHED / REJECTED in recent days (do NOT re-surface these; if a past
day marked something rejected or already-in-place, honor that judgment) ===
{pitch_history or "(no recent pitch history)"}

{tblock}

Output EXACTLY two parts separated by a line containing only ===SUMMARY===
PART 1 (durable record): Technique (1-2 sentences); Who's doing it (the video title +
URL + any corroborating sources); Evidence it's real (what you cross-checked); Need
it serves; Build sketch (concrete first steps).
PART 2 (200-400 word summary for the episode writer): lead with the single best
pitch — what it is, who's doing it, why it's verified, and the one-line upgrade for
Kyle's setup. If NOTHING clears the bar, PART 2's first line must be exactly:
NO_VERIFIED_PITCH"""

    body = json.dumps({
        "tools": [{"google_search": {}}],
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 4000, "temperature": 0.4},
    }).encode()
    req = urllib.request.Request(ENDPOINT, data=body,
                                headers={"x-goog-api-key": _key(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        data = json.load(r)
    cand = (data.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
    if not text.strip():
        print(f"FATAL: empty response: {json.dumps(data)[:300]}", file=sys.stderr); sys.exit(1)
    durable, summary = text.split("===SUMMARY===", 1) if "===SUMMARY===" in text else (text, text)
    (ROOT / "build-pitches").mkdir(exist_ok=True)
    (ROOT / "build-pitches" / f"{TODAY}.md").write_text(
        f"# Build Pitches — {TODAY} (Gemini, combed {len(transcripts)} claude_lab transcripts)\n\n" + durable.strip() + "\n")
    (ROOT / ".tmp").mkdir(exist_ok=True)
    (ROOT / ".tmp" / "build-pitches.md").write_text(summary.strip() + "\n")
    print(f"DONE: combed {len(transcripts)} transcripts, grounded={'groundingMetadata' in cand}, {len(text.split())} words")

    # Auto-route the build pitch to Kyle's PRIVATE podcast feed as audio so he can
    # review it on a walk instead of reading it on his phone (Kyle, 2026-06-25:
    # "build plans generated for my review should be automatically routed as audio
    # to my podcast feed"). Best-effort: a kokoro/publish outage must NEVER fail
    # pitch generation — the durable file still exists for the dashboard "Send to
    # podcast" button fallback. Idempotent (content-hash ledger) so re-runs of
    # generate-episode.sh don't double-publish. Disable with BUILDPITCH_AUTO_PODCAST=0.
    if os.environ.get("BUILDPITCH_AUTO_PODCAST", "1") != "0":
        try:
            sys.path.insert(0, str(ROOT))
            import publish_review
            pitch_file = ROOT / "build-pitches" / f"{TODAY}.md"
            res = publish_review.publish_review(
                title=f"Fleet Build Pitch — {TODAY}",
                md_path=pitch_file,
                description="Daily Fleet build-pitch — a verified Claude/agent technique for Kyle's review.",
                source=str(pitch_file),
            )
            print(f"build-pitch podcast: {res['state']} {res.get('url') or ''}", file=sys.stderr)
        except Exception as e:
            print(f"build-pitch podcast route failed (non-fatal): {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
