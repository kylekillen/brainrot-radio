#!/usr/bin/env python3
"""Code Voice — synth-server watchdog.

The Kokoro TTS server (com.codevoice.server, port 8765) wedges intermittently:
a synth thread gets stuck holding the non-thread-safe mlx Kokoro lock, so every
POST /v1/audio/speech hangs forever — but GET /health keeps returning 200
(health never takes the synth lock). The wedge is therefore INVISIBLE to a
health check: say_to_phone.py helpers hang post-call and Kyle silently stops
getting Telegram voice notes while everything *looks* healthy. Observed 3x on
2026-06-27, each needing a manual `launchctl kickstart`.

This watchdog exercises the ACTUAL synth path with a tiny request and restarts
the server ONLY on a true wedge (process up, model warm, synth hangs). It is
careful NOT to restart during the ~3.5min model-reload warmup after a restart
(during which the port is refused / health isn't warm yet) and enforces a
~10min cooldown so it can never restart-storm.

Run on a ~180s launchd StartInterval (com.codevoice.watchdog). Manual / test:
    python3 code-voice/voice-watchdog.py            # one real probe
    python3 code-voice/voice-watchdog.py --self-test # unit-test decision logic
    python3 code-voice/voice-watchdog.py --port 9999 --dry-run  # probe a test port

Health file (inspectable state):
    ~/.observer/data/codevoice-watchdog.health  ->  state=<...> ts=<...>
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8765
SERVICE = "com.codevoice.server"

SYNTH_TIMEOUT = 20        # hard cap on the synth probe — a wedge hangs forever
HEALTH_TIMEOUT = 5        # /health is cheap; a slow answer here is itself a smell
COOLDOWN_SECS = 600       # never restart more than once per ~10 min

DATA_DIR = Path.home() / ".observer" / "data"
HEALTH_FILE = DATA_DIR / "codevoice-watchdog.health"
COOLDOWN_FILE = DATA_DIR / "codevoice-watchdog.last-restart"
LOG = Path(__file__).resolve().parent / "watchdog.log"


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def write_health(state: str):
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        HEALTH_FILE.write_text(f"state={state} ts={ts}\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Probes (I/O)
# ---------------------------------------------------------------------------

def check_health(host=HOST, port=PORT):
    """Return {reachable: bool, warm: bool}. Connection-refused/timeout means the
    server isn't up (mid-restart / loading model) -> not reachable."""
    url = f"http://{host}:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=HEALTH_TIMEOUT) as r:
            body = json.loads(r.read() or b"{}")
            return {"reachable": True, "warm": bool(body.get("warm"))}
    except Exception:  # noqa: BLE001 — refused / timeout / bad body all == not-up
        return {"reachable": False, "warm": False}


def probe_synth(host=HOST, port=PORT, timeout=SYNTH_TIMEOUT):
    """Send a real tiny synth request and classify the OUTCOME (not a verdict).

    Returns one of: "ok" (200 in time), "timeout" (connected but synth hung),
    "refused" (server went down between checks), "error" (responded non-200)."""
    url = f"http://{host}:{port}/v1/audio/speech"
    payload = json.dumps({"voice": "af_heart", "input": "watchdog ping"}).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()
            return "ok" if r.status == 200 else "error"
    except urllib.error.HTTPError:
        # Server answered with a non-2xx status — it is RESPONSIVE, not wedged.
        return "error"
    except Exception as e:  # noqa: BLE001
        # Distinguish a connection refused / reset (server down == warming /
        # restarting) from a read timeout (connected but synth hung forever ==
        # the wedge signature). socket.timeout subclasses TimeoutError/OSError.
        text = (str(getattr(e, "reason", "")) + " " + str(e)).lower()
        if "refused" in text or "could not connect" in text or "reset" in text:
            return "refused"
        return "timeout"


# ---------------------------------------------------------------------------
# Decision logic (pure — unit tested)
# ---------------------------------------------------------------------------

def classify(health: dict, synth_outcome: str) -> str:
    """Pure verdict from observed probe outcomes.

    Returns: "ok" | "wedged" | "warming" | "error".
    Only "wedged" should trigger a restart.

    - Not reachable          -> warming  (port refused: restarting / loading model)
    - Reachable, not warm     -> warming  (model still loading after a restart)
    - Warm, synth ok          -> ok
    - Warm, synth timed out    -> wedged   (the bug: synth lock held forever)
    - Warm, synth refused      -> warming  (server went down mid-probe)
    - Warm, synth errored      -> error    (responsive but raised — NOT a wedge)
    """
    if not health.get("reachable"):
        return "warming"
    if not health.get("warm"):
        return "warming"
    if synth_outcome == "ok":
        return "ok"
    if synth_outcome == "timeout":
        return "wedged"
    if synth_outcome == "refused":
        return "warming"
    return "error"


# ---------------------------------------------------------------------------
# Cooldown + restart
# ---------------------------------------------------------------------------

def cooldown_active() -> bool:
    try:
        last = float(COOLDOWN_FILE.read_text().strip())
    except (OSError, ValueError):
        return False
    return (time.time() - last) < COOLDOWN_SECS


def stamp_cooldown():
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        COOLDOWN_FILE.write_text(str(time.time()))
    except OSError:
        pass


def restart_server(dry_run=False) -> bool:
    cmd = ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{SERVICE}"]
    if dry_run:
        log(f"DRY-RUN would restart: {' '.join(cmd)}")
        return True
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=30)
        return True
    except Exception as e:  # noqa: BLE001
        log(f"restart failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_once(host=HOST, port=PORT, dry_run=False) -> str:
    """One watchdog cycle. Returns the state it wrote. Fails safe (never raises)."""
    try:
        health = check_health(host, port)
        if not health["reachable"] or not health["warm"]:
            state = "warming"
            write_health(state)
            log(f"warming (reachable={health['reachable']} warm={health['warm']}) — no action")
            return state

        outcome = probe_synth(host, port)
        # A single timeout could be a momentarily-busy server (a long real synth
        # holds the lock ~25s). Confirm with a second probe before declaring a
        # wedge — a true wedge hangs forever, a busy server clears. ~40s of
        # continuous hang is the wedge signature, not transient load.
        if outcome == "timeout":
            log("synth probe timed out — confirming with a second probe")
            outcome = probe_synth(host, port)

        state = classify(health, outcome)

        if state == "wedged":
            if cooldown_active():
                write_health("wedged-cooldown")
                log("WEDGED but within cooldown — skipping restart")
                return "wedged-cooldown"
            log(f"WEDGED (synth={outcome}) — restarting {SERVICE}")
            stamp_cooldown()
            ok = restart_server(dry_run=dry_run)
            state = "wedged-restarted" if ok else "wedged-restart-failed"
            write_health(state)
            return state

        write_health(state)
        log(f"state={state} (synth={outcome})")
        return state
    except Exception as e:  # noqa: BLE001 — never error noisily; fail safe
        log(f"watchdog internal error (ignored): {e}")
        write_health("error")
        return "error"


# ---------------------------------------------------------------------------
# Self-test (decision logic)
# ---------------------------------------------------------------------------

def self_test() -> int:
    cases = [
        # (health, synth_outcome, expected)
        ({"reachable": True, "warm": True}, "ok", "ok"),
        ({"reachable": True, "warm": True}, "timeout", "wedged"),
        ({"reachable": False, "warm": False}, "refused", "warming"),  # port refused
        ({"reachable": True, "warm": False}, "ok", "warming"),        # loading model
        ({"reachable": True, "warm": True}, "refused", "warming"),     # down mid-probe
        ({"reachable": True, "warm": True}, "error", "error"),         # responsive 5xx
    ]
    failures = 0
    for health, outcome, expected in cases:
        got = classify(health, outcome)
        ok = got == expected
        failures += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] health={health} synth={outcome} "
              f"-> {got} (expected {expected})")
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


def main():
    ap = argparse.ArgumentParser(description="Code Voice synth-server watchdog")
    ap.add_argument("--self-test", action="store_true",
                    help="unit-test the decision logic and exit")
    ap.add_argument("--port", type=int, default=PORT, help="port to probe")
    ap.add_argument("--host", default=HOST, help="host to probe")
    ap.add_argument("--dry-run", action="store_true",
                    help="classify + log but never actually restart")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    state = run_once(host=args.host, port=args.port, dry_run=args.dry_run)
    # Exit 0 on healthy/handled states; non-zero only on hard failure to restart.
    print(state)
    return 0 if state != "wedged-restart-failed" else 1


if __name__ == "__main__":
    sys.exit(main())
