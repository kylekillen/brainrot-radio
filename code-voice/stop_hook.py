#!/usr/bin/env python3
"""Code Voice — Claude Code Stop hook.

Fires when a session finishes a turn. Reads the Stop-hook JSON from stdin,
pulls Claude's last response out of the transcript, cleans the markdown,
and POSTs it to the resident warm server (which summarizes + speaks it).

Opt-in: does nothing unless the flag file exists. Default OFF so background
workers / the COS aren't narrated.
    touch /tmp/claude-voice-enabled    # turn on for ALL sessions
    rm    /tmp/claude-voice-enabled    # turn off everywhere

Per-session scoping: if the flag file is non-empty, each non-blank line is
treated as a cwd substring allowlist — only sessions whose working directory
matches a line are narrated. This keeps the COS / other projects silent while
you listen to one. Example (narrate only brainrot-radio sessions):
    echo /Users/kylekillen/brainrot-radio > /tmp/claude-voice-enabled

Stdlib only — runs under whatever python3 the session has. Fast and silent;
never blocks the session (always exits 0, no stdout) and fires the POST in
a detached background thread so afplay/synth latency never delays the prompt.
"""
import json
import os
import sys
import threading
import time
from pathlib import Path

FLAG = Path("/tmp/claude-voice-enabled")
LOG = Path(__file__).resolve().parent / "phone_hook.log"


def _log(msg: str):
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG, "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except OSError:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from text_clean import strip_markdown
except Exception:  # noqa: BLE001 — never let an import failure break the session
    def strip_markdown(text):
        return text


def _assistant_messages(transcript_path: str):
    """Yield (text, has_tool_use) for each assistant message, in order."""
    out = []
    try:
        with open(transcript_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "assistant":
                    continue
                msg = obj.get("message")
                if not isinstance(msg, dict) or msg.get("role") != "assistant":
                    continue
                content = msg.get("content")
                if not isinstance(content, list):
                    continue
                parts = [
                    c.get("text", "")
                    for c in content
                    if isinstance(c, dict) and c.get("type") == "text"
                ]
                has_tool = any(
                    isinstance(c, dict) and c.get("type") == "tool_use" for c in content
                )
                text = "\n".join(p for p in parts if p.strip())
                out.append((text, has_tool))
    except OSError:
        return []
    return out


def is_cos_session(transcript_path: str) -> bool:
    """True if this session is the Chief of Staff.

    The COS loads its identity CLAUDE.md as an `attachment` entry containing
    "You are the COS" / "You are the Chief of Staff". A session that merely
    DISCUSSES the COS has those strings only in user/assistant message text,
    never in an attachment — so this never false-positives on a normal
    session talking about the COS. Identity-based: works wherever the COS
    roams, no cwd or restart needed.
    """
    try:
        with open(transcript_path) as f:
            for line in f:
                if "You are the COS" in line or "You are the Chief of Staff" in line:
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("type") == "attachment":
                        return True
    except OSError:
        return False
    return False


def final_prose_text(transcript_path: str) -> str:
    """Text of my closing summary — ONLY if the transcript's last assistant
    message is pure prose (text, no tool call).

    The harness writes preamble text (the line before a tool call) as its own
    text-only message, with the tool calls in later messages — so a preamble
    is never the LAST assistant message, my closing summary is. Returning ""
    when the last message is a tool call (or empty) means the settle loop
    keeps waiting until my real summary lands — which also defeats the flush
    race (we never speak until the final prose is on disk).
    """
    msgs = _assistant_messages(transcript_path)
    # Ignore trailing empty messages (defensive), find the last with content.
    for text, has_tool in reversed(msgs):
        if not text.strip() and not has_tool:
            continue  # skip blank
        # First non-blank from the end: speak only if it's prose, no tool.
        return text if (text.strip() and not has_tool) else ""
    return ""


def send_to_phone(text: str):
    """Synthesize in Brooke's voice and deliver as a Telegram voice note."""
    try:
        from say_to_phone import synth_mp3, mp3_to_opus_ogg, send_voice, _creds

        token, chat = _creds()
        if not token or not chat:
            return
        ogg = mp3_to_opus_ogg(synth_mp3(text))
        try:
            send_voice(token, chat, ogg)
        finally:
            try:
                import os
                os.unlink(ogg)
            except OSError:
                pass
    except Exception:  # noqa: BLE001 — never surface to the session
        pass


def in_scope(payload) -> bool:
    """Decide whether this session's cwd should be narrated.

    Flag-file lines:
      - empty file            => ALL sessions (universal)
      - "<substring>"         => allowlist: only cwds containing it
      - "!<substring>"        => substring-exclude: skip cwds containing it
      - "=<exact path>"       => exact-exclude: skip only this exact cwd
    Excludes always win. The exact form exists because the COS runs from the
    HOME dir (/Users/kylekillen), which is a prefix of every project path — a
    substring exclude there would silence everything, so it needs "=".
    """
    try:
        lines = [ln.strip() for ln in FLAG.read_text().splitlines() if ln.strip()]
    except OSError:
        lines = []
    cwd = payload.get("cwd") or ""
    exact_excludes = [s[1:] for s in lines if s.startswith("=")]
    sub_excludes = [s[1:] for s in lines if s.startswith("!")]
    includes = [s for s in lines if not s.startswith(("=", "!"))]
    if cwd in exact_excludes:
        return False
    if any(e and e in cwd for e in sub_excludes):
        return False
    if not includes:
        return True  # universal (minus excludes)
    return any(i in cwd for i in includes)


def main():
    # Self-mute: non-interactive jobs (e.g. the podcast pipeline) export
    # CODE_VOICE_MUTE=1 so their turns are never narrated, even in-scope.
    if os.getenv("CODE_VOICE_MUTE"):
        return
    # Opt-in gate — silent no-op when the flag is absent (cheapest path).
    if not FLAG.exists():
        return
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return
    if not in_scope(payload):
        return
    transcript = payload.get("transcript_path")
    if not transcript:
        return
    # The COS is the one always-excluded session — identity-based, so it holds
    # no matter what directory the COS happens to be working in.
    if is_cos_session(transcript):
        return
    # Settle wait: the final message may still be flushing when Stop fires.
    # Poll until the pure-prose text stops changing (max ~4s).
    text, prev = "", None
    deadline = time.time() + 4.0
    while time.time() < deadline:
        text = final_prose_text(transcript)
        if text and text == prev:
            break
        prev = text
        time.sleep(0.4)
    if not text.strip():
        _log("no prose text found; nothing sent")
        return
    # Speak my WHOLE closing message, verbatim — no LLM, no clipping.
    # final_prose_text() already isolates the closing summary (the final
    # pure-prose assistant message). Earlier we spoke only its last paragraph
    # to keep notes short, but that dropped the substance above it (numbers,
    # timelines, the actual conclusion) and caused signal loss. This is the
    # substitute for the claude.ai read-aloud button, which reads everything.
    spoken = strip_markdown(text)
    if not spoken.strip():
        return
    paras = spoken.count("\n\n") + 1
    _log(
        f"speaking {len(spoken)} chars, {paras} paragraph(s) | "
        f"START {spoken[:90]!r} | END {spoken[-90:]!r}"
    )
    # Detach so synth + send latency never delays the session returning.
    t = threading.Thread(target=send_to_phone, args=(spoken,), daemon=True)
    t.start()
    t.join(timeout=15)


if __name__ == "__main__":
    main()
