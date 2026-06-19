#!/usr/bin/env python3
"""or_writer.py — OpenRouter (Kimi) FALLBACK writer for Killen Time episodes.

This is a *fallback only*. The default daily path writes every episode with
Claude (flat-rate Max pool, $0 marginal). OpenRouter is pay-per-token, so we
reach for it ONLY when a Claude write pass has actually FAILED (e.g. the shared
pool hit its cap) and we still want the episode to ship. See generate-episode.sh
(Step 2a / Step 2b) for where this is invoked.

Unlike the Claude write passes — which are agentic `claude -p` runs that read the
source files themselves — Kimi via or_complete.py is a single chat completion
with no tool use. So this script does the file-gathering itself: it reads the
same inputs the Claude prompt would have read (topic brief, transcripts,
articles, recent scripts + covered-*.json for dedup, build-pitches), inlines them
into one prompt that preserves the CLAUDE.md format / word targets / dedup
discipline / build-pitch fold-in, calls Kimi, then writes (pass 1) or appends
(pass 2) the BASIL/BROOKE script identically. On pass 2 it also saves covered
stories so multi-episode dedup keeps working.

Usage:
  python3 or_writer.py --pass 1 --script scripts/killen-time-2026-06-19.txt \
      --greeting "This is a morning episode ..." [--model moonshotai/kimi-k2-0905]
  python3 or_writer.py --pass 2 --script scripts/killen-time-2026-06-19.txt --greeting "..."

Exit 0 on a written/appended script; non-zero + stderr message on failure (so
the caller can decide what to do — there's no further fallback below this).
"""
import argparse
import json
import re
import sys
from pathlib import Path

import or_complete

ROOT = Path(__file__).resolve().parent
TMP = ROOT / ".tmp"
SCRIPTS_DIR = ROOT / "scripts"

# Empty = use whatever OFFLOAD_MODEL is configured in
# ~/.config/personal-os/offload.env (currently FREE Gemini Flash). Keeps the
# fallback writer provider-agnostic — the offload provider is a config choice,
# not hardcoded. Pass --model only to override for a one-off test.
DEFAULT_MODEL = ""

# Per-source truncation caps (chars) so the prompt stays bounded on a pay-per-token
# model. The topic brief and build-pitch summary are the spine and go in whole.
MAX_TRANSCRIPTS = 3
TRANSCRIPT_CAP = 8000
MAX_ARTICLES = 6
ARTICLE_CAP = 6000
MAX_RECENT_SCRIPTS = 3
RECENT_SCRIPT_CAP = 4000
# Dedup only meaningfully cares about recent coverage (CLAUDE.md: the last ~48h
# of scripts plus covered-*.json). There are 100+ historical covered files; feeding
# them all blows the request, so take only the most recent ones, each capped.
MAX_COVERED = 7
COVERED_CAP = 6000

# Trailer markers Kimi appends on pass 2 so we can recover the covered-stories
# dict for multi-episode dedup, then strip it from the script body.
COVERED_BEGIN = "<<<COVERED_JSON>>>"
COVERED_END = "<<<END_COVERED_JSON>>>"


def _read(path: Path, cap: int | None = None) -> str:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return ""
    if cap and len(text) > cap:
        return text[:cap] + f"\n[... truncated, {len(text) - cap} more chars ...]"
    return text


def _gather_sources() -> dict:
    """Read the same inputs a Claude write pass would read, with caps."""
    out = {}
    out["claude_md"] = _read(ROOT / "CLAUDE.md")
    out["topic_brief"] = _read(TMP / "topic-brief.txt")

    pitch = TMP / "build-pitches.md"
    out["build_pitches"] = _read(pitch) if pitch.exists() else ""

    transcripts = sorted((TMP / "transcripts").glob("*.txt")) if (TMP / "transcripts").exists() else []
    out["transcripts"] = [
        (t.name, _read(t, TRANSCRIPT_CAP)) for t in transcripts[:MAX_TRANSCRIPTS]
    ]

    articles = sorted((TMP / "articles").glob("*.txt")) if (TMP / "articles").exists() else []
    out["articles"] = [
        (a.name, _read(a, ARTICLE_CAP)) for a in articles[:MAX_ARTICLES]
    ]

    # Dedup context: recent scripts (truncated) + ALL covered-*.json (compact + the
    # highest-signal "already said on air" record).
    recent = sorted(SCRIPTS_DIR.glob("killen-time-*.txt"))[-MAX_RECENT_SCRIPTS:]
    out["recent_scripts"] = [(s.name, _read(s, RECENT_SCRIPT_CAP)) for s in recent]
    covered = sorted(SCRIPTS_DIR.glob(".covered-*.json"))[-MAX_COVERED:]
    out["covered"] = [(c.name, _read(c, COVERED_CAP)) for c in covered]
    return out


def _sources_block(src: dict, include_recent_scripts: bool) -> str:
    parts = []
    parts.append("=== TODAY'S RANKED TOPIC BRIEF (.tmp/topic-brief.txt) ===\n" + src["topic_brief"])
    if src["build_pitches"]:
        parts.append("=== BUILD-PITCH SUMMARY (.tmp/build-pitches.md) ===\n" + src["build_pitches"])
    for name, body in src["transcripts"]:
        parts.append(f"=== PODCAST TRANSCRIPT ({name}) ===\n{body}")
    for name, body in src["articles"]:
        parts.append(f"=== SUBSTACK ARTICLE ({name}) ===\n{body}")
    parts.append(
        "=== DEDUP — STORIES/FACTS ALREADY COVERED IN PREVIOUS EPISODES (do NOT repeat) ===\n"
        + "\n\n".join(f"-- {name} --\n{body}" for name, body in src["covered"])
    )
    if include_recent_scripts and src["recent_scripts"]:
        parts.append(
            "=== RECENT EPISODE SCRIPTS (truncated; for dedup) ===\n"
            + "\n\n".join(f"-- {name} --\n{body}" for name, body in src["recent_scripts"])
        )
    return "\n\n".join(parts)


SYSTEM = (
    "You are a scriptwriter for Killen Time, a personalized daily news show with "
    "two AI hosts, BASIL (anchor, confident, leads) and BROOKE (commentator, "
    "analytical). You write the spoken script ONLY — no stage directions, no "
    "markdown, no commentary about the task. Output is fed directly to a "
    "text-to-speech engine.\n\n"
    "FORMAT RULES (strict — TTS depends on them):\n"
    "- Every spoken block begins with a speaker tag on its own: [BASIL] or [BROOKE].\n"
    "- Use [TRANSITION] on its own line between beats/segments. NEVER write '---'.\n"
    "- ALTERNATE speakers. Never two consecutive blocks from the same speaker.\n"
    "- No headings, no bullet points, no asterisks, no section labels in the body.\n"
    "- Conversational, substantive, specific. Quote real details/arguments from the "
    "provided sources. Engage at a practitioner/insider level, not summary filler.\n"
    "- Do not invent sources, quotes, or a Build-Pitch. Use only what is provided."
)


def _pass1_prompt(src: dict, greeting: str) -> str:
    return f"""{_sources_block(src, include_recent_scripts=True)}

=== EDITORIAL GUIDE (CLAUDE.md excerpt — follow voice/format) ===
{src['claude_md']}

=== YOUR TASK: WRITE THE FIRST HALF ===
TIME OF DAY: {greeting}

Write the INTRO and the FIRST HALF of today's episode: AI/TECH plus the featured
AGENTS & BUILDING WITH AI beat. You are writing ONLY the first half — another pass
writes the second half (sports, entertainment, economics, outro). Do NOT write an
outro or sign-off; END your output with a line containing exactly [TRANSITION].

Include:
- Show intro: cold open on the single biggest story, then the show name and date.
  Greeting must match the time of day above.
- AI & Technology (1-2 segments, ~2500-3500 words): lead with the highest-signal AI
  discussion in the sources (the AI Daily Brief / Moonshots framing when present),
  using the news headlines as context around it. Skip generic news-summary filler.
- Agents & Building With AI (2-3 segments, ~3500-4500 words) — THE FEATURED BEAT:
  how people actually run agents — harness/CLAUDE.md/context engineering, subagents
  and multi-agent orchestration, evals, MCP/tooling, dev-loop optimization. Frame
  every item as "what can WE learn for our own multi-agent setup." Be specific.
- BUILD PITCH OF THE DAY: ONLY if a build-pitch summary is provided above AND its
  first line is NOT "NO_VERIFIED_PITCH", give the top pitch its own ~400-700 word
  exchange (what it is, who's doing it, evidence it's real, how it'd upgrade Kyle's
  setup) and have a host note it's logged in the build-pitches folder to greenlight.
  If there is no pitch or it says NO_VERIFIED_PITCH, skip it — do NOT invent one.

Honor the dedup section: do not repeat any story, argument, quote, or fact already
covered in previous episodes. Target 7000-9000 words for this half. Begin the output
immediately with the first [BASIL] block — no preamble."""


def _pass2_prompt(src: dict, greeting: str, existing_script: str) -> str:
    return f"""{_sources_block(src, include_recent_scripts=False)}

=== THE FIRST HALF OF TODAY'S EPISODE (already written — do NOT repeat any of it) ===
{existing_script}

=== EDITORIAL GUIDE (CLAUDE.md excerpt — follow voice/format) ===
{src['claude_md']}

=== YOUR TASK: WRITE THE SECOND HALF ===
TIME OF DAY: {greeting}

Write the SECOND HALF that CONTINUES the script above. Do NOT rewrite or duplicate
anything from the first half. Your output will be appended directly after it, so
START with a [TRANSITION] line and then the first new [BASIL] or [BROOKE] block.

Cover, in order:
- Sports (2-3 segments, ~2500-3500 words) — LEAD WITH NFL FOOTBALL (Ringer Fantasy
  Football Show, Fantasy Footballers, Bill Barnwell — rankings, values/busts, roster
  strategy, league trends, with specific analyst quotes from the transcripts). Then
  NBA only for genuinely notable storylines (Finals, draft, major trades), tighter.
- Entertainment & Film/TV (1-2 segments, ~2000-3000 words): industry news, deals,
  box office, engaged at a screenwriter/producer level.
- Economics/Culture (1-2 segments, ~1500-2500 words): best pieces from the
  rationalist/policy/economics blogosphere in the sources.
- Prediction Markets quick-hit (OPTIONAL, ONE short exchange, ~300-600 words): only
  if there is genuinely notable movement today; otherwise SKIP entirely. No padding.
- Quick Hits: 2-3 shorter items that didn't warrant full segments.
- Outro: brief recap of the most interesting thread, then a short sign-off matching
  the time of day.

Honor the dedup section AND the first half above: never repeat a story/fact/quote.
Target 7000-9000 words for this half. Use [BASIL]/[BROOKE]/[TRANSITION] only and
alternate speakers.

AFTER the outro and a final blank line, append a machine-readable trailer recording
EVERY story covered across the WHOLE episode (both halves) so future episodes can
dedup. Use exactly this format and nothing after it:
{COVERED_BEGIN}
{{"stories": ["kebab-case-slug-per-story"], "segments": {{"kebab-case-slug": "one-sentence summary of the specific facts/quotes/arguments used on air"}}, "podcast_guids": []}}
{COVERED_END}"""


_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*\n(.*?)\n```\s*$", re.DOTALL)


def _clean_script(text: str) -> str:
    """Strip code fences / chatty preamble so only the spoken script remains."""
    text = text.strip()
    m = _FENCE_RE.match(text)
    if m:
        text = m.group(1).strip()
    # Drop anything before the first speaker tag (chatty "Here's the script:" intros).
    idx = text.find("[BASIL]")
    idx2 = text.find("[BROOKE]")
    idx_tr = text.find("[TRANSITION]")
    candidates = [i for i in (idx, idx2, idx_tr) if i != -1]
    if candidates:
        first = min(candidates)
        if first > 0:
            text = text[first:]
    return text.strip()


def _extract_covered(text: str):
    """Pull and strip the covered-stories trailer (pass 2). Returns (body, dict|None)."""
    start = text.find(COVERED_BEGIN)
    if start == -1:
        return text, None
    end = text.find(COVERED_END, start)
    raw = text[start + len(COVERED_BEGIN): end if end != -1 else len(text)].strip()
    body = text[:start].rstrip()
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = None
    except json.JSONDecodeError:
        data = None
    return body, data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pass", dest="pass_no", type=int, choices=[1, 2], required=True)
    ap.add_argument("--script", required=True, help="path to the episode script file")
    ap.add_argument("--greeting", default="", help="time-of-day greeting hint")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--max-tokens", type=int, default=16000)
    args = ap.parse_args()

    script_path = Path(args.script)
    if not script_path.is_absolute():
        script_path = ROOT / script_path

    src = _gather_sources()
    if not src["topic_brief"]:
        sys.stderr.write("or_writer: no .tmp/topic-brief.txt — cannot write episode\n")
        sys.exit(1)

    if args.pass_no == 1:
        prompt = _pass1_prompt(src, args.greeting)
    else:
        if not script_path.exists():
            sys.stderr.write(f"or_writer: pass 2 needs an existing {script_path} (pass 1 output)\n")
            sys.exit(1)
        existing = script_path.read_text(errors="replace")
        prompt = _pass2_prompt(src, args.greeting, existing)

    sys.stderr.write(
        f"or_writer: FALLBACK pass {args.pass_no} via OpenRouter model={args.model} "
        f"(prompt ~{len(prompt)} chars)\n"
    )
    # Descending max-tokens ladder. OpenRouter reserves the FULL max_tokens cost
    # upfront, so on a low/zero-credit account a large request 402s ("Payment
    # Required") even though smaller ones succeed. We'd rather ship a shorter
    # episode than none, so on failure we retry with a smaller output budget. On a
    # funded account the first (largest) request succeeds and this is a single call.
    ladder = sorted({args.max_tokens, 8000, 4000}, reverse=True)
    ladder = [t for t in ladder if t <= args.max_tokens]
    completion = None
    last_err = None
    for mt in ladder:
        try:
            completion = or_complete.complete(prompt, args.model, system=SYSTEM, max_tokens=mt)
            if mt < args.max_tokens:
                sys.stderr.write(
                    f"or_writer: succeeded at reduced max_tokens={mt} (requested "
                    f"{args.max_tokens}); episode half will be shorter. Add OpenRouter "
                    f"credit to lift this cap.\n"
                )
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
            sys.stderr.write(f"or_writer: completion failed at max_tokens={mt}: {e}\n")
    if completion is None:
        sys.stderr.write(f"or_writer: OpenRouter completion failed at all budgets: {last_err}\n")
        sys.exit(1)

    covered = None
    if args.pass_no == 2:
        completion, covered = _extract_covered(completion)
    body = _clean_script(completion)
    if len(body.split()) < 500:
        sys.stderr.write(
            f"or_writer: completion too short ({len(body.split())} words) — treating as failure\n"
        )
        sys.exit(1)

    if args.pass_no == 1:
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(body + "\n")
    else:
        # Append to the existing first half. The first half ends with a
        # [TRANSITION] and the model is told to start its half with one too, so
        # deterministically collapse the join to a single [TRANSITION] — that
        # back-to-back-transition is one of the recurring two-pass defects.
        existing_tail = script_path.read_text(errors="replace").rstrip()
        ends_with_transition = existing_tail.endswith("[TRANSITION]")
        lines = body.split("\n")
        while lines and lines[0].strip() == "[TRANSITION]":
            lines.pop(0)
        body = "\n".join(lines).lstrip()
        join = "\n" if ends_with_transition else "\n[TRANSITION]\n"
        with open(script_path, "a") as f:
            f.write(join + body + "\n")
        # Save covered stories for multi-episode dedup (best effort).
        try:
            from ingest import save_covered_stories
            if covered and covered.get("stories"):
                save_covered_stories(
                    covered.get("stories", []),
                    covered.get("segments") or {},
                    podcast_guids=covered.get("podcast_guids") or [],
                )
                sys.stderr.write(
                    f"or_writer: saved {len(covered['stories'])} covered stories\n"
                )
            else:
                sys.stderr.write(
                    "or_writer: no parseable covered-stories trailer; relying on "
                    "source archiving (Step 5 safety net) for dedup\n"
                )
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"or_writer: save_covered_stories failed (non-fatal): {e}\n")

    words = len(body.split())
    sys.stderr.write(f"or_writer: pass {args.pass_no} wrote {words} words to {script_path}\n")


if __name__ == "__main__":
    main()
