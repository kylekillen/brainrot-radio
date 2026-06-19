#!/usr/bin/env python3
"""or_complete.py — OpenRouter chat-completion helper (OpenAI-compatible).

The building block for offloading NON-critical, content-generation fleet work
off the Claude Max pool onto pay-as-you-go open models (GLM / Kimi / DeepSeek)
via OpenRouter. Stays OUT of any money/trading path (credit-resilience guardrail).

Usage:
  echo "<prompt>" | or_complete.py --model z-ai/glm-4.6 [--max-tokens N] [--system "..."]
  or_complete.py --model deepseek/deepseek-chat --prompt "..."

Key: OPENROUTER_API_KEY env, else ~/.config/personal-os/openrouter.env.
Exit 0 + completion on stdout; non-zero + message on stderr on failure (so a
caller can fall back to Claude).
"""
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

# Provider config (precedence: env vars → ~/.config/personal-os/offload.env →
# legacy OpenRouter fallback). Repoint to whichever PAYG provider Kyle's card/
# PayPal works with — DeepSeek (api.deepseek.com/v1), Hugging Face
# (router.huggingface.co/v1), Together, DeepInfra, OpenRouter — by editing ONE
# file, no code change. All are OpenAI-compatible /chat/completions.
#   offload.env:  OFFLOAD_BASE_URL=...  OFFLOAD_API_KEY=...  OFFLOAD_MODEL=...
DEFAULT_BASE = "https://openrouter.ai/api/v1"
OFFLOAD_ENV = Path.home() / ".config" / "personal-os" / "offload.env"
LEGACY_OR_ENV = Path.home() / ".config" / "personal-os" / "openrouter.env"


def _read_env_file(path: Path) -> dict:
    out: dict = {}
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def _config() -> tuple[str, str, str]:
    """(base_url, api_key, default_model). env > offload.env > legacy OpenRouter."""
    f = _read_env_file(OFFLOAD_ENV)
    leg = _read_env_file(LEGACY_OR_ENV)
    base = os.getenv("OFFLOAD_BASE_URL") or f.get("OFFLOAD_BASE_URL") or DEFAULT_BASE
    key = (os.getenv("OFFLOAD_API_KEY") or f.get("OFFLOAD_API_KEY")
           or os.getenv("OPENROUTER_API_KEY") or leg.get("OPENROUTER_API_KEY") or "")
    model = os.getenv("OFFLOAD_MODEL") or f.get("OFFLOAD_MODEL") or ""
    return base.rstrip("/"), key, model


def complete(prompt: str, model: str = "", system: str = "", max_tokens: int = 8000,
             timeout: int = 600) -> str:
    base, key, default_model = _config()
    model = model or default_model
    if not key:
        raise RuntimeError("no offload API key (set ~/.config/personal-os/offload.env "
                           "OFFLOAD_API_KEY, or legacy openrouter.env)")
    if not model:
        raise RuntimeError("no model (pass model= or set OFFLOAD_MODEL)")
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    body = json.dumps({"model": model, "messages": msgs,
                       "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(
        base + "/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "HTTP-Referer": "https://github.com/kylekillen/brainrot-radio",
                 "X-Title": "Killen Time fleet offload"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    if "choices" not in data:
        raise RuntimeError(f"provider error: {json.dumps(data)[:400]}")
    ch = data["choices"][0]
    content = (ch.get("message") or {}).get("content")
    if not content:
        # e.g. a reasoning model burned the whole budget on reasoning, or a
        # truncation — fail clearly so the caller can fall back to Claude.
        raise RuntimeError(
            f"empty content (finish_reason={ch.get('finish_reason')}); "
            f"raise --max-tokens or use a non-reasoning model")
    return content


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="", help="override OFFLOAD_MODEL, e.g. deepseek-chat, moonshotai/Kimi-K2.6, z-ai/glm-4.6")
    ap.add_argument("--prompt", help="prompt text (else read stdin)")
    ap.add_argument("--system", default="")
    ap.add_argument("--max-tokens", type=int, default=8000)
    args = ap.parse_args()
    prompt = args.prompt if args.prompt is not None else sys.stdin.read()
    try:
        sys.stdout.write(complete(prompt, args.model, args.system, args.max_tokens))
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"or_complete failed: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
