#!/usr/bin/env python3
"""Tests for the offload fallback COST CEILING (free_lane_diag.offload_spend_decision
and the run_kimi_pass gate in generate-episode.sh).

Context: on 2026-09-29 at 05:26 the offload fallback ran with BURN_DEGRADED=1 — the
burn gate was UP, which is the entire reason the pipeline had degraded to the free
external lane — and the fallback 402'd against an overdrawn OpenRouter line. The
fallback was allowed to spend money in the one run where the fleet was explicitly
trying to spend none. PR #47 made the log honest about the route; these tests pin
the CEILING, which PR #47 deliberately did not add.

The rule under test: while the burn gate is up, this lane may not bill. A route
that is not provably $0 is refused BEFORE any dispatch, and the Claude path (the
Max pool, $0 marginal) carries the episode instead.

The load-bearing test is `test_refused_pass_never_dispatches` — it runs the real
run_kimi_pass out of the real generate-episode.sh with a stub python3 on PATH, and
asserts or_writer.py is never invoked. Everything else is the decision function.
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import free_lane_diag  # noqa: E402
import or_complete  # noqa: E402

SHELL = os.path.join(ROOT, "generate-episode.sh")


@pytest.fixture
def config(tmp_path, monkeypatch):
    """Point or_complete's env files at tmp_path and clear the process env."""
    for var in ("OFFLOAD_BASE_URL", "OFFLOAD_API_KEY", "OFFLOAD_MODEL",
                "OPENROUTER_API_KEY", "OFFLOAD_REASONING_EFFORT"):
        monkeypatch.delenv(var, raising=False)
    offload = tmp_path / "offload.env"
    legacy = tmp_path / "openrouter.env"
    monkeypatch.setattr(or_complete, "OFFLOAD_ENV", offload)
    monkeypatch.setattr(or_complete, "LEGACY_OR_ENV", legacy)
    return offload, legacy


# The exact 2026-09-29 05:26 shape: no base, no key in offload.env, so
# or_complete falls through to openrouter.ai + the legacy funded key, with a
# model that carries no free marker. Metered, and it 402'd.
def _metered(config):
    offload, legacy = config
    offload.write_text("OFFLOAD_MODEL=gemini-flash-latest\n")
    legacy.write_text("OPENROUTER_API_KEY=sk-legacy-funded\n")


# ── the ceiling: burn gate UP ────────────────────────────────────────────────

def test_burn_gate_up_refuses_a_metered_route(config):
    """The 09-29 failure, as a guard: gate up + metered route = no dispatch."""
    _metered(config)
    d = free_lane_diag.offload_spend_decision(burn_degraded=True)
    assert d["allowed"] is False
    assert d["cost_class"] == free_lane_diag.COST_METERED
    assert "MAY BILL" in d["why"]
    assert "REFUSED" in d["why"]
    # The remedy it names is the $0 one, not "spend a little".
    assert "Max pool" in d["why"]
    assert "PODCAST_OFFLOAD_ALLOW_BILLING=1" in d["why"]


def test_burn_gate_up_allows_a_provably_free_route(config):
    """A :free slug costs nothing, so the ceiling must not stop it. The free
    DAILY BUCKET is a rate limit, not a bill — refusing this would be a
    self-inflicted 429 with no money saved."""
    offload, _ = config
    offload.write_text("OFFLOAD_BASE_URL=https://openrouter.ai/api/v1\n"
                       "OFFLOAD_API_KEY=k\nOFFLOAD_MODEL=some/model:free\n")
    d = free_lane_diag.offload_spend_decision(burn_degraded=True)
    assert d["allowed"] is True
    assert d["cost_class"] == free_lane_diag.COST_FREE
    assert "provably $0" in d["why"]


def test_local_endpoint_is_free_under_the_gate(config):
    offload, _ = config
    offload.write_text("OFFLOAD_BASE_URL=http://127.0.0.1:11434/v1\n"
                       "OFFLOAD_API_KEY=k\nOFFLOAD_MODEL=llama3\n")
    assert free_lane_diag.offload_spend_decision(burn_degraded=True)["allowed"] is True


# ── the local-endpoint test is a money guard, so it must not be gameable ────
# Code review (codex-cli, 2026-09-30) on this PR: _is_local() was a substring
# test over the whole URL, so any remote host CONTAINING a local-looking string
# read as free and walked straight past the ceiling. Every one of these is a
# real remote host; all three were classified FREE before the fix.

@pytest.mark.parametrize("base", [
    "https://localhost.billing-provider.example/v1",  # reviewer-reported
    "https://localhost.attacker.io/v1",
    "http://notlocalhost.example.com/v1",
    "https://evil-local.attacker.com/v1",
    "http://127.0.0.1.attacker.example/v1",
    "https://api.example.com/localhost/v1",          # the string was in the PATH
    "https://example.com/v1?host=localhost",         # ...and in the query
    "https://example.com/localhost",                 # ...and in the path alone
])
def test_remote_host_containing_a_local_looking_string_is_not_free(base):
    assert free_lane_diag._is_local(base) is False


@pytest.mark.parametrize("base", [
    "http://localhost:11434/v1",
    "http://127.0.0.1:1234/v1",
    "http://127.0.0.53:1/v1",        # any address in 127.0.0.0/8 is loopback
    "http://[::1]:8080/v1",          # IPv6 loopback
    "localhost:11434/v1",            # no scheme — or_complete allows this form
    "http://LOCALHOST:1234/v1",      # hostnames are case-insensitive
    "http://localhost.:1234/v1",     # trailing root dot
    "http://myserver.local:1234/v1", # mDNS link-local
])
def test_genuine_loopback_hosts_are_still_free(base):
    assert free_lane_diag._is_local(base) is True


@pytest.mark.parametrize("base", [
    "",                        # unset
    "not a url at all",
    "https://openrouter.ai/api/v1",
    "https://generativelanguage.googleapis.com/v1beta/openai",
    "http://10.0.0.5:11434/v1",  # private LAN — routable, not loopback
])
def test_non_loopback_hosts_are_not_free(base):
    assert free_lane_diag._is_local(base) is False


def test_a_spoofed_local_base_is_refused_by_the_gate_not_just_mislogged(config):
    """End to end: the bypass has to be closed at the DECISION, not only in the
    cost label. A base that merely contains 'localhost' must not buy a dispatch
    while the burn gate is up — that is the whole attack."""
    offload, _ = config
    offload.write_text("OFFLOAD_BASE_URL=https://localhost.billing-provider.example/v1\n"
                       "OFFLOAD_API_KEY=k\nOFFLOAD_MODEL=gemini-flash-latest\n")
    r = free_lane_diag.offload_route()
    assert r["cost_class"] == free_lane_diag.COST_METERED
    d = free_lane_diag.offload_spend_decision(burn_degraded=True)
    assert d["allowed"] is False
    assert "MAY BILL" in d["why"]


def test_local_host_classification_is_shared_by_the_gate_and_the_log(config):
    """The ceiling and the printed cost class must move together, or a spoofed
    base gets one answer in the log and another at the gate."""
    offload, _ = config
    offload.write_text("OFFLOAD_BASE_URL=https://localhost.billing-provider.example/v1\n"
                       "OFFLOAD_API_KEY=k\nOFFLOAD_MODEL=llama3\n")
    out = free_lane_diag.describe_offload_route()
    assert "FREE" not in out
    assert "COSTS MONEY" in out
    assert free_lane_diag.offload_spend_decision(True)["allowed"] is False


def test_burn_gate_up_refuses_when_nothing_is_configured(config):
    """Unresolvable is not free. Nothing configured means DEFAULT_BASE, and the
    call cannot succeed anyway — refusing costs nothing and cannot be wrong."""
    d = free_lane_diag.offload_spend_decision(burn_degraded=True)
    assert d["allowed"] is False
    assert d["cost_class"] == free_lane_diag.COST_UNKNOWN


def test_unresolvable_route_fails_closed_not_open(config, monkeypatch):
    """If the route cannot even be resolved, REFUSE. A reporting tool that cannot
    tell must never wave a possibly-billed call through — that is the 09-29 402."""
    def boom():
        raise RuntimeError("cannot read _config()")
    monkeypatch.setattr(free_lane_diag, "offload_route", boom)
    d = free_lane_diag.offload_spend_decision(burn_degraded=True)
    assert d["allowed"] is False
    assert d["cost_class"] == free_lane_diag.COST_UNKNOWN
    assert "do NOT assume this lane is free" in d["route"]


# ── the opt-in: a human, per run, in the environment ────────────────────────

def test_opt_in_overrides_the_ceiling_and_leaves_a_receipt(config):
    _metered(config)
    d = free_lane_diag.offload_spend_decision(burn_degraded=True, opt_in=True)
    assert d["allowed"] is True
    assert "opt-in" in d["why"]
    assert "receipt" in d["why"]   # the allow line is auditable, not silent


def test_opt_in_is_honoured_even_when_the_route_cannot_be_resolved(config, monkeypatch):
    def boom():
        raise RuntimeError("cannot read _config()")
    monkeypatch.setattr(free_lane_diag, "offload_route", boom)
    assert free_lane_diag.offload_spend_decision(True, opt_in=True)["allowed"] is True


# ── gate DOWN: unchanged behaviour, and deliberately so ──────────────────────

def test_gate_down_allows_a_metered_route(config):
    """With the gate down this lane is a deliberate rescue of a failed episode,
    not a background bleed. Refusing here would change behaviour nobody asked to
    change, so the ceiling is scoped to the gate and says so."""
    _metered(config)
    d = free_lane_diag.offload_spend_decision(burn_degraded=False)
    assert d["allowed"] is True
    assert "burn gate is NOT up" in d["why"]


# ── one source of truth: the gate and the log read the same field ───────────

def test_gate_and_log_agree_on_cost_class(config):
    """If these ever read different classifiers, the ceiling and the log can
    disagree — which is the failure this whole file exists to prevent."""
    _metered(config)
    route = free_lane_diag.offload_route()
    decision = free_lane_diag.offload_spend_decision(burn_degraded=True)
    assert decision["cost_class"] == route["cost_class"]
    assert decision["allowed"] is (route["cost_class"] == free_lane_diag.COST_FREE)
    # ...and the prose the log prints carries the same verdict.
    assert "NOT a free slug" in free_lane_diag.describe_offload_route()


def test_cost_class_is_computed_in_the_same_chain_as_the_prose(config):
    """A slug with no free marker and one that ends :free must never share a class."""
    offload, _ = config
    offload.write_text("OFFLOAD_BASE_URL=https://example.test/v1\nOFFLOAD_API_KEY=k\n")
    offload.write_text("OFFLOAD_BASE_URL=https://example.test/v1\nOFFLOAD_API_KEY=k\n"
                       "OFFLOAD_MODEL=deepseek/deepseek-chat\n")
    assert free_lane_diag.offload_route()["cost_class"] == free_lane_diag.COST_METERED
    offload.write_text("OFFLOAD_BASE_URL=https://example.test/v1\nOFFLOAD_API_KEY=k\n"
                       "OFFLOAD_MODEL=deepseek/deepseek-chat:free\n")
    assert free_lane_diag.offload_route()["cost_class"] == free_lane_diag.COST_FREE


def test_the_gate_never_prints_the_key(config):
    _metered(config)
    for degraded in (True, False):
        for opt in (True, False):
            out = free_lane_diag.describe_offload_spend_decision(degraded, opt)
            assert "sk-legacy-funded" not in out


# ── the shell: the gate runs BEFORE the dispatch ────────────────────────────

def _extract_function(name: str) -> str:
    """Pull one top-level shell function out of the real generate-episode.sh.

    Read from the live file rather than a copy so the test cannot drift away
    from the thing it is guarding.
    """
    lines = open(SHELL).read().splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(f"{name}() {{"))
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "}")
    return "\n".join(lines[start:end + 1])


def _run_kimi_pass(tmp_path, gate_exit, burn_degraded="0", opt_in=None, name="run"):
    """Run the REAL run_kimi_pass with a stub python3 that records its argv.

    Returns (returncode, log_text, argv_lines). gate_exit is the exit code the
    stubbed free_lane_diag.py offload-gate returns — 0 to allow, 3 to refuse.
    Each call gets its own directory so a test that runs two cases cannot read
    the first one's argv.
    """
    work = tmp_path / name
    work.mkdir(parents=True, exist_ok=True)
    stub = work / "bin"
    stub.mkdir(exist_ok=True)
    argv_log = work / "argv.log"
    result_log = work / "result.log"
    result_log.write_text("")
    (stub / "python3").write_text(
        "#!/bin/bash\n"
        f'echo "$@" >> "{argv_log}"\n'
        'if [ "$1" = "free_lane_diag.py" ] && [ "$2" = "offload-gate" ]; then\n'
        '  echo "ALLOW: stub gate decision"\n'
        f"  exit {gate_exit}\n"
        "fi\n"
        'if [ "$1" = "free_lane_diag.py" ] && [ "$2" = "offload" ]; then\n'
        '  echo "base=https://example.test/v1 model=m cost=NOT a free slug key=offload.env"\n'
        "  exit 0\n"
        "fi\n"
        'if [ "$1" = "or_writer.py" ]; then echo "OR_WRITER_RAN"; exit 0; fi\n'
        "exit 0\n"
    )
    os.chmod(stub / "python3", 0o755)

    script = "\n".join([
        _extract_function("offload_route_log"),
        _extract_function("offload_billing_allowed"),
        _extract_function("run_kimi_pass"),
        f'BURN_DEGRADED="{burn_degraded}"',
        f'BRAINROT_DIR="{work}"',
        f'RESULT_LOG="{result_log}"',
        'SCRIPT_FILE="script.md"',
        'GREETING_HINT="hi"',
        f'export PATH="{stub}:$PATH"',
        'log() { echo "LOG: $*"; }',
        'run_kimi_pass 1',
        'echo "RC=$?"',
    ])
    if opt_in is not None:
        script = f'export PODCAST_OFFLOAD_ALLOW_BILLING="{opt_in}"\n' + script

    proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=60)
    argv = argv_log.read_text().splitlines() if argv_log.exists() else []
    dispatched = "OR_WRITER_RAN" in result_log.read_text()
    return proc.returncode, proc.stdout + proc.stderr, argv, dispatched


def test_refused_pass_never_dispatches(tmp_path):
    """THE load-bearing test. When the gate refuses, or_writer.py must not run:
    the whole point is that no billable HTTP call is made, so a guard placed
    after the dispatch would be worthless."""
    _, out, argv, dispatched = _run_kimi_pass(tmp_path, gate_exit=3, burn_degraded="1")
    assert dispatched is False
    assert "OR_WRITER_RAN" not in out
    assert not any("or_writer.py" in a for a in argv), argv
    assert "COST CEILING" in out
    assert "Nothing was dispatched" in out
    assert "RC=1" in out


def test_allowed_pass_does_dispatch(tmp_path):
    """And the guard must not be a tripwire: an allowed pass still writes."""
    _, out, argv, dispatched = _run_kimi_pass(tmp_path, gate_exit=0, burn_degraded="0")
    assert dispatched is True
    assert any("or_writer.py" in a for a in argv), argv
    assert "RC=0" in out


def test_refusal_names_the_route_and_the_remedy(tmp_path):
    _, out, _, _ = _run_kimi_pass(tmp_path, gate_exit=3, burn_degraded="1")
    assert "PODCAST_OFFLOAD_ALLOW_BILLING=1" in out   # the human override
    assert "Claude path carries the episode" in out   # what happens instead
    assert "Max pool" in out                          # ...at $0


def test_gate_is_consulted_before_the_route_is_used(tmp_path):
    """Ordering, asserted on argv: the gate is asked first, so a refusal costs
    no provider round-trip at all."""
    _, _, argv, _ = _run_kimi_pass(tmp_path, gate_exit=3, burn_degraded="1")
    gate_idx = next(i for i, a in enumerate(argv) if "offload-gate" in a)
    writer_idx = [i for i, a in enumerate(argv) if "or_writer.py" in a]
    assert not writer_idx
    assert gate_idx >= 0


def test_opt_in_env_is_what_the_gate_reads(tmp_path):
    """The override is an env var in the run's own environment — not a key in
    offload.env, which a config edit could turn on by accident."""
    _, _, argv, _ = _run_kimi_pass(tmp_path, gate_exit=0, burn_degraded="1",
                                   opt_in="1", name="with_optin")
    gate_line = next(a for a in argv if "offload-gate" in a)
    assert "--opt-in 1" in gate_line
    assert "--burn-degraded 1" in gate_line
    _, _, argv, _ = _run_kimi_pass(tmp_path, gate_exit=0, burn_degraded="1",
                                   name="without_optin")
    assert "--opt-in 0" in next(a for a in argv if "offload-gate" in a)


def test_launchd_never_sets_the_billing_opt_in():
    """If the scheduled job set PODCAST_OFFLOAD_ALLOW_BILLING, the ceiling would
    be decorative — every unattended run would bill."""
    plist = os.path.expanduser("~/Library/LaunchAgents/com.mojo.brainrot-radio.plist")
    if not os.path.exists(plist):
        pytest.skip("launchd plist not present in this environment")
    assert "PODCAST_OFFLOAD_ALLOW_BILLING" not in open(plist).read()


def test_shell_is_syntactically_valid():
    subprocess.run(["bash", "-n", SHELL], check=True, timeout=60)


# ── the CLI the shell actually calls ────────────────────────────────────────

def test_offload_gate_cli_exit_codes(tmp_path, monkeypatch):
    """0 = dispatch, 3 = refuse. The shell branches on the exit code, so these
    two numbers are the contract."""
    env = dict(os.environ, HOME=str(tmp_path))
    (tmp_path / ".config" / "personal-os").mkdir(parents=True)
    (tmp_path / ".config" / "personal-os" / "offload.env").write_text(
        "OFFLOAD_BASE_URL=https://example.test/v1\n"
        "OFFLOAD_API_KEY=sk-secret-must-never-be-printed\n"
        "OFFLOAD_MODEL=gemini-flash-latest\n")

    def run(*args):
        return subprocess.run([sys.executable, "free_lane_diag.py", "offload-gate", *args],
                              cwd=ROOT, capture_output=True, text=True, env=env, timeout=60)

    assert run("--burn-degraded", "1").returncode == 3
    assert run("--burn-degraded", "0").returncode == 0
    assert run("--burn-degraded", "1", "--opt-in", "1").returncode == 0
    out = run("--burn-degraded", "1").stdout
    assert "REFUSE" in out
    assert "sk-secret-must-never-be-printed" not in out
    assert "OFFLOAD_BASE_URL" in out      # the key SOURCE is named...
    assert "=sk-" not in out              # ...but never the key itself


def test_cli_help_documents_the_opt_in():
    out = subprocess.run([sys.executable, "free_lane_diag.py", "offload-gate", "--help"],
                         cwd=ROOT, capture_output=True, text=True, timeout=60).stdout
    assert "--burn-degraded" in out and "--opt-in" in out
