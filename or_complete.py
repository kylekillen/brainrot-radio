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

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


def _key() -> str:
    k = os.getenv("OPENROUTER_API_KEY", "")
    if k:
        return k
    f = Path.home() / ".config" / "personal-os" / "openrouter.env"
    try:
        for line in f.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def complete(prompt: str, model: str, system: str = "", max_tokens: int = 8000,
             timeout: int = 600) -> str:
    key = _key()
    if not key:
        raise RuntimeError("no OPENROUTER_API_KEY (env or ~/.config/personal-os/openrouter.env)")
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    body = json.dumps({"model": model, "messages": msgs,
                       "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(
        ENDPOINT, data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "HTTP-Referer": "https://github.com/kylekillen/brainrot-radio",
                 "X-Title": "Killen Time fleet offload"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    if "choices" not in data:
        raise RuntimeError(f"OpenRouter error: {json.dumps(data)[:400]}")
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
    ap.add_argument("--model", required=True, help="e.g. z-ai/glm-4.6, moonshotai/kimi-k2-0905, deepseek/deepseek-chat")
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
