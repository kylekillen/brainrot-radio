#!/usr/bin/env python3
"""Killen Time Episode Dashboard — real-time pipeline progress monitor.

Watches the filesystem for pipeline artifacts to determine which stage
the current episode is in. No modification to generate-episode.sh needed.

Usage:
    python3 dashboard.py          # Start on port 8811
    python3 dashboard.py --port 9000
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
SCRIPTS_DIR = PROJECT_DIR / "scripts"
OUTPUT_DIR = PROJECT_DIR / "output"
TEMP_DIR = PROJECT_DIR / ".tmp"
SEGMENTS_DIR = TEMP_DIR / "segments"
ARTWORK_DIR = PROJECT_DIR / "assets" / "episode-artwork"
LOGS_DIR = PROJECT_DIR / "logs"
FEED_URL = "https://kylekillen.github.io/killen-time-podcast/feed.xml"

STAGES = [
    {"id": "ingest", "label": "Ingest", "icon": "📡"},
    {"id": "script", "label": "Script", "icon": "✍️"},
    {"id": "qc", "label": "QC", "icon": "🔍"},
    {"id": "render", "label": "Render", "icon": "🎙️"},
    {"id": "artwork", "label": "Artwork", "icon": "🎨"},
    {"id": "mix", "label": "Mix", "icon": "🎛️"},
    {"id": "publish", "label": "Publish", "icon": "📤"},
]


def get_today():
    return date.today().isoformat()


def get_episodes_today():
    """List all completed episodes for today."""
    today = get_today()
    episodes = []
    for mp3 in sorted(OUTPUT_DIR.glob(f"killen-time-{today}*.mp3")):
        if "test" in mp3.name:
            continue
        stat = mp3.stat()
        duration_s = stat.st_size / (128000 / 8)  # rough estimate from 128kbps
        episodes.append({
            "name": mp3.stem,
            "size_mb": round(stat.st_size / 1_048_576, 1),
            "duration_min": round(duration_s / 60, 1),
            "time": datetime.fromtimestamp(stat.st_mtime).strftime("%I:%M %p"),
        })
    return episodes


def get_schedule():
    """Return today's episode schedule and which have fired."""
    schedule_hours = [5, 10, 14, 18, 22]
    now = datetime.now()
    schedule = []
    for h in schedule_hours:
        fired = now.hour >= h
        # Check if a log exists for this run
        log_pattern = f"generate-{get_today().replace('-', '')}-{h:02d}*.log"
        logs = list(LOGS_DIR.glob(log_pattern))
        schedule.append({
            "hour": h,
            "label": f"{h % 12 or 12}{'AM' if h < 12 else 'PM'}",
            "fired": fired,
            "has_log": len(logs) > 0,
        })
    return schedule


def detect_pipeline_state():
    """Detect current pipeline state by watching filesystem artifacts."""
    today = get_today()
    state = {
        "stage": "idle",
        "stage_idx": -1,
        "detail": "No episode in progress",
        "progress_pct": 0,
        "segments_done": 0,
        "segments_total": 0,
    }

    # Check if claude process is running for brainrot
    try:
        ps = subprocess.run(
            ["pgrep", "-f", "claude.*brainrot"],
            capture_output=True, text=True, timeout=5,
        )
        claude_running = ps.returncode == 0
    except Exception:
        claude_running = False

    # Check if generate-episode.sh is running
    try:
        ps = subprocess.run(
            ["pgrep", "-f", "generate-episode"],
            capture_output=True, text=True, timeout=5,
        )
        gen_running = ps.returncode == 0
    except Exception:
        gen_running = False

    # Check if ingest is running
    try:
        ps = subprocess.run(
            ["pgrep", "-f", "ingest.py"],
            capture_output=True, text=True, timeout=5,
        )
        ingest_running = ps.returncode == 0
    except Exception:
        ingest_running = False

    if not gen_running and not claude_running and not ingest_running:
        # Check the most recent log for status
        logs = sorted(LOGS_DIR.glob("generate-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        if logs:
            last_log = logs[0]
            try:
                content = last_log.read_text()[-500:]
                if "Claude exited with code" in content or "timed out" in content:
                    state["detail"] = f"Last run failed — {last_log.name}"
                    state["stage"] = "error"
            except Exception:
                pass
        return state

    # Something is running — figure out which stage

    # Get the latest topic brief mod time
    topic_brief = TEMP_DIR / "topic-brief.txt"
    brief_fresh = False
    if topic_brief.exists():
        age_min = (datetime.now().timestamp() - topic_brief.stat().st_mtime) / 60
        brief_fresh = age_min < 60  # less than 1 hour old

    if ingest_running:
        state["stage"] = "ingest"
        state["stage_idx"] = 0
        state["detail"] = "Fetching RSS, podcasts, Substacks..."
        state["progress_pct"] = 5
        return state

    if not brief_fresh:
        state["stage"] = "ingest"
        state["stage_idx"] = 0
        state["detail"] = "Waiting for ingest..."
        state["progress_pct"] = 3
        return state

    # Topic brief is fresh — check for script
    today_scripts = sorted(SCRIPTS_DIR.glob(f"killen-time-{today}*.txt"), key=lambda p: p.stat().st_mtime)
    latest_output = sorted(OUTPUT_DIR.glob(f"killen-time-{today}*.mp3"), key=lambda p: p.stat().st_mtime)
    # Filter test files
    latest_output = [p for p in latest_output if "test" not in p.name]

    # How many completed episodes vs scripts
    n_scripts = len(today_scripts)
    n_outputs = len(latest_output)

    if n_scripts > n_outputs:
        # There's a script without a matching output — we're in render/mix/publish
        latest_script = today_scripts[-1]
        script_age_min = (datetime.now().timestamp() - latest_script.stat().st_mtime) / 60

        # Check segment progress
        seg_files = sorted(SEGMENTS_DIR.glob("seg_*.mp3"))
        n_segs = len(seg_files)

        # Count expected segments from script
        try:
            script_text = latest_script.read_text()
            import re
            expected_segs = len(re.findall(r"^\[(ALEX|NOVA)\]", script_text, re.MULTILINE))
        except Exception:
            expected_segs = 0

        # Check for fresh artwork
        today_artwork = sorted(ARTWORK_DIR.glob(f"artwork-{today}*.jpg"), key=lambda p: p.stat().st_mtime)
        latest_artwork_fresh = False
        if today_artwork:
            art_age = (datetime.now().timestamp() - today_artwork[-1].stat().st_mtime) / 60
            latest_artwork_fresh = art_age < 30

        if n_segs > 0 and n_segs < expected_segs:
            state["stage"] = "render"
            state["stage_idx"] = 3
            state["segments_done"] = n_segs
            state["segments_total"] = expected_segs
            pct = 45 + int(35 * n_segs / max(expected_segs, 1))
            state["progress_pct"] = pct
            state["detail"] = f"Rendering segment {n_segs}/{expected_segs}..."
            return state
        elif n_segs >= expected_segs and expected_segs > 0:
            if not latest_artwork_fresh:
                state["stage"] = "artwork"
                state["stage_idx"] = 4
                state["progress_pct"] = 82
                state["detail"] = "Generating episode artwork..."
                return state
            else:
                state["stage"] = "mix"
                state["stage_idx"] = 5
                state["progress_pct"] = 90
                state["detail"] = "Mixing final audio..."
                return state
        else:
            # Script exists but no segments yet — still writing or QC
            if script_age_min < 3:
                state["stage"] = "qc"
                state["stage_idx"] = 2
                state["progress_pct"] = 40
                state["detail"] = "Running quality check..."
            else:
                state["stage"] = "render"
                state["stage_idx"] = 3
                state["progress_pct"] = 45
                state["detail"] = "Starting voice render..."
            return state
    elif claude_running:
        # Claude is running but no new script yet — writing
        state["stage"] = "script"
        state["stage_idx"] = 1
        state["detail"] = "Claude is writing the episode..."
        state["progress_pct"] = 20
        return state

    # If we get here, everything looks complete
    state["stage"] = "idle"
    state["detail"] = f"{n_outputs} episodes completed today"
    state["progress_pct"] = 100
    return state


def get_status():
    """Full status payload."""
    return {
        "timestamp": datetime.now().isoformat(),
        "today": get_today(),
        "pipeline": detect_pipeline_state(),
        "episodes_today": get_episodes_today(),
        "schedule": get_schedule(),
        "stages": STAGES,
    }


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Killen Time — Episode Dashboard</title>
<style>
  :root {
    --bg: #0a0a0f;
    --card: #13131a;
    --border: #1e1e2a;
    --text: #e0e0e8;
    --dim: #6b6b80;
    --accent: #f97316;
    --accent2: #3b82f6;
    --green: #22c55e;
    --red: #ef4444;
    --yellow: #eab308;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', monospace;
    min-height: 100vh;
    padding: 24px;
  }
  .header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 32px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 16px;
  }
  .header h1 {
    font-size: 20px;
    font-weight: 600;
    letter-spacing: 2px;
    text-transform: uppercase;
  }
  .header .time {
    color: var(--dim);
    font-size: 13px;
  }
  .pulse {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 8px;
    animation: pulse 2s ease-in-out infinite;
  }
  .pulse.active { background: var(--green); }
  .pulse.idle { background: var(--dim); animation: none; }
  .pulse.error { background: var(--red); animation: none; }
  @keyframes pulse {
    0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.4); }
    50% { opacity: 0.6; box-shadow: 0 0 0 8px rgba(34, 197, 94, 0); }
  }

  /* ── Progress Meter ── */
  .meter-section {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 32px;
    margin-bottom: 24px;
  }
  .meter-label {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }
  .meter-label .stage-name {
    font-size: 16px;
    font-weight: 600;
    color: var(--accent);
  }
  .meter-label .pct {
    font-size: 28px;
    font-weight: 700;
    color: var(--text);
  }
  .meter-detail {
    color: var(--dim);
    font-size: 13px;
    margin-bottom: 20px;
  }
  .meter-bar-track {
    width: 100%;
    height: 12px;
    background: var(--bg);
    border-radius: 6px;
    overflow: hidden;
    margin-bottom: 24px;
  }
  .meter-bar-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--accent), var(--accent2));
    border-radius: 6px;
    transition: width 1s ease;
    position: relative;
  }
  .meter-bar-fill.active::after {
    content: '';
    position: absolute;
    right: 0;
    top: 0;
    width: 40px;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3));
    animation: shimmer 1.5s ease-in-out infinite;
  }
  @keyframes shimmer {
    0%, 100% { opacity: 0; }
    50% { opacity: 1; }
  }

  /* ── Stage Pipeline ── */
  .stages {
    display: flex;
    gap: 4px;
    align-items: center;
  }
  .stage-dot {
    display: flex;
    flex-direction: column;
    align-items: center;
    flex: 1;
    position: relative;
  }
  .stage-icon {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    border: 2px solid var(--border);
    background: var(--bg);
    transition: all 0.5s ease;
    margin-bottom: 6px;
  }
  .stage-dot.done .stage-icon {
    border-color: var(--green);
    background: rgba(34, 197, 94, 0.1);
  }
  .stage-dot.active .stage-icon {
    border-color: var(--accent);
    background: rgba(249, 115, 22, 0.15);
    box-shadow: 0 0 12px rgba(249, 115, 22, 0.3);
    animation: stagePulse 2s ease-in-out infinite;
  }
  @keyframes stagePulse {
    0%, 100% { box-shadow: 0 0 8px rgba(249, 115, 22, 0.2); }
    50% { box-shadow: 0 0 16px rgba(249, 115, 22, 0.5); }
  }
  .stage-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--dim);
  }
  .stage-dot.active .stage-label { color: var(--accent); }
  .stage-dot.done .stage-label { color: var(--green); }
  .stage-connector {
    flex: 0.5;
    height: 2px;
    background: var(--border);
    margin-bottom: 20px;
  }
  .stage-connector.done { background: var(--green); }

  /* ── Schedule ── */
  .schedule-section {
    display: flex;
    gap: 12px;
    margin-bottom: 24px;
  }
  .schedule-slot {
    flex: 1;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    text-align: center;
  }
  .schedule-slot .hour {
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 4px;
  }
  .schedule-slot .status {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
  }
  .schedule-slot.done { border-color: var(--green); }
  .schedule-slot.done .status { color: var(--green); }
  .schedule-slot.next { border-color: var(--accent); }
  .schedule-slot.next .status { color: var(--accent); }
  .schedule-slot.pending .status { color: var(--dim); }

  /* ── Episodes List ── */
  .episodes-section {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 24px;
  }
  .episodes-section h2 {
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: var(--dim);
    margin-bottom: 16px;
  }
  .episode-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
  }
  .episode-row:last-child { border-bottom: none; }
  .episode-name { font-weight: 500; }
  .episode-meta {
    display: flex;
    gap: 16px;
    color: var(--dim);
    font-size: 13px;
  }
  .no-episodes {
    color: var(--dim);
    font-style: italic;
    padding: 8px 0;
  }

  /* ── Segment Counter ── */
  .segment-counter {
    margin-top: 8px;
    font-size: 13px;
    color: var(--accent2);
  }
</style>
</head>
<body>
<div class="header">
  <h1><span class="pulse idle" id="statusDot"></span>Killen Time</h1>
  <span class="time" id="clock"></span>
</div>

<div class="meter-section">
  <div class="meter-label">
    <span class="stage-name" id="stageName">—</span>
    <span class="pct" id="pctLabel">0%</span>
  </div>
  <div class="meter-detail" id="stageDetail">Checking status...</div>
  <div class="meter-bar-track">
    <div class="meter-bar-fill" id="meterFill" style="width: 0%"></div>
  </div>
  <div class="stages" id="stagesRow"></div>
  <div class="segment-counter" id="segmentCounter"></div>
</div>

<div class="schedule-section" id="scheduleRow"></div>

<div class="episodes-section">
  <h2>Today's Episodes</h2>
  <div id="episodesList"><div class="no-episodes">Loading...</div></div>
</div>

<script>
function updateClock() {
  document.getElementById('clock').textContent = new Date().toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
}
setInterval(updateClock, 1000);
updateClock();

function renderStages(stages, currentIdx) {
  const row = document.getElementById('stagesRow');
  row.innerHTML = '';
  stages.forEach((s, i) => {
    if (i > 0) {
      const conn = document.createElement('div');
      conn.className = 'stage-connector' + (i <= currentIdx ? ' done' : '');
      row.appendChild(conn);
    }
    const dot = document.createElement('div');
    let cls = 'stage-dot';
    if (i < currentIdx) cls += ' done';
    else if (i === currentIdx) cls += ' active';
    dot.className = cls;
    dot.innerHTML = `<div class="stage-icon">${s.icon}</div><div class="stage-label">${s.label}</div>`;
    row.appendChild(dot);
  });
}

function renderSchedule(schedule) {
  const row = document.getElementById('scheduleRow');
  row.innerHTML = '';
  let foundNext = false;
  schedule.forEach(s => {
    const slot = document.createElement('div');
    let cls = 'schedule-slot';
    let statusText = '';
    if (s.fired && s.has_log) {
      cls += ' done';
      statusText = '✓ Done';
    } else if (s.fired) {
      cls += ' done';
      statusText = '✓ Fired';
    } else if (!foundNext) {
      cls += ' next';
      statusText = 'Next';
      foundNext = true;
    } else {
      cls += ' pending';
      statusText = 'Pending';
    }
    slot.className = cls;
    slot.innerHTML = `<div class="hour">${s.label}</div><div class="status">${statusText}</div>`;
    row.appendChild(slot);
  });
}

function renderEpisodes(episodes) {
  const list = document.getElementById('episodesList');
  if (!episodes.length) {
    list.innerHTML = '<div class="no-episodes">No episodes yet today</div>';
    return;
  }
  list.innerHTML = episodes.map(e => `
    <div class="episode-row">
      <span class="episode-name">${e.name}</span>
      <span class="episode-meta">
        <span>${e.duration_min} min</span>
        <span>${e.size_mb} MB</span>
        <span>${e.time}</span>
      </span>
    </div>
  `).join('');
}

async function poll() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    const p = data.pipeline;

    // Status dot
    const dot = document.getElementById('statusDot');
    if (p.stage === 'idle') {
      dot.className = 'pulse idle';
    } else if (p.stage === 'error') {
      dot.className = 'pulse error';
    } else {
      dot.className = 'pulse active';
    }

    // Meter
    document.getElementById('stageName').textContent =
      p.stage === 'idle' ? 'Idle' :
      p.stage === 'error' ? 'Error' :
      data.stages[p.stage_idx]?.icon + ' ' + data.stages[p.stage_idx]?.label || p.stage;
    document.getElementById('pctLabel').textContent = p.progress_pct + '%';
    document.getElementById('stageDetail').textContent = p.detail;
    const fill = document.getElementById('meterFill');
    fill.style.width = p.progress_pct + '%';
    fill.className = 'meter-bar-fill' + (p.stage !== 'idle' && p.stage !== 'error' ? ' active' : '');

    // Segment counter
    const sc = document.getElementById('segmentCounter');
    if (p.stage === 'render' && p.segments_total > 0) {
      sc.textContent = `Segments: ${p.segments_done} / ${p.segments_total}`;
    } else {
      sc.textContent = '';
    }

    // Stages
    renderStages(data.stages, p.stage_idx);

    // Schedule
    renderSchedule(data.schedule);

    // Episodes
    renderEpisodes(data.episodes_today);

  } catch (e) {
    console.error('Poll error:', e);
  }
}

poll();
setInterval(poll, 5000);
</script>
</body>
</html>
"""


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode())
        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(json.dumps(get_status()).encode())
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass  # Suppress request logging


def main():
    parser = argparse.ArgumentParser(description="Killen Time Dashboard")
    parser.add_argument("--port", type=int, default=8811)
    args = parser.parse_args()

    server = HTTPServer(("0.0.0.0", args.port), DashboardHandler)
    print(f"Dashboard running at http://localhost:{args.port}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.", file=sys.stderr)
        server.server_close()


if __name__ == "__main__":
    main()
