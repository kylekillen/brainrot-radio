#!/usr/bin/env python3
"""Tests for free_lane_diag.py and the generate-episode.sh log lines it backs.

Context: the 2026-09-29 05:15 run proved two hardcoded log lines false and both
misled an operator — the offload fallback announced a free provider while
or_complete._config() was about to fall through to openrouter.ai (which 402'd),
and the free-lane 429 warning always prescribed a model rotation that cannot
move an account-level daily bucket. These tests pin the corrected behaviour,
including the parts that must NOT come back ("$0", "fix DEFAULT_MODEL").
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import free_lane_diag  # noqa: E402
import or_complete  # noqa: E402

# Verbatim from logs/generate-20260929-051500.log line 354 (the real 429).
ACCOUNT_BUCKET_ERR = (
    'external_writer: write-pass1 dispatch FAILED: provider error '
    '(openrouter/openrouter/nvidia/nemotron-3-ultra-550b-a55b:free): RateLimitError: '
    'litellm.RateLimitError: RateLimitError: OpenrouterException - '
    '{"error":{"message":"Rate limit exceeded: free-models-per-day-high-balance. ",'
    '"code":429,"metadata":{"headers":{"X-RateLimit-Limit":"1000",'
    '"X-RateLimit-Remaining":"0","X-RateLimit-Reset":"1790726400000"},'
    '"limit_source":"openrouter_free_tier_daily","remedy_hint":"Wait for the daily '
    'reset (see X-RateLimit-Reset), or purchase credits to raise your free-model daily '
    'limit.","provider_name":null}},"user_id":"user_3FMTkKagDmaVzfw1KsmfhrQOPor"} '
    '(footer: cost unavailable this dispatch)'
)

PER_MODEL_ERR = (
    'external_writer: write-pass1 dispatch FAILED: provider error '
    '(openrouter/openrouter/nvidia/nemotron-3-ultra-550b-a55b:free): RateLimitError: '
    '{"error":{"message":"Rate limit exceeded","code":429,"metadata":'
    '{"headers":{"X-RateLimit-Limit":"20"},"limit_source":"openrouter_per_model_minute"}}}'
)

PAYMENT_ERR = ("or_writer: completion failed at max_tokens=16000: "
               "HTTP Error 402: Payment Required")
GONE_ERR = ('external_writer: pass 1 failed: provider error '
            '(openrouter/openrouter/nvidia/nemotron-3-ultra-550b-a55b:free): 404 '
            'No endpoints found for nvidia/nemotron-3-ultra-550b-a55b:free')


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


# ── offload lane: what will actually be called ───────────────────────────────

def test_configured_free_slug_reads_as_free_and_never_prints_the_key(config):
    offload, _ = config
    offload.write_text("OFFLOAD_BASE_URL=https://example.test/v1\n"
                       "OFFLOAD_API_KEY=sk-secret-value\n"
                       "OFFLOAD_MODEL=some/model:free\n")
    out = free_lane_diag.describe_offload_route()
    assert "base=https://example.test/v1" in out
    assert "offload.env OFFLOAD_BASE_URL" in out
    assert "model=some/model:free" in out
    assert "explicit free slug" in out
    assert "key=offload.env" in out
    assert "sk-secret-value" not in out
    assert "⚠" not in out  # nothing to warn about


def test_0915_shape_offload_env_without_key_falls_to_openrouter(config):
    """The 2026-09-29 failure: model configured, no key/base → DEFAULT_BASE +
    legacy OpenRouter key, i.e. metered, with a loud warning. Never "$0"."""
    offload, legacy = config
    offload.write_text("OFFLOAD_MODEL=gemini-flash-latest\n")
    legacy.write_text("OPENROUTER_API_KEY=or-legacy-secret\n")
    out = free_lane_diag.describe_offload_route()
    assert "base=https://openrouter.ai/api/v1" in out
    assert "NO OFFLOAD_BASE_URL is configured" in out
    assert "legacy" in out
    assert "or-legacy-secret" not in out
    assert "not a free slug" in out.lower() or "NOT a free slug" in out
    assert "SPENDS MONEY" in out
    assert "$0" not in out
    assert "openrouter.ai" in out  # the warning names where the money goes


def test_nothing_configured_at_all_is_unresolved_not_free(config):
    out = free_lane_diag.describe_offload_route()
    assert "model=(unset)" in out
    assert "no model set" in out
    assert "key=NONE" in out
    assert "cannot succeed" in out


def test_local_base_is_free_regardless_of_slug(config):
    offload, _ = config
    offload.write_text("OFFLOAD_BASE_URL=http://127.0.0.1:11434/v1\n"
                       "OFFLOAD_API_KEY=not-a-secret\nOFFLOAD_MODEL=llama3\n")
    assert "FREE (local/self-hosted endpoint)" in free_lane_diag.describe_offload_route()


def test_key_source_reports_unknown_if_precedence_changes(config, monkeypatch):
    """If or_complete's chain is edited, we say so rather than name a stale source."""
    offload, _ = config
    offload.write_text("OFFLOAD_API_KEY=k1\nOFFLOAD_MODEL=m:free\n")
    monkeypatch.setattr(free_lane_diag, "_key_candidates",
                        lambda: [("somewhere else", "k-different")])
    assert "precedence changed" in free_lane_diag.describe_offload_route()


# ── free-lane failure: the remedy follows from the error body ────────────────

def test_account_daily_bucket_never_prescribes_a_model_rotation():
    out = free_lane_diag.classify_error_line("external_writer", ACCOUNT_BUCKET_ERR)
    assert "ACCOUNT-LEVEL DAILY BUCKET" in out
    assert "limit_source=openrouter_free_tier_daily" in out
    assert "0 of 1000 requests left" in out
    assert "resets 2026-09-30 00:00 UTC" in out
    assert "will NOT help" in out          # the 09-08 rotation, correctly withheld
    assert "fleet-wide" in out


def test_per_model_quota_does_prescribe_a_model_rotation():
    out = free_lane_diag.classify_error_line("external_writer", PER_MODEL_ERR)
    assert "PER-MODEL QUOTA" in out
    assert "DEFAULT_MODEL" in out
    assert "WILL help" in out


def test_402_is_billing_not_a_model_problem():
    out = free_lane_diag.classify_error_line("or_writer", PAYMENT_ERR)
    assert "402" in out
    assert "billing problem" in out
    assert "NOT fix a 402" in out


def test_404_model_gone_is_a_rotation():
    out = free_lane_diag.classify_error_line("external_writer", GONE_ERR)
    assert "MODEL UNAVAILABLE" in out
    assert "DEFAULT_MODEL" in out


def test_429_without_limit_source_refuses_to_guess():
    out = free_lane_diag.classify_error_line("external_writer",
                                             "external_writer: dispatch FAILED: HTTP Error 429")
    assert "no limit_source" in out
    assert "Do not change DEFAULT_MODEL" in out or "before changing" in out


def test_missing_log_does_not_blame_the_model(tmp_path):
    out = free_lane_diag.classify_log(str(tmp_path / "nope.log"))
    assert "cannot classify" in out
    assert "before changing" in out


def test_reset_parses_seconds_as_well_as_milliseconds():
    # The same instant in the two spellings a provider might use.
    assert "2026-09-30 00:00 UTC" in free_lane_diag._reset_utc("1790726400")
    assert "2026-09-30 00:00 UTC" in free_lane_diag._reset_utc("1790726400000")
    assert free_lane_diag._reset_utc("not-a-number") == ""


def test_classify_log_takes_the_last_error_in_the_run(tmp_path):
    log = tmp_path / "generate-test.log"
    log.write_text(ACCOUNT_BUCKET_ERR + "\n" + PAYMENT_ERR + "\n")
    out = free_lane_diag.classify_log(str(log))
    assert "402" in out  # or_writer's payment failure is the later event


# ── the shell lines themselves ───────────────────────────────────────────────

def _log_lines():
    """The text each `log "..."` call will actually write.

    Deliberately not the whole file: a corrective COMMENT is allowed to name the
    claim it retracts ("it used to say ... currently free Gemini Flash"), and a
    guard that can't tell a claim from a retraction is a guard nobody keeps.
    """
    src = open(os.path.join(ROOT, "generate-episode.sh")).read()
    out = []
    for raw in src.splitlines():
        line = raw.strip()
        idx = line.find('log "')
        if idx == -1:
            continue
        end = line.rfind('"')
        if end > idx:
            out.append(line[idx + 5:end])
    return "\n".join(out)


def test_log_lines_carry_no_hardcoded_provider_claim():
    emitted = _log_lines()
    for false_claim in ("currently free Gemini Flash",      # proven false 2026-09-29
                        "OpenRouter (Kimi)",                # the call is provider-agnostic
                        "Fix the free lane",                # wrong remedy for a 429
                        "the fallback is also $0"):          # proven false 2026-09-29
        assert false_claim not in emitted, false_claim


def test_run_kimi_pass_resolves_the_route_it_logs():
    emitted = _log_lines()
    assert "free_lane_diag.py offload" in open(os.path.join(ROOT, "generate-episode.sh")).read()
    assert "offload_route_log()" in open(os.path.join(ROOT, "generate-episode.sh")).read()
    # The fallback announcement must carry the resolved route, not a remembered name.
    assert any("Resolved right now: $route" in line for line in emitted.splitlines()
               if "FALLBACK: routing write-pass" in line)


def test_burn_degraded_warning_classifies_instead_of_prescribing():
    emitted = _log_lines()
    assert any("free_lane_diag.py classify" in line and "BURN-DEGRADED" not in line
               for line in emitted.splitlines())


def test_or_writer_stderr_names_the_resolved_route_not_a_provider():
    src = open(os.path.join(ROOT, "or_writer.py")).read()
    emitted = "\n".join(line for line in src.splitlines()
                        if "sys.stderr.write" in line or line.strip().startswith("f\""))
    assert "via OpenRouter" not in emitted
    assert "describe_offload_route()" in src
