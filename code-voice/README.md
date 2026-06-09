# Code Voice — hear your Claude Code sessions on your phone

When any Claude Code session finishes a turn, this speaks the session's
closing summary to Kyle's phone as a **Telegram voice note** in the Killen
Time "Brooke" voice (local Kokoro). It's the substitute for the claude.ai
mobile read-aloud button (which is server-side ElevenLabs with no API).

**Goal, in Kyle's words:** "every single code session produces voice-memo
summaries, with one exception — the COS." Kyle interacts by typing/dictating
from his phone (Remote Control, etc.); this is the voice coming *back*. He
does not think in repos/cwds, so nothing here requires him to.

## How it works (voice-OUT only)

```
A Claude Code session finishes a turn
  └─ Stop hook  (~/.claude/hooks/voice-stop.sh → code-voice/stop_hook.py)
       ├─ CODE_VOICE_MUTE=1 set?            → skip   (podcast pipeline self-mutes)
       ├─ flag /tmp/claude-voice-enabled?   → on/off + optional scoping
       ├─ is this the COS? (identity)       → skip   (the one exclusion)
       ├─ wait for my FINAL prose message to settle on disk
       ├─ take its last paragraph (my closing summary), strip markdown
       └─ say_to_phone.py:
            ├─ POST text → local Kokoro  /v1/audio/speech (:8765) → mp3
            ├─ ffmpeg mp3 → opus/ogg
            └─ Telegram sendVoice → Kyle's phone   (his EXISTING bot, outbound only)
```

No LLM summarizer, no STT, no ccgram, no new bot. Just: extract my closing
paragraph → Kokoro → Telegram voice note.

### Why these specific design choices (hard-won — don't undo without reading)

- **Speak my last *prose* message, not "last text".** The harness writes the
  preamble line I type right before a tool call as its OWN text-only message,
  with tool calls in separate later messages. So "last text block" is often a
  preamble, not my summary. `final_prose_text()` only returns text when the
  transcript's LAST assistant message is pure prose (no tool call) — which is
  my closing summary by construction. A settle-loop waits for it to land
  (defeats a flush race where Stop fires before the final message is on disk).
- **The COS is excluded by IDENTITY, not cwd.** The COS roams directories as
  it works (cwd cycles through home, `.observer/wiki`, project dirs…), so no
  cwd rule can pin it. `is_cos_session()` returns True iff the transcript has
  an `attachment`-type entry containing "You are the COS"/"You are the Chief
  of Staff" (its loaded CLAUDE.md). This is false-positive-proof: a session
  that merely *discusses* the COS has those strings only in message text,
  never in an attachment.
- **Verbatim, not summarized.** An earlier Ollama summarizer dropped critical
  detail (numbers, questions). Kyle's call: speak the closing summary I
  already write, verbatim. The summarizer is OUT of this path.
- **Reuses Kyle's existing Telegram bot.** Sending a voice note to your own
  chat needs no BotFather/group setup — only the inbound (ccgram) path would.

## Components

| file | role |
|---|---|
| `stop_hook.py` | Stop hook: gate → identity-skip COS → extract closing summary → send. Stdlib only. |
| `say_to_phone.py` | text → Kokoro mp3 → opus → Telegram voice note. Creds from env or `~/.claude/settings.json`. |
| `server.py` | resident warm Kokoro server (`com.codevoice.server`, :8765). Serves OpenAI-compatible `/v1/audio/speech`. |
| `text_clean.py` | markdown → spoken prose (shared). |
| `restore-flag.sh` + `com.codevoice.flag.plist` | login agent: restores the flag from the persistent scope at boot (/tmp clears on reboot). |
| `~/.claude/hooks/voice-stop.sh` | wrapper registered in `~/.claude/settings.json` `hooks.Stop`. |

Runtime config (not in repo): `~/.config/codevoice/voice-scope` (persistent
flag contents), and the Telegram creds come from the `env` block of
`~/.claude/settings.json`.

## Control — the flag `/tmp/claude-voice-enabled`

Read fresh every turn (no restart ever). The persistent copy is
`~/.config/codevoice/voice-scope`; a login agent restores it to /tmp at boot.

```
(empty file, present)  → ON, UNIVERSAL — every session narrates   ← current setting
rm the file            → OFF everywhere
"<substring>"          → allowlist: only cwds containing it narrate
"!<substring>"         → exclude cwds containing it
"=<exact path>"        → exclude exactly this cwd
```

Current state: **empty (universal)**. The COS is excluded in code (identity),
NOT via the flag. The cwd machinery is kept for ad-hoc scoping but unused.

```bash
curl -s 127.0.0.1:8765/health           # Kokoro server warm?
tail -f code-voice/phone_hook.log        # what the hook spoke / skipped
launchctl list | grep codevoice          # server + flag-restore agents
```

## Muting non-interactive jobs

The 5:30 AM podcast pipeline exports `CODE_VOICE_MUTE=1` (one line in
`generate-episode.sh`); the hook hard-skips any turn with that env set. Any
other automated job can self-mute the same way.

## Dormant (kept, not used)

Built during exploration, then dropped when Kyle clarified he only needs
voice-OUT: `stt_server.py` (local Whisper, `com.codevoice.stt` — unloaded),
ccgram (`uv tool install ccgram`, patched for local Kokoro/Whisper — for a
future two-way voice-IN path), and the Ollama summarizer. Research:
`~/.observer/wiki/research/phone-voice-claude-code-2026-06-08.md`.
The full chronology is in `../STATUS.md` under "Code Voice".
