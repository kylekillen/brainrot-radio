#!/usr/bin/env python3
"""free_lane_diag.py — name what the free / offload lanes are ACTUALLY about to
call, what a provider failure actually means, and whether the offload fallback
may spend money right now. The first two are reporting only; the third gates.

Why it exists (2026-09-29). generate-episode.sh hardcoded two claims that the
05:15 run proved false, and both cost an operator real time:

  * The offload fallback announced "offload.env — currently free Gemini Flash
    ... the fallback is also $0" on the strength of a comment. or_complete.
    _config() actually falls back to DEFAULT_BASE (openrouter.ai) plus the
    legacy openrouter.env key when offload.env carries no key, so that run
    printed the $0 claim and then or_writer 402'd on an overdrawn wallet.
  * The free-lane 429 warning always prescribed "fix external_writer.py
    DEFAULT_MODEL" — the 09-08 "rotate the free model" fix misfiring on a
    failure it cannot touch. That 429 was limit_source=openrouter_free_tier_
    daily with a flat X-RateLimit-Limit 1000 / Remaining 0: an ACCOUNT-level
    daily bucket. Any other :free slug on the same key draws the same empty
    bucket, so rotating the model changes nothing.

So both facts are computed, never assumed:

  offload    resolve or_complete._config() and print the base URL, the model,
             the cost class (FREE / FREE-TIER / METERED) and which file the key
             came from — never the key itself.
  classify   read a run log, take the LAST provider error in it and name the
             remedy that follows from its limit_source / error body, or say
             plainly that it could not tell.
  offload-gate  exit 0 (dispatch) or 3 (refuse): while the burn gate is up, a
             route that cannot be shown to be $0 is REFUSED before any HTTP
             call. See offload_spend_decision() for the rule and its reasoning.
             The gate reads the SAME cost_class the `offload` line prints, so
             the log and the ceiling can never disagree.

Usage:
  python3 free_lane_diag.py offload
  python3 free_lane_diag.py offload-gate --burn-degraded 1 [--opt-in 1]
  python3 free_lane_diag.py classify logs/generate-20260929-051500.log
"""
import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import or_complete  # noqa: E402

# A free slug, in the two spellings the fleet actually uses: OpenRouter's
# ":free" suffix and the bare "-free" aliases the external lane passes
# (nemotron-3-ultra-550b-free resolves to the ":free" slug provider-side).
FREE_SLUG_SUFFIXES = (":free", "-free")
LOCAL_HOST_MARKERS = ("localhost", "127.0.0.1", "0.0.0.0", "::1", ".local")

# Machine-readable cost classes. `describe_offload_route()` renders the prose and
# offload_spend_decision() gates on these — one classification, two readers.
COST_FREE = "free"        # provably $0: a local endpoint, or an explicit :free/-free slug
COST_METERED = "metered"  # a slug with no free marker: the price tier lives at the provider
COST_UNKNOWN = "unknown"  # not resolvable from config — treated as billable, never as $0

ERROR_LINE_MARKERS = (
    "provider error (",
    "HTTP Error ",
    "dispatch FAILED",
    "completion failed",
    "no offload API key",
    "no model (",
)


# ── offload lane ─────────────────────────────────────────────────────────────

def _is_local(base: str) -> bool:
    return any(m in (base or "").lower() for m in LOCAL_HOST_MARKERS)


def _is_free_slug(model: str) -> bool:
    m = (model or "").lower()
    return any(m.endswith(s) for s in FREE_SLUG_SUFFIXES)


def _key_candidates() -> list[tuple[str, str]]:
    """(source, value) for the key precedence chain in or_complete._config().

    Re-derived rather than imported so we can NAME the source. Compared against
    the key _config() actually returned, so if or_complete's precedence ever
    changes this reports 'unknown' instead of quietly lying.
    """
    offload = or_complete._read_env_file(or_complete.OFFLOAD_ENV)
    legacy = or_complete._read_env_file(or_complete.LEGACY_OR_ENV)
    return [
        ("env OFFLOAD_API_KEY", os.getenv("OFFLOAD_API_KEY") or ""),
        ("offload.env OFFLOAD_API_KEY", offload.get("OFFLOAD_API_KEY") or ""),
        ("env OPENROUTER_API_KEY", os.getenv("OPENROUTER_API_KEY") or ""),
        ("legacy openrouter.env OPENROUTER_API_KEY",
         legacy.get("OPENROUTER_API_KEY") or ""),
    ]


def _base_source(base: str) -> str:
    offload = or_complete._read_env_file(or_complete.OFFLOAD_ENV)
    if os.getenv("OFFLOAD_BASE_URL") and base == os.getenv("OFFLOAD_BASE_URL").rstrip("/"):
        return "env OFFLOAD_BASE_URL"
    if offload.get("OFFLOAD_BASE_URL") and base == offload["OFFLOAD_BASE_URL"].rstrip("/"):
        return "offload.env OFFLOAD_BASE_URL"
    if base == or_complete.DEFAULT_BASE:
        return "or_complete.DEFAULT_BASE — NO OFFLOAD_BASE_URL is configured"
    return "unknown source"


def offload_route() -> dict:
    """What or_complete.complete() will actually call. The key is never returned."""
    base, key, model, _effort = or_complete._config()
    if key:
        source = next((name for name, val in _key_candidates() if val and val == key), None)
        key_source = source or "unknown (or_complete._config() precedence changed — re-check)"
    else:
        key_source = "NONE — or_writer.py fails before it dispatches"

    warnings: list[str] = []
    # cost_class is the machine-readable twin of the `cost` sentence below, and the
    # ONLY thing the spend gate is allowed to read. It is computed in the same if/elif
    # chain as the prose on purpose: a second classifier in a second file is how the
    # 2026-09-29 05:26 402 happened (the log said "$0", the call went to a metered
    # route). One chain, one answer, used by both the log line and the gate.
    if not model:
        cost_class = COST_UNKNOWN
        cost = "UNKNOWN — no model set; or_complete.complete() raises 'no model'"
    elif _is_local(base):
        cost_class = COST_FREE
        cost = "FREE (local/self-hosted endpoint)"
    elif _is_free_slug(model):
        cost_class = COST_FREE
        cost = ("explicit free slug — $0 per call, but it draws the shared daily free bucket "
                "and starts 402ing once that bucket is empty")
    else:
        cost_class = COST_METERED
        # We can read the slug; we cannot read what the provider charges for it, and
        # the same slug can be $0 on one key tier and billed on another. Say so
        # instead of picking a side — the 09-29 run's cost was a false $0 claim.
        cost = ("NOT a free slug (:free/-free) — assume this call COSTS MONEY; the price tier "
                "lives at the provider, not in offload.env, so it cannot be confirmed here")

    if base == or_complete.DEFAULT_BASE:
        warnings.append(
            "nothing configured: offload.env names no base, so this call goes to openrouter.ai "
            "— if the key is a legacy/funded one, it SPENDS MONEY and 402s when overdrawn "
            "(exactly the 2026-09-29 05:26 failure)")
    if not key:
        warnings.append("no API key resolved — the call cannot succeed at all")
    if not model:
        warnings.append("no model resolved — or_complete.complete() will raise before dispatching")
    if key and "legacy" in key_source:
        warnings.append("the key came from the legacy OpenRouter file, not from offload.env")

    return {
        "base": base or "(unset)",
        "base_source": _base_source(base),
        "model": model or "(unset)",
        "cost": cost,
        "cost_class": cost_class,
        "key_source": key_source,
        "has_key": bool(key),
        "warnings": warnings,
    }


def describe_offload_route() -> str:
    r = offload_route()
    out = (f"base={r['base']} ({r['base_source']})  model={r['model']}  "
           f"cost={r['cost']}  key={r['key_source']}")
    if r["warnings"]:
        out += "  ⚠ " + "; ".join(r["warnings"])
    return out


def offload_spend_decision(burn_degraded: bool, opt_in: bool = False) -> dict:
    """May the offload fallback dispatch RIGHT NOW, given the burn gate?

    The decision (2026-09-30, brainrot-radio PR #48). Before this, run_kimi_pass
    called or_writer.py against whatever offload.env resolved to with NO ceiling
    on what it could spend — and the one time that mattered, the burn gate was up
    (BURN_DEGRADED=1, the exact condition that forces the external free lane),
    the Claude pass had just failed, and the fallback 402'd on an overdrawn
    OpenRouter line. The fallback was spending the money the gate existed to
    protect, in the one run where the gate was screaming.

    The rule, in one line: WHILE THE BURN GATE IS UP, THIS LANE MAY NOT BILL.
    Otherwise it may, because the ceiling is the gate and the gate is up precisely
    to say "spend nothing marginal today" (Kyle's 2026-09-08 ruling).

      * gate UP   + route is provably $0        -> ALLOW (a free slug or localhost
                                                  costs nothing; the free daily
                                                  bucket is a rate limit, not a bill)
      * gate UP   + route metered / unresolvable -> REFUSE. Fail loud, dispatch
                                                  nothing, and let the Claude path
                                                  carry the episode — $0 on the Max
                                                  pool, which is the whole point of
                                                  degrading instead of skipping.
      * gate UP   + PODCAST_OFFLOAD_ALLOW_BILLING=1 -> ALLOW. A human running this
                                                  by hand has said "yes, bill me",
                                                  per run, in the environment. The
                                                  launchd job never sets it.
      * gate DOWN                                -> ALLOW. The daily default is
                                                  100% Claude and this lane only
                                                  runs when Claude has already
                                                  failed, so a metered call here is
                                                  a deliberate rescue of the episode,
                                                  not a background bleed — and the
                                                  gate is down, so nothing is
                                                  protected by refusing it.

    Fail-closed on error: if the route cannot be resolved, that is UNKNOWN, and
    UNKNOWN is treated as billable. A reporting tool that cannot tell must never
    wave a paid call through.
    """
    try:
        r = offload_route()
    except Exception as e:  # noqa: BLE001
        # Fail closed HERE, not just at the CLI edge: a caller importing this
        # function gets the same answer. "Could not resolve the route" becomes
        # UNKNOWN, and UNKNOWN is billable — never "$0".
        r = {"cost_class": COST_UNKNOWN,
             "route": f"route unresolved ({e}) — do NOT assume this lane is free"}
    cls = r["cost_class"]
    allowed = True
    if burn_degraded and cls != COST_FREE and not opt_in:
        allowed = False

    if not burn_degraded:
        why = ("burn gate is NOT up (BURN_DEGRADED=0) — the daily default is 100% Claude at $0 "
               "on the Max pool, and this lane only runs after a Claude pass has already failed, "
               "so a metered call here is a deliberate rescue of the episode, not a background "
               "bleed. Allowed.")
    elif opt_in:
        why = ("burn gate is UP, but PODCAST_OFFLOAD_ALLOW_BILLING=1 was set for this run — an "
               "explicit human opt-in to bill. Allowed, and this line is the receipt.")
    elif cls == COST_FREE:
        why = "burn gate is UP and this route is provably $0 (local endpoint or an explicit free slug). Allowed."
    else:
        why = ("burn gate is UP and this route cannot be shown to be free, so this call MAY BILL "
               "money the burn gate exists to protect. REFUSED — nothing was dispatched. The Claude "
               "path carries the episode instead ($0 on the Max pool). To override for one run by "
               "hand: PODCAST_OFFLOAD_ALLOW_BILLING=1.")

    return {
        "allowed": allowed,
        "cost_class": cls,
        "burn_degraded": burn_degraded,
        "opt_in": opt_in,
        "route": r["route"] if "route" in r else describe_offload_route(),
        "why": why,
    }


def describe_offload_spend_decision(burn_degraded: bool, opt_in: bool = False) -> str:
    d = offload_spend_decision(burn_degraded, opt_in)
    return f"{'ALLOW' if d['allowed'] else 'REFUSE'}: {d['why']}  [{d['route']}]"


# ── free-lane failure classification ─────────────────────────────────────────

def _last_error_line(text: str) -> tuple[str, str]:
    """(lane, line) for the last provider-error-looking line in `text`."""
    lane, hit = "unknown", ""
    for line in text.splitlines():
        if any(marker in line for marker in ERROR_LINE_MARKERS):
            lane = ("external_writer" if line.startswith("external_writer")
                    else "or_writer" if line.startswith("or_writer") else "unknown")
            hit = line
    return lane, hit


def _field(line: str, name: str) -> str:
    m = re.search(rf'"{re.escape(name)}":\s*(?:"([^"]*)"|([0-9.]+)|(null))', line)
    if not m:
        return ""
    return (m.group(1) or m.group(2) or m.group(3) or "")


def _reset_utc(raw: str) -> str:
    """X-RateLimit-Reset → 'YYYY-MM-DD HH:MM UTC (in 3h 4m)'."""
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return ""
    secs = val / 1000.0 if val > 1e11 else val
    try:
        when = datetime.fromtimestamp(secs, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return ""
    delta = (when - datetime.now(timezone.utc)).total_seconds()
    if delta >= 0:
        rel = f"in {int(delta // 3600)}h {int(delta % 3600 // 60)}m"
    else:
        rel = f"{int(-delta // 60)}m AGO — the bucket has already reset"
    return f"{when.strftime('%Y-%m-%d %H:%M')} UTC ({rel})"


def classify_error_line(lane: str, line: str) -> str:
    """One line: what happened, and the remedy that actually follows from it."""
    limit_source = _field(line, "limit_source")
    message = _field(line, "message")
    code = _field(line, "code")
    m = re.search(r"HTTP Error (\d+)", line)
    if m:
        code = m.group(1)
    model = ""
    m = re.search(r"provider error \(([^)]*)\)", line)
    if m:
        model = m.group(1)
    limit = _field(line, "X-RateLimit-Limit")
    remaining = _field(line, "X-RateLimit-Remaining")
    reset = _reset_utc(_field(line, "X-RateLimit-Reset"))
    where = f" [{lane}]" if lane != "unknown" else ""
    head = f"free-lane failure{where}"

    if code == "402" or "Payment Required" in line or "insufficient credit" in line.lower():
        return (f"{head}: PAYMENT 402 — the lane's key is out of credit. That is a "
                f"billing problem, not a free-model problem: check that key's balance. "
                f"Rotating external_writer.py DEFAULT_MODEL will NOT fix a 402.")

    if limit_source:
        src = limit_source.lower()
        if "daily" in src or "account" in src or "per-day" in message.lower():
            bucket = f"{remaining or '?'} of {limit or '?'} requests left" if limit else ""
            when = f"; bucket resets {reset}" if reset else ""
            return (f"{head}: ACCOUNT-LEVEL DAILY BUCKET (limit_source={limit_source}"
                    f"{', ' + bucket if bucket else ''}{when}). Every free-model dispatch on "
                    f"this key draws the same bucket — the show is one of several fleet-wide "
                    f"consumers of it — so rotating external_writer.py DEFAULT_MODEL to another "
                    f":free slug will NOT help. Remedy: wait for the reset, or route through a "
                    f"different free provider/account, or let the Claude path carry the run.")
        if "model" in src:
            return (f"{head}: PER-MODEL QUOTA (limit_source={limit_source}). The quota belongs to "
                    f"the slug, not the account — rotating external_writer.py DEFAULT_MODEL to "
                    f"another free model WILL help.")
        return (f"{head}: UNKNOWN limit_source={limit_source}. Do not change DEFAULT_MODEL on a "
                f"guess — read the error line above first.")

    if code == "404" or re.search(r"no endpoints|not found|does not exist|not available for free",
                                  line, re.I):
        return (f"{head}: MODEL UNAVAILABLE ({model or 'slug'}) — the slug is gone or is not "
                f"served free right now. Rotating external_writer.py DEFAULT_MODEL is the fix "
                f"(the 2026-09-08 case, provider closed the free window).")

    if code == "429":
        return (f"{head}: 429 with no limit_source in the body — cannot tell an account bucket "
                f"from a per-model quota. Read the error above before changing DEFAULT_MODEL.")

    return (f"{head}: could not classify this error — read the line above before changing "
            f"external_writer.py DEFAULT_MODEL or any provider key.")


def classify_log(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return (f"free-lane failure: no result log at {p} — cannot classify. Read the run's "
                f"log before changing external_writer.py DEFAULT_MODEL.")
    try:
        text = p.read_text(errors="replace")
    except OSError as e:
        return f"free-lane failure: could not read {p} ({e}) — cannot classify."
    lane, line = _last_error_line(text)
    if not line:
        return ("free-lane failure: no provider error found in the log — the lane failed for a "
                "reason that isn't a provider 4xx/5xx. Read the run's log before changing "
                "external_writer.py DEFAULT_MODEL.")
    return classify_error_line(lane, line)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("offload", help="print the offload lane as or_complete._config() resolves it")
    g = sub.add_parser("offload-gate",
                       help="may the offload fallback dispatch right now? exit 0 = yes, 3 = no")
    g.add_argument("--burn-degraded", choices=("0", "1"), required=True,
                   help="pass generate-episode.sh's BURN_DEGRADED verbatim")
    g.add_argument("--opt-in", choices=("0", "1"), default="0",
                   help="1 when PODCAST_OFFLOAD_ALLOW_BILLING is set for this run")
    c = sub.add_parser("classify", help="diagnose the last provider error in a run log")
    c.add_argument("logfile")
    args = ap.parse_args()
    try:
        if args.cmd == "offload":
            print(describe_offload_route())
        elif args.cmd == "offload-gate":
            d = offload_spend_decision(args.burn_degraded == "1", args.opt_in == "1")
            print(describe_offload_spend_decision(args.burn_degraded == "1", args.opt_in == "1"))
            return 0 if d["allowed"] else 3
        else:
            print(classify_log(args.logfile))
    except Exception as e:  # noqa: BLE001 — a reporting tool must never break a run
        print(f"free_lane_diag could not answer ({e}) — read the run's log; do NOT assume the "
              f"lane is free and do NOT change DEFAULT_MODEL on a guess.")
        if args.cmd == "offload-gate":
            # Fail CLOSED on the gate. "Could not resolve the route" is not "$0" —
            # that conflation is the 2026-09-29 402. With the burn gate up we refuse;
            # with it down the answer was ALLOW anyway, so the exit code is the same
            # as the decision we would have reached. The opt-in is honoured on the
            # next attempt, when the config can be read.
            return 3 if args.burn_degraded == "1" and args.opt_in != "1" else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
