#!/usr/bin/env python3
"""bin/test-single-pass.py — New Hire test harness (ALL-HANDS Round 3, kt-podcast).

Question: is a SINGLE writer pass of ~3,500 spoken words better than today's
TWO-pass ~6,000-9,600-word episode, on the SAME day's sources?

  A (control) = the aired script for --date, written by the production two-pass
                pipeline. Never regenerated.
  B (variant) = ONE writer pass over the same topic brief / build pitch /
                transcripts / articles, targeted at 3,000-4,000 SPOKEN words,
                carrying the same beats (including the Build Pitch of the Day)
                and writing its own outro.

Stages (--stage, default `all`):
  manifest  sha256 + size of every source file both variants read
  write     variant B, one pass, on a non-Anthropic writer lane
  qc        the production QC (.claude/commands/qc-episode.md) on A and on B
  scan      the seam/leak scan on A and on B
  judge     a blind A/B judging pass on a free model that is not the writer
  report    test-runs/<date>-single-pass.md + -metrics.json

HARD LIMITS enforced by this file: it never invokes voice.py / mixer.py /
artwork.py / publish.py / publish_private.py / render_report.py, never touches
Kokoro :8765, and writes only under test-runs/. It reads the live repo for
sources and runs QC there (read-only) so the dedup ledger is the real one.

Usage:
  python3 bin/test-single-pass.py --date 2026-09-28
  python3 bin/test-single-pass.py --date 2026-09-28 --stage scan
"""
import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LIVE = Path(os.environ.get("KT_LIVE_REPO", str(Path.home() / "brainrot-radio")))
TEST_DIR = REPO / "test-runs"
OBSERVER_PY = Path.home() / "observer-system" / ".venv" / "bin" / "python"
OLLAMA = os.environ.get("KT_OLLAMA_URL", "http://127.0.0.1:11434")

# Writer lane: local MLX Glimmer. Chosen because (a) it is NOT an Anthropic
# model, (b) it costs $0, (c) kt-podcast's own Round 3 answer names Glimmer as
# the podcast's fallback writer, and (d) it is already resident in ollama, so
# this test loads nothing new into RAM. Judge lane is a different free model.
WRITER = os.environ.get("KT_TEST_WRITER", "muse-glimmer:30b-mlx")
JUDGE = os.environ.get("KT_TEST_JUDGE", "muse-spark-1.3-free")
B_MIN_WORDS, B_MAX_WORDS = 3000, 4000
# The Sonnet rerun's length target. B-long isolates pass count at the production
# spec; B-short tests the original length hypothesis. Each is scored separately.
BAND = os.environ.get("KT_TEST_BAND", "short")          # "long" | "short"
# Where the writer is pointed. The 09-28 rerun reads a FROZEN bundle, not the
# live .tmp/ — see test-runs/2026-09-28-sonnet-onepass-criteria.md.
BUNDLE = os.environ.get("KT_TEST_BUNDLE", "")
# Suffix on every artifact, so a two-variant run never overwrites the other.
SUFFIX = os.environ.get("KT_TEST_SUFFIX", "")

# ---------------------------------------------------------------- helpers ---


def spoken_words(text: str) -> int:
    """Words that actually go through TTS: speaker tags removed."""
    return len(re.sub(r"\[(BASIL|BROOKE|TRANSITION)\]", " ", text).split())


def sha(path: Path) -> dict:
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()[:16]}


def _load_modules():
    """The production source-gatherer and prompt format, reused not rebuilt."""
    sys.path.insert(0, str(LIVE))
    os.chdir(LIVE)  # or_writer resolves .tmp/ and scripts/ relative to its own ROOT
    import or_writer  # noqa: E402
    return or_writer


# ----------------------------------------------------------------- write ---


def single_pass_prompt(or_writer, src, greeting: str) -> str:
    """The production pass-1 prompt MINUS the expansion step, plus the beats
    pass 2 would have covered, compressed into one 3,000-4,000-word episode.
    Same source bundle, same format rules, same build-pitch discipline."""
    return f"""{or_writer._sources_block(src, include_recent_scripts=True)}

=== EDITORIAL GUIDE (CLAUDE.md — voice, format, source discipline) ===
{src['claude_md']}

=== YOUR TASK: WRITE THE WHOLE EPISODE IN ONE PASS ===
TIME OF DAY: {greeting}

This is a single-pass episode. There is no second half and no separate writer.
You write the complete show start to finish, including the outro.

Length: 3,000-4,000 spoken words TOTAL. That is the whole episode, not a target
per segment. Depth beats coverage: fewer stories, each properly reported, beats
a sweep of everything in the brief. Roughly:

  - COLD OPEN + show name and date                          ~200 words
  - AI & TECH                                                ~700 words
  - AGENTS & BUILDING WITH AI — the featured beat, the most
    airtime on the show; concrete stealable practices
    quoted from the sources, framed as what we can learn
    for our own multi-agent setup                         ~1,000-1,200 words
  - BUILD PITCH OF THE DAY — its own exchange inside the
    Agents & Building block, only if the build-pitch file
    above is not NO_VERIFIED_PITCH                         ~400-500 words
  - SPORTS, NFL-LED (basketball only if genuinely notable)  ~400 words
  - ENTERTAINMENT at screenwriter/producer level            ~300 words
  - ECONOMICS / CULTURE                                     ~300 words
  - 2-3 QUICK HITS                                          ~150 words
  - OUTRO: recap the most interesting thread, short sign-off  ~100 words

The Build Pitch of the Day, if you do one: what the technique is, who is doing it
(name the source), the evidence it is real, and in GENERAL terms why it could
matter to someone running agents. Keep the listener's private system out of the
audio — no repo names, no role names, no launchd jobs, no config keys, no
internal counts from the pitch file. Then have a host say plainly that it is
logged in the build-pitches folder so he can point an agent at it and greenlight
the build. If the pitch file says NO_VERIFIED_PITCH, skip it — never invent one.

OUTPUT RULES (strict — this goes straight to a text-to-speech engine):
- Every spoken block opens with [BASIL] or [BROOKE] on its own. Alternate; never
  two same-speaker blocks in a row. [TRANSITION] alone between beats, never '---'.
- No headings, bullets, asterisks or stage directions in the body.
- Write the outro yourself. Do NOT end on a [TRANSITION] tag.
- Never write "this half", "the first half", "the second half", "pass one" or
  "pass two" — there are no halves in a single-pass episode.
- Conversational and opinionated but grounded; at least one real direct quote per
  segment. Assume an expert listener. Nothing about the listener's own machines,
  repos, agents or internal setup.
- Do not invent sources, quotes or callbacks. If it is not in the material above,
  it does not go on air.

Write ONLY the script text. No preamble, no markdown fences, no commentary.
"""


# ── Sonnet writer path (KT_TEST_WRITER=sonnet) ─────────────────────────────
#
# The first test was not a fair fight: a 32K-context local model against Sonnet
# with full context. This path holds the WRITER MODEL fixed at Sonnet and varies
# only the pass count, so the result is about one pass vs two rather than about
# a free local model.
#
# It invokes the writer exactly as generate-episode.sh's run_claude_step does —
# the same `claude --dangerously-skip-permissions --model sonnet -p` call, the
# same working directory, the same tools, the same uncompacted source bundle and
# context files, the same 1M context. The ONLY change to the pass-1 prompt is
# that it writes the WHOLE episode in one pass: no "first half", no second pass,
# no expansion/top-up step. Nothing else about the writer's job changes.
#
# Tokens come from the CLI's own JSON `usage` (--output-format json), which
# reports input / cache_creation / cache_read / output separately. That is a
# MEASUREMENT, not an estimate — the same fields the control's real usage is
# summed from, so the two are directly comparable.

SONNET_MODEL = os.environ.get("KT_TEST_SONNET_MODEL", "sonnet")
CLAUDE_BIN = os.environ.get("KT_TEST_CLAUDE", "/Users/kylekillen/.local/bin/claude")

# Length bands, pre-registered in test-runs/2026-09-28-sonnet-onepass-criteria.md.
# B-long isolates pass count at the production spec in .claude/context/editorial-voice.md
# (~14,000-18,000 words); the criterion allows 15% of the spec. B-short tests the
# original 3,000-4,000-word hypothesis.
LONG_SPEC = (14000, 18000)
LONG_TOLERANCE = 0.15


def sonnet_one_pass_prompt(band: str) -> str:
    """Pass 1's prompt with ONE change: write the whole episode, not the first half.

    Everything else — the tools, the working directory, the source bundle, the
    context files, the build-pitch discipline, the evidence rules, the dedup
    context, the speaker-tag format — is pass 1's own prompt, reused verbatim
    where it applies. The second half's beats (sports, entertainment, economics,
    the quick-hits run) are folded in, because a one-pass episode that skipped
    them would be testing a different show.
    """
    if band == "long":
        target = ("LENGTH: ~14,000-18,000 spoken words TOTAL for the whole episode. "
                  "That is the production spec in .claude/context/editorial-voice.md "
                  "(a ~60 minute show). Cover everything the brief holds; at minimum "
                  "hit highlights of every story. Write the complete episode start to "
                  "finish in this one pass — there is no second pass coming, so budget "
                  "the whole show across the sections below and do not stop short.")
        beats = """  - COLD OPEN + show name and date                          ~300 words
  - AI & TECH (1-2 segments, anchored on the podcast transcripts) ~3,000 words
  - AGENTS & BUILDING WITH AI — the featured beat, the most airtime
    on the show; concrete stealable practices quoted from the sources,
    framed as what we can learn for our own multi-agent setup ~5,000 words
  - BUILD PITCH OF THE DAY — its own exchange inside the Agents &
    Building block, only if the build-pitch file above is not
    NO_VERIFIED_PITCH                                             ~500-700 words
  - SPORTS, NFL-LED                                              ~1,500 words
  - ENTERTAINMENT at screenwriter/producer level                ~1,200 words
  - ECONOMICS / CULTURE                                         ~1,500 words
  - 2-3 QUICK HITS                                             ~300 words
  - OUTRO: recap the most interesting thread, short sign-off    ~200 words"""
    else:
        target = ("LENGTH: 3,000-4,000 spoken words TOTAL for the whole episode. That is "
                  "the whole episode, not a target per segment. Depth beats coverage: "
                  "fewer stories, each properly reported, beats a sweep of everything in "
                  "the brief. Write the complete episode start to finish in this one "
                  "pass — there is no second pass coming.")
        beats = """  - COLD OPEN + show name and date                          ~200 words
  - AI & TECH                                                  ~700 words
  - AGENTS & BUILDING WITH AI — the featured beat, the most
    airtime on the show; concrete stealable practices
    quoted from the sources, framed as what we can learn
    for our own multi-agent setup                         ~1,000-1,200 words
  - BUILD PITCH OF THE DAY — its own exchange inside the
    Agents & Building block, only if the build-pitch file
    above is not NO_VERIFIED_PITCH                           ~400-500 words
  - SPORTS, NFL-LED (basketball only if genuinely notable)     ~400 words
  - ENTERTAINMENT at screenwriter/producer level              ~300 words
  - ECONOMICS / CULTURE                                       ~300 words
  - 2-3 QUICK HITS                                            ~150 words
  - OUTRO: recap the most interesting thread, short sign-off ~100 words"""
    return f"""You are producing a complete Killen Time episode in a SINGLE PASS. Your working directory is {{CWD}}.

Read CLAUDE.md for full editorial guidelines, voice format, and content direction.

TIME OF DAY: This is a morning episode.

YOUR JOB: Write the WHOLE episode — start to finish, including the outro — and write it to: {{SCRIPT}}

This is a one-pass episode. There is no second pass, no other writer, and no
later expansion or top-up step. You cover every section of the show below in this
single response.

{target}

Steps:
1. Read .tmp/topic-brief.txt for today's ranked stories
   - The X PULSE section at its end shows what is trending on X and leads from accounts Kyle follows. Use it to judge which stories are today's MAJOR ones and dig deeper on those; follow its attribution rules.
2. Read the podcast transcripts in .tmp/transcripts/ — PRIORITIZE the two anchor AI shows when fresh episodes exist: the AI Daily Brief (Nathaniel Whittemore) and Moonshots (Peter Diamandis). After those, pick what's most relevant to how people build with / run AI agents.
3. Read the Substack full articles in .tmp/articles/ — focus on AI/tech and agent-building/practitioner articles.
4. Read .tmp/build-pitches.md if it exists — this is the verified output of the Claude Lab Build-Pitch Reporter.
5. Read ALL scripts/.covered-*.json files for dedup.
6. Read recent episode scripts in scripts/ for dedup.
7. Write the complete episode to {{SCRIPT}}, roughly:
{beats}
   - Include specific quotes from podcast transcripts and Substack articles
   - Alternate speakers — never two consecutive same-speaker blocks
   - Use BASIL/BROOKE/TRANSITION format (speaker tags in square brackets)

BUILD PITCH OF THE DAY: If .tmp/build-pitches.md exists AND its first line is not "NO_VERIFIED_PITCH", give the top verified pitch its own dedicated exchange inside the Agents & Building block: what the technique is, who's doing it (name the source), the evidence it's real, and, in GENERAL terms, why it could matter to someone running agents. Keep the listener's private system out of the audio: do NOT name Kyle's repos, roles, launchd jobs, launch-site counts, config keys, or any other internal statistic from .tmp/build-pitches.md. Then have a host say plainly that it's logged in the build-pitches folder so Kyle can point an agent at it and greenlight the build if he likes it. If the file is missing or says NO_VERIFIED_PITCH, skip this — do NOT invent a pitch.

Write the OUTRO yourself. Do NOT end on a [TRANSITION] tag.

IMPORTANT: Do NOT save covered stories or archive sources yet.

STOP after writing the script file. Do NOT render, mix, or publish.
Write ONLY the script file. Do not modify any other file in the repository, and
do not read or write anything under scripts/killen-time-{{TODAY}}.txt.

Begin by reading CLAUDE.md, then .tmp/topic-brief.txt, then the previous episode scripts.
"""


def stage_write_sonnet(date, metrics):
    """One Sonnet pass, invoked exactly as generate-episode.sh invokes pass 1."""
    cwd = Path(BUNDLE) if BUNDLE else LIVE
    out = TEST_DIR / f"{date}-sonnet-{BAND}.txt"
    if out.exists():
        out.unlink()
    prompt = sonnet_one_pass_prompt(BAND).format(
        CWD=cwd, SCRIPT=out, TODAY=date)
    metrics["writer"] = {
        "lane": f"claude:{SONNET_MODEL}", "band": BAND,
        "cwd": str(cwd), "prompt_chars": len(prompt),
        "context_window": 1000000,
        "script": str(out.relative_to(REPO)),
    }
    print(f"[write] claude --model {SONNET_MODEL} one pass, band={BAND}, "
          f"cwd={cwd}, prompt={len(prompt):,} chars", flush=True)

    t0 = time.time()
    proc = subprocess.run(
        [CLAUDE_BIN, "--dangerously-skip-permissions", "--model", SONNET_MODEL,
         "--output-format", "json", "-p", prompt],
        cwd=str(cwd), capture_output=True, text=True, timeout=5400)
    if proc.returncode != 0 or not proc.stdout.strip():
        err = (proc.stderr or proc.stdout or "")[-600:]
        metrics["writer"]["error"] = f"exit {proc.returncode}: {err}"
        sys.exit(f"WRITER LANE ERROR (claude:{SONNET_MODEL}): exit "
                 f"{proc.returncode}: {err}")
    try:
        blob = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        metrics["writer"]["error"] = f"unparsable CLI JSON: {e}"
        sys.exit(f"WRITER LANE ERROR: unparsable CLI JSON: {e}")
    if blob.get("is_error"):
        metrics["writer"]["error"] = str(blob.get("result"))[:600]
        sys.exit(f"WRITER LANE ERROR: {blob.get('result')}")

    usage = blob.get("usage") or {}
    # Count tokens the way the control's real usage is counted: every input token
    # the lane read, plus everything it wrote. cache_read is a read discount, not
    # a smaller prompt — it is the same text going back into the context window.
    inp = ((usage.get("input_tokens") or 0)
           + (usage.get("cache_creation_input_tokens") or 0)
           + (usage.get("cache_read_input_tokens") or 0))
    outp = usage.get("output_tokens") or 0
    if not out.exists():
        metrics["writer"]["error"] = "writer produced no script file"
        sys.exit("WRITER LANE ERROR: no script written to " + str(out))

    body = out.read_text(errors="replace")
    metrics["writer"].update({
        "ok": True, "seconds": round(time.time() - t0, 1),
        "input_tokens": usage.get("input_tokens"),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
        "output_tokens": outp,
        "tokens_total": inp + outp,
        "tokens_basis": "MEASURED (claude CLI --output-format json usage)",
        "cost_usd": blob.get("total_cost_usd"),
        "session_id": blob.get("session_id"),
        "num_turns": blob.get("num_turns"),
        "spoken_words": spoken_words(body),
    })
    print(f"[write] {out} — {spoken_words(body):,} spoken words, "
          f"{inp + outp:,} tokens ({metrics['writer']['seconds']}s, "
          f"${blob.get('total_cost_usd')})", flush=True)


# The free local writer lane has a 32,768-token resident context (checked live
# against /api/ps) and Glimmer tokenises this bundle at a MEASURED 3.635
# chars/token. The production Claude writer has 1M. A's full source bundle is
# 219,574 chars (~60k tokens) and does not fit, so B reads a capped slice of the
# SAME files. This is a measured property of the lane, not a choice, and it is
# reported as a caveat on the result: part of any B<A gap is input budget.
CAPS = {"transcripts": (3, 2500), "articles": (2, 1800), "covered": (3, 1000),
        "recent_scripts": (2, 800), "evidence_rules": 2000, "evidence_ledger": 3000,
        "aired_digest": 1500}
OUTPUT_RESERVE_TOK = 9000   # ~4.8k for 3,500 spoken words + thinking


def compact_sources(src):
    """Same files as or_writer._gather_sources returns, capped to fit the writer
    lane's context. The topic brief and the build-pitch file go in WHOLE — they
    are the spine and the pitch is a pass/fail criterion. Kept here rather than
    edited into or_writer so the daily pipeline's prompts are not touched."""
    out = dict(src)
    for key, val in CAPS.items():
        if isinstance(val, int):                     # a single text blob
            out[key] = src[key][:val]
            continue
        n, cap = val
        out[key] = [(name, body[:cap] + (f"\n[... {len(body) - cap} more chars]"
                                         if len(body) > cap else ""))
                    for name, body in list(src.get(key, []))[:n]]
    return out


CHARS_PER_TOKEN = 3.635       # measured on muse-glimmer:30b-mlx, 2026-09-28


def ctx_tokens():
    """The context the writer lane currently has loaded, or None."""
    try:
        import urllib.request
        with urllib.request.urlopen(f"{OLLAMA}/api/ps", timeout=10) as r:
            models = json.load(r).get("models", [])
        return models[0].get("context_length") if models else None
    except Exception:                                          # noqa: BLE001
        return None


def stage_write(date, writer, metrics):
    full = writer._gather_sources()
    src = compact_sources(full)
    if not src["topic_brief"]:
        sys.exit("no .tmp/topic-brief.txt — nothing to write from")
    prompt = single_pass_prompt(writer, src, "This is a morning episode.")
    ctx = ctx_tokens() or 32768
    est_in = len(prompt) / CHARS_PER_TOKEN
    if est_in + OUTPUT_RESERVE_TOK > ctx:
        sys.exit(f"WRITER LANE ERROR: prompt ~{est_in:,.0f} tok + "
                 f"{OUTPUT_RESERVE_TOK:,} output exceeds the lane's {ctx:,}-token "
                 f"context — lower CAPS in bin/test-single-pass.py")
    metrics["writer"] = {
        "lane": f"ollama:{WRITER}", "prompt_chars": len(prompt),
        "context_tokens": ctx, "prompt_tokens_est": round(est_in),
        "full_bundle_chars": len(full["topic_brief"]) + sum(
            len(b) for _, b in full["transcripts"] + full["articles"]),
    }
    print(f"[write] {WRITER}  prompt={len(prompt):,} chars (~{est_in:,.0f} tok, "
          f"ctx {ctx:,})", flush=True)

    t0 = time.time()
    payload = json.dumps({
        "model": WRITER, "prompt": prompt, "stream": False, "think": True,
        "options": {"num_ctx": ctx, "num_predict": 8000, "temperature": 0.7},
        "keep_alive": "2h",
    })
    try:
        import urllib.request
        req = urllib.request.Request(f"{OLLAMA}/api/generate", data=payload.encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5400) as r:
            data = json.load(r)
    except Exception as e:                                    # noqa: BLE001
        metrics["writer"]["error"] = f"{type(e).__name__}: {e}"
        sys.exit(f"WRITER LANE ERROR: {type(e).__name__}: {e}")
    if not data.get("done"):
        metrics["writer"]["error"] = str(data.get("error"))
        sys.exit(f"WRITER LANE ERROR: not done: {data.get('error')}")

    body = writer._clean_script(data.get("response", ""))
    out = TEST_DIR / f"{date}-single-pass.txt"
    out.write_text(body.rstrip() + "\n")
    metrics["writer"].update({
        "ok": True, "seconds": round(time.time() - t0, 1),
        "prompt_tokens": data.get("prompt_eval_count"),
        "completion_tokens": data.get("eval_count"),
        "script": str(out.relative_to(REPO)),
    })
    print(f"[write] {out} — {spoken_words(body)} spoken words in "
          f"{data.get('eval_count')} tokens ({metrics['writer']['seconds']}s)", flush=True)


# -------------------------------------------------------------------- qc ---


def b_script(date):
    """Variant B's script for the lane this run is testing."""
    return TEST_DIR / (f"{date}-sonnet-{BAND}.txt" if WRITER == "sonnet"
                       else f"{date}-single-pass.txt")


def stage_qc(date, metrics):
    """The production QC, run on both variants exactly as generate-episode.sh
    runs it (same command file, same 3 skeptics, same synthesis)."""
    variants = {
        "A": (LIVE / "scripts" / f"killen-time-{date}.txt",
              TEST_DIR / f"{date}-variant-A-copy.txt"),
        "B": (b_script(date), None),
    }
    metrics["qc"] = {}
    for key, (src, copy) in variants.items():
        if not src.exists():
            metrics["qc"][key] = {"error": f"missing {src}"}
            continue
        target = copy or src
        if copy:
            copy.write_text(src.read_text())
        prompt = (
            f"Read the file .claude/commands/qc-episode.md and follow its "
            f"instructions exactly.\nYour working directory is {LIVE}.\n"
            f"The script to QC is: {target}\n\n"
            f"Sourcing rule for Agent C: any specific (number, quote, name, score, "
            f'"the hosts argued") attached to a topic-brief item labelled "(no '
            f'transcript)" — or whose text was never provided — is UNSOURCED and '
            f"MUST-FIX. Also cut invented callbacks that name a story absent from "
            f"the last 7 days.\n"
            f"NOTE: {date} is in the dedup ledger because it already aired. Judge "
            f"freshness/dedup on that basis, not as a fresh re-air.\n"
        )
        print(f"[qc] variant {key} …", flush=True)
        t0 = time.time()
        # Same invocation generate-episode.sh uses for a QC step.
        proc = subprocess.run(
            ["claude", "--dangerously-skip-permissions", "--model", "sonnet",
             "-p", prompt],
            cwd=str(LIVE), capture_output=True, text=True, timeout=5400)
        blob = proc.stdout or ""
        m = re.findall(r"QC VERDICT:\s*(PASS|FAIL)", blob)
        metrics["qc"][key] = {
            "verdict": m[-1] if m else "NO-VERDICT",
            "seconds": round(time.time() - t0, 1),
            "exit": proc.returncode,
            "script": str(target.relative_to(LIVE)) if str(target).startswith(str(LIVE)) else str(target),
        }
        (TEST_DIR / f"{date}-qc-{key}{SUFFIX}.log").write_text(blob + "\n" + proc.stderr)
        print(f"[qc] variant {key}: {metrics['qc'][key]['verdict']}", flush=True)


# ------------------------------------------------------------------ scan ---

# Seam/leak scan. Two classes, and each pattern has to be the DEFECT rather than
# ordinary English — a scanner that fires on the show's own name ("the Killen Time
# Update", which is public by design) or on a podcast called "Locked On" reports
# noise and makes "0 defects" meaningless. Calibration on the 09-28 control below.
SEAM_PATTERNS = [
    # 1. Editorial scaffolding left over from the two-pass construction. Tuned on
    #    the 09-25…09-28 control set so it fires on the two real seams (09-25 L3
    #    "In the second half:", 09-27 L145 "out of this half") and NOT on ordinary
    #    English — 09-26 L166 "the first half of the review" and 09-27 L45 "the
    #    other half of Naam's case" are prose about a film and about a case.
    ("half_reference", r"\bthis half\b|\bin the (first|second|back) half\b|"
                       r"\bthe (first|second|back) half of (the|this) "
                       r"(show|episode|morning|update|hour)\b|"
                       r"\bthe other half of (the|this) (show|episode|morning|update)\b|"
                       r"\b(covered|came up|talked about|we said|we discussed) "
                       r"(it|that|this) (in|back in) the (first|second|back) half\b"),
    ("pass_number", r"\bpass (one|two|1|2)\b|\bthe first pass\b|\bthe second pass\b|"
                    r"\bpass-1\b|\bpass-2\b"),
    ("production_meta", r"\bthe draft\b|\bfirst draft\b|\brevised version\b|"
                        r"\bwe('ll| will) (expand|top up|top-up|pad)\b|"
                        r"\bword (count|target)s?\b|"
                        r"\bas (I|we) (mentioned|said) (earlier|above)\b"),
    # 2. GUARDRAILS "Never include internal fleet state". "killen time update" is
    # the show's public name and is allowed; the repo is not.
    ("internal_name", r"observer-system|brainrot-radio|killen-time-podcast|"
                      r"\.observer/|status\.d|handoff\.md|inbox\.md|calibration\.md|"
                      r"launchd|launchctl|LaunchAgent|\bplist\b|\.venv|\bsweeper\b|"
                      r"\bworktree\b|kt-podcast|fleet-optimizer|model-router|"
                      r"spotify-markets|\bkillen-time\b(?! update)|"
                      r"\bblocked on\b[^.]{0,40}\b(role|agent|model|lane|task|router|fleet|pipeline)\b|"
                      r"\btickler\b|\btasks?\.db\b|\bINBOX\b"),
    ("internal_metric", r"\b(our|my) (agents|roles|daemons?|workers?|repos?|registry|ledger)\b|"
                        r"\bI (dispatched|queued|greenlighted)\b|\bthe observer\b"),
    ("private_system", r"\bgreenlight the build\b|\bpoint an agent at\b|"
                       r"\bfleet budget\b|\bburn budget\b|\bcredit balance\b|"
                       r"\bfree lane\b|\brouter lane\b|\bthe pause flag\b|"
                       r"\bbuild-pitches folder\b"),
]
VALID_TAGS = {"BASIL", "BROOKE", "TRANSITION"}
# The 09-28 pitch is the "effort dial" one. A pitch counts as present only if a
# SINGLE substantive block carries the mechanism AND its source, with enough
# airtime to be a real segment — not a passing clause.
PITCH_TERMS = ("effort", "low", "medium", "max", "escalat", "ladder", "cheaper",
               "cost per task", "price", "budget")
PITCH_SOURCE = ("opus 5.5", "anthropic", "artificial analysis", "berman", "arxiv")
PITCH_MIN_WORDS = 150


def detect_build_pitch(text: str):
    """Return (present, evidence) for a dedicated Build-Pitch-of-the-Day block."""
    blocks = re.split(r"\[TRANSITION\]", text)
    for raw in blocks:
        block = re.sub(r"\[(BASIL|BROOKE)\]", " ", raw)
        if len(block.split()) < PITCH_MIN_WORDS:
            continue
        low = block.lower()
        hits = [t for t in PITCH_TERMS if t in low]
        srcs = [s for s in PITCH_SOURCE if s in low]
        if len(hits) >= 3 and srcs:
            return True, {"words": len(block.split()), "terms": hits[:6],
                          "sources": srcs[:3],
                          "text": " ".join(block.split())[:400]}
    return False, {}


def estimate_writer_A(date, metrics):
    """A's writer tokens are NOT logged by generate-episode.sh. Estimate them
    from the corpus the two Claude passes were pointed at, at B's MEASURED
    chars-per-input-token and tokens-per-output-word rates. Labelled ESTIMATE
    everywhere it is used."""
    files = [LIVE / "CLAUDE.md", LIVE / ".tmp" / "topic-brief.txt",
             LIVE / ".tmp" / "build-pitches.md", LIVE / ".tmp" / "covered-pending-2026-09-28.json"]
    for d in (".tmp/transcripts", ".tmp/articles", ".claude/context"):
        files += sorted((LIVE / d).glob("*")) if (LIVE / d).exists() else []
    files += sorted((LIVE / "scripts").glob(".covered-*.json"))[-7:]
    files += sorted((LIVE / "scripts").glob("killen-time-*.txt"))[-3:]
    files = [f for f in files if f.is_file()]
    chars = sum(f.stat().st_size for f in files)
    log = (LIVE / "logs" / f"generate-{date.replace('-', '')}-040000.log")
    pass1, combined = 0, 0
    if log.exists():
        txt = log.read_text(errors="replace")
        m1 = re.search(r"Pass 1 complete: (\d+) words", txt)
        m2 = re.search(r"Combined script: (\d+) words", txt)
        pass1 = int(m1.group(1)) if m1 else 0
        combined = int(m2.group(1)) if m2 else 0
    return {"writer_input_chars": chars * 2,  # both passes read the same corpus
            "writer_input_files": len(files), "pass1_words": pass1,
            "pass2_words": max(0, combined - pass1), "source": "ESTIMATE"}


def measure_writer_A_real(date):
    """A's REAL writer tokens, summed from the session transcripts.

    generate-episode.sh does not log writer tokens — PR #42 had to estimate them.
    It does not need to: every `claude -p` run writes a transcript under
    ~/.claude/projects/-Users-kylekillen-brainrot-radio/ carrying per-message
    `usage`, so the control's cost is a measurement, on the same fields the
    Sonnet writer reports (input + cache_creation + cache_read + output).

    The writer sessions are identified by their own opening prompt, not by clock
    time: the 09-28 run's four sessions are the build-pitch reporter, pass 1,
    pass 2 and QC, and only pass 1 + pass 2 are "the writer". Returns None if
    the transcripts are not there, so the caller reports INCONCLUSIVE rather
    than silently falling back to an estimate.
    """
    root = Path(os.environ.get("KT_CLAUDE_PROJECTS",
                               str(Path.home() / ".claude" / "projects"
                                   / "-Users-kylekillen-brainrot-radio")))
    if not root.is_dir():
        return None
    day = date.replace("-", "")
    # The pipeline logs its own step boundaries; the writer sessions are the two
    # that bracket "Pass 1 complete" and "Combined script".
    log = LIVE / "logs" / f"generate-{day}-040000.log"
    if not log.exists():
        cands = sorted(root.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    else:
        cands = [p for p in root.glob("*.jsonl")
                 if date in p.read_text(errors="replace")[:2000]]
    writer_sessions, total_in, total_out = [], 0, 0
    for p in cands:
        # The opening prompt lands in the transcript's first records — a
        # queue-operation enqueue for a `claude -p` run, or the first user
        # message — so read the head rather than guessing which record carries
        # it. Only the two writer passes open with "FIRST HALF"/"SECOND HALF";
        # the build-pitch reporter and QC open differently.
        try:
            head = p.read_text(errors="replace")[:4000]
        except OSError:
            continue
        m = re.search(r"FIRST HALF|SECOND HALF", head)
        if not m:
            continue          # build-pitch reporter, QC, or an unrelated session
        opener = head[max(0, m.start() - 60):m.end() + 40].replace("\\n", " ")
        pin, pout = 0, 0
        for line in p.open(errors="replace"):
            try:
                o = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if o.get("type") != "assistant":
                continue
            u = (o.get("message") or {}).get("usage") or {}
            if not u:
                continue
            pin += ((u.get("input_tokens") or 0)
                    + (u.get("cache_creation_input_tokens") or 0)
                    + (u.get("cache_read_input_tokens") or 0))
            pout += u.get("output_tokens") or 0
        writer_sessions.append({"session": p.stem,
                                 "pass": ("pass 1" if "FIRST HALF" in opener
                                          else "pass 2"),
                                 "input_tokens": pin, "output_tokens": pout,
                                 "total": pin + pout})
        total_in += pin
        total_out += pout
    if not writer_sessions:
        return None
    return {"tokens_total": total_in + total_out,
            "input_tokens": total_in, "output_tokens": total_out,
            "sessions": writer_sessions,
            "source": "MEASURED — ~/.claude/projects session transcripts",
            "note": "summed over the writer passes only; the build-pitch "
                    "reporter and QC sessions are excluded"}


def b_tok_total(metrics):
    w = metrics.get("writer", {})
    return (w.get("prompt_tokens") or 0) + (w.get("completion_tokens") or 0)


def stage_scan(date, metrics):
    metrics["seam"] = {}
    paths = {"A": LIVE / "scripts" / f"killen-time-{date}.txt",
             "B": b_script(date)}
    for key, path in paths.items():
        if not path.exists():
            metrics["seam"][key] = {"error": f"missing {path}"}
            continue
        text = path.read_text(errors="replace")
        hits = []
        for name, pat in SEAM_PATTERNS:
            for m in re.finditer(pat, text, re.IGNORECASE):
                line = text[:m.start()].count("\n") + 1
                ctx = " ".join(text[max(0, m.start() - 60):m.end() + 60].split())
                hits.append({"rule": name, "line": line, "match": m.group(0), "context": ctx})
        # structural / repeat scan
        blocks = [b.strip() for b in re.split(r"\[(?:BASIL|BROOKE|TRANSITION)\]", text) if b.strip()]
        norm = [" ".join(b.lower().split()) for b in blocks]
        repeats = [{"block_words": len(b.split()),
                    "text": " ".join(b.split())[:160]}
                   for b in norm if len(b.split()) >= 40 and norm.count(b) > 1]
        tags = re.findall(r"^\[(\w+)\]", text, re.MULTILINE)
        bad_tags = sorted({t for t in tags if t not in VALID_TAGS})
        collisions, prev, transition_run = 0, None, 0
        for t in tags:
            if t in ("BASIL", "BROOKE"):
                if t == prev:
                    collisions += 1
                prev, transition_run = t, 0
            else:
                prev, transition_run = None, transition_run + 1
        metrics["seam"][key] = {
            # "defects" = the four classes the test names: half references, pass
            # numbers, repeated segments, fleet-internal names/state. Structure
            # is reported separately because production QC owns it.
            "defects": len(hits) + len(repeats),
            "pattern_hits": len(hits),
            "hits": hits,
            "repeated_blocks": repeats,
            "speaker_collisions": collisions,
            "back_to_back_transitions": max(0, transition_run - 1),
            "invalid_tags": bad_tags,
            "em_dash_dividers": len(re.findall(r"^---\s*$", text, re.MULTILINE)),
        }
        print(f"[scan] {key}: {len(hits)} seam/leak hits, {collisions} speaker "
              f"collisions, {len(repeats)} repeated blocks", flush=True)


# ----------------------------------------------------------------- judge ---

JUDGE_PROMPT = """You are scoring two candidate scripts for the daily Killen Time podcast, a two-host (BASIL, BROOKE) personalised news show. Both were written from the SAME day's source material by the same editorial rules. Only their length and drafting method differ.

Judge on four axes, each 1-5 (5 = excellent, 3 = adequate, 1 = poor):
  SOURCING   — is every specific claim, number, quote and attribution traceable to the supplied material? Are unsourced specifics and invented callbacks absent?
  SUBSTANCE  — does it actually deliver insight and concrete detail for an expert listener, or is it summary filler?
  PITCH      — quality of the Build Pitch of the Day exchange: is the technique explained concretely, sourced, and pitched in general terms without describing the listener's private setup? (If a script has no build pitch, score it 1.)
  FLOW       — does it read as one coherent episode that holds attention from open to outro?

Return ONLY a JSON object, no prose, no fences, in exactly this shape:
{{"SOURCING": {{"X": n, "Y": n}}, "SUBSTANCE": {{"X": n, "Y": n}}, "PITCH": {{"X": n, "Y": n}}, "FLOW": {{"X": n, "Y": n}}, "REASON": "one sentence per script, X first then Y"}}

=== SCRIPT X ===
{x}

=== SCRIPT Y ===
{y}
"""


def _summon(model, prompt, timeout=2400):
    pf = Path("/tmp") / f"kt-test-{model.replace(':', '_').replace('/', '_')}.txt"
    pf.write_text(prompt)
    cmd = [str(OBSERVER_PY), "-m", "observer.dream.external_summon", "--role",
           "killen-time", "--model", model, "--message-file", str(pf),
           "--out", str(pf) + ".out", "--timeout-sec", str(timeout), "--json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 180)
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            data = json.loads(line)
            data["model"] = model        # the cache must say which lane produced it
            return data
    return {"ok": False, "model": model,
            "error": f"unparsable dispatch output: {proc.stdout[-500:]}"}


def _judge_claude(prompt: str, model: str = "opus", timeout: int = 2400) -> dict:
    """An Anthropic judge, through the same claude CLI the writer and QC use.

    A 5/2 spread on a quality rubric deserves a second, stronger opinion before
    anything about the show's format changes, and a free-model judge alone is not
    that. Returns the external_summon-shaped dict the scorer reads.
    """
    pf = Path("/tmp") / f"kt-judge-{model}.txt"
    pf.write_text(prompt)
    proc = subprocess.run(
        [CLAUDE_BIN, "--dangerously-skip-permissions", "--model", model,
         "-p", prompt], capture_output=True, text=True, timeout=timeout)
    blob = (proc.stdout or "").strip()
    if proc.returncode != 0 or not blob:
        return {"ok": False, "model": model,
                "error": f"exit {proc.returncode}: {(proc.stderr or '')[-400:]}"}
    return {"ok": True, "model": model, "reply": blob}


def _parse_scores(blob: str):
    m = re.search(r"\{.*\}", blob, re.S)
    scores = json.loads(m.group(0))
    axes = ("SOURCING", "SUBSTANCE", "PITCH", "FLOW")
    return ({k: int(scores[k]["X"]) for k in axes},
            {k: int(scores[k]["Y"]) for k in axes},
            scores.get("REASON", ""))


def stage_judge(date, metrics):
    """TWO blind judges, order shuffled: space-bunny-free and Anthropic Opus.

    Each judge gets its own shuffled X/Y order, seeded and recorded, so a judge
    cannot infer which script is the control from position. A cached successful
    dispatch is reused: re-scoring a variant must not re-spend the judge's
    tokens, and the labels are the whole point of the stage.
    """
    a = (LIVE / "scripts" / f"killen-time-{date}.txt").read_text(errors="replace")
    b = b_script(date).read_text(errors="replace")
    text = {"A": a, "B": b}
    judges = [j.strip() for j in os.environ.get(
        "KT_TEST_JUDGES", "space-bunny-free,opus").split(",") if j.strip()]

    out = {}
    for lane in judges:
        # A per-lane seed: the same shuffle for both judges would let one judge's
        # position preference leak into the other's read of the pair.
        seed = int(hashlib.sha256(f"{date}|{lane}".encode()).hexdigest()[:8], 16)
        order = ["A", "B"]
        random.Random(seed).shuffle(order)
        first, second = order
        prompt = JUDGE_PROMPT.format(x=text[first], y=text[second])
        raw_path = TEST_DIR / f"{date}-judge-raw-{lane.replace(':', '_')}{SUFFIX}.json"
        print(f"[judge] {lane}  blind order: X={first} Y={second} (seed {seed})",
              flush=True)
        res = json.loads(raw_path.read_text()) if raw_path.exists() else {}
        reused = bool(res.get("ok"))
        if not reused:
            res = _summon(lane, prompt) if lane != "opus" else _judge_claude(prompt)
            raw_path.write_text(json.dumps(res, indent=1)[:20000])
        if not res.get("ok"):
            out[lane] = {"ok": False, "error": res.get("error"), "seed": seed}
            metrics["judge"] = {"ok": False, "by_lane": out}
            sys.exit(f"JUDGE LANE ERROR ({lane}): {res.get('error')}")
        try:
            got, other, reason = _parse_scores(res.get("reply", ""))
        except Exception as e:                                # noqa: BLE001
            out[lane] = {"ok": False, "error": f"unparsable scores: {e}",
                         "seed": seed, "raw": res.get("reply", "")[:2000]}
            metrics["judge"] = {"ok": False, "by_lane": out}
            sys.exit(f"JUDGE LANE ERROR ({lane}): unparsable score JSON: {e}")
        out[lane] = {
            "ok": True, "seed": seed, "reused_cached_dispatch": reused,
            "blind_order_XY": [first, second],
            "by_variant": {first: got, second: other},
            "reason": reason,
            "prompt_tokens": res.get("prompt_tokens"),
            "completion_tokens": res.get("completion_tokens"),
        }
        print(f"[judge] {lane}: {out[lane]['by_variant']}", flush=True)

    # Disagreement between judges is a result, not a footnote: report it.
    disagree = []
    if len(out) == 2:
        (l1, l2) = list(out)
        for axis in ("SOURCING", "SUBSTANCE", "PITCH", "FLOW"):
            for v in ("A", "B"):
                s1 = (out[l1].get("by_variant") or {}).get(v, {}).get(axis)
                s2 = (out[l2].get("by_variant") or {}).get(v, {}).get(axis)
                if s1 is not None and s2 is not None and s1 != s2:
                    disagree.append({"axis": axis, "variant": v,
                                     l1: s1, l2: s2})
    metrics["judge"] = {"ok": True, "lanes": list(out), "by_lane": out,
                        "disagreements": disagree}
    if disagree:
        print(f"[judge] judges disagree on {len(disagree)} cell(s): {disagree}",
              flush=True)


# ---------------------------------------------------------------- report ---


def stage_report(date, metrics):
    a_text = (LIVE / "scripts" / f"killen-time-{date}.txt").read_text(errors="replace")
    b_text = b_script(date).read_text(errors="replace")
    a_words, b_words = spoken_words(a_text), spoken_words(b_text)
    w = metrics.get("writer", {})
    b_tok = w.get("tokens_total") if WRITER == "sonnet" else b_tok_total(metrics)

    # A's real writer tokens, summed from the session transcripts the pipeline
    # itself wrote. MEASURED, not estimated — this rerun does not need the
    # estimate PR #42 had to use, and the token criterion only means something
    # when both sides are counted the same way.
    real_a = measure_writer_A_real(date)

    seam_b = metrics.get("seam", {}).get("B", {})
    seam_a = metrics.get("seam", {}).get("A", {})
    qc_b = (metrics.get("qc", {}).get("B") or {}).get("verdict")
    qc_a = (metrics.get("qc", {}).get("A") or {}).get("verdict")
    j = metrics.get("judge", {})
    by_lane = j.get("by_lane") or {}
    pitch_a, pitch_ea = detect_build_pitch(a_text)
    pitch_b, pitch_eb = detect_build_pitch(b_text)

    # Criterion 1 is "0 seam/leak defects NOT ALSO PRESENT IN A": the replay makes
    # A imperfect too, and only defects A does not share count against B.
    b_only = max(0, (seam_b.get("defects") or 0) - (seam_a.get("defects") or 0))

    # Criterion 4: each variant has its own band, pre-registered in the criteria
    # file committed before either variant existed.
    if BAND == "long":
        lo = LONG_SPEC[0] * (1 - LONG_TOLERANCE)
        hi = LONG_SPEC[1] * (1 + LONG_TOLERANCE)
        band_label = (f"{lo:,.0f}-{hi:,.0f} spoken words "
                      f"(spec {LONG_SPEC[0]:,}-{LONG_SPEC[1]:,} +/-15%)")
        in_band = lo <= b_words <= hi
    else:
        band_label = f"{B_MIN_WORDS}-{B_MAX_WORDS} spoken words"
        in_band = B_MIN_WORDS <= b_words <= B_MAX_WORDS

    # Criteria 6 and 7: BOTH judges must score B >= A. One dissenting judge fails.
    def both(axis):
        rows = []
        for lane, res in by_lane.items():
            bv = (res.get("by_variant") or {}).get("B", {}).get(axis)
            av = (res.get("by_variant") or {}).get("A", {}).get(axis)
            rows.append(f"{lane}: B {bv} / A {av}")
        verdict_ok = bool(by_lane) and all(
            (res.get("by_variant") or {}).get("B", {}).get(axis, 0)
            >= (res.get("by_variant") or {}).get("A", {}).get(axis, 0)
            for res in by_lane.values())
        return verdict_ok, "; ".join(rows) or "no judge scores"

    a_tok = (real_a or {}).get("tokens_total")
    qc_real = metrics.get("qc_real_defects")
    checks = [
        ("B has 0 seam/leak defects not also in A", b_only == 0,
         f"B {seam_b.get('defects')} vs A {seam_a.get('defects')} -> {b_only} B-only"),
        ("B gets no QC FAIL beyond dedup-replay items",
         qc_b == "PASS" or (qc_real is not None and qc_real == 0),
         f"QC verdict {qc_b}"
         + (f", {qc_real} real (non-dedup) MUST-FIX" if qc_real is not None else "")),
        ("B includes a Build Pitch of the Day", pitch_b,
         f"{pitch_eb.get('words', 0)}-word block, sources {pitch_eb.get('sources')}"
         if pitch_b else "no qualifying pitch block found"),
        (f"B is within its length band ({band_label})", in_band,
         f"{b_words} spoken words"),
        ("B writer tokens <= 60% of A's (both MEASURED)",
         bool(a_tok) and b_tok is not None and b_tok <= 0.60 * a_tok,
         f"B {b_tok:,} vs A {a_tok:,} = {100 * b_tok / a_tok:.0f}%"
         if a_tok and b_tok is not None else "n/a"),
        ("BOTH judges score B >= A on SOURCING", both("SOURCING")[0],
         both("SOURCING")[1]),
        ("BOTH judges score B >= A on SUBSTANCE", both("SUBSTANCE")[0],
         both("SUBSTANCE")[1]),
    ]
    if not j.get("ok"):
        verdict = "INCONCLUSIVE — judge lane errored"
    elif not w.get("ok"):
        verdict = "INCONCLUSIVE — writer lane errored"
    elif not a_tok:
        verdict = "INCONCLUSIVE — A's real writer tokens not measurable"
    elif any(not ok for _, ok, _ in checks):
        verdict = "FAIL"
    else:
        verdict = "PASS"

    metrics.update({
        "date": date, "band": BAND, "verdict": verdict,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "A": {"script": f"scripts/killen-time-{date}.txt", "spoken_words": a_words,
              "writer": "claude sonnet, two agentic passes (production, as aired)",
              "writer_tokens": a_tok,
              "writer_tokens_basis": "MEASURED — summed from the 09-28 claude "
                                     "session transcripts' own per-message usage",
              "writer_tokens_detail": real_a,
              "qc": qc_a, "seam_defects": seam_a.get("defects"),
              "build_pitch": pitch_a, "build_pitch_evidence": pitch_ea},
        "B": {"script": str(b_script(date).relative_to(REPO)),
              "spoken_words": b_words,
              "writer": (f"claude {SONNET_MODEL}, ONE pass" if WRITER == "sonnet"
                         else f"ollama:{WRITER}, one pass"),
              "writer_tokens": b_tok,
              "writer_tokens_basis": w.get("tokens_basis", "MEASURED"),
              "writer_detail": w,
              "qc": qc_b, "seam_defects": seam_b.get("defects"),
              "b_only_seam_defects": b_only,
              "build_pitch": pitch_b, "build_pitch_evidence": pitch_eb},
        "judges": by_lane,
        "judge_disagreements": j.get("disagreements", []),
        "dedup_replay_note": metrics.get("dedup_note", ""),
        "checks": [{"criterion": c, "pass": ok, "evidence": ev} for c, ok, ev in checks],
    })
    name = f"{date}-single-pass-metrics{SUFFIX}.json"
    (TEST_DIR / name).write_text(json.dumps(metrics, indent=1))
    print(f"[report] {name} verdict: {verdict}")
    for c, ok, ev in checks:
        print(f"   [{'PASS' if ok else 'FAIL'}] {c} — {ev}")
# ------------------------------------------------------------------ main ---

STAGES = ["manifest", "write", "qc", "scan", "judge", "report"]


def main():
    # or_writer/dedup_guard use PEP 604 unions (3.10+). Re-exec into the repo's
    # own venv rather than failing with a confusing TypeError on the system 3.9.
    if sys.version_info < (3, 10):
        vpy = LIVE / "venv" / "bin" / "python"
        if vpy.exists():
            os.execv(str(vpy), [str(vpy), os.path.abspath(__file__), *sys.argv[1:]])
        sys.exit("need Python 3.10+ and no repo venv found at " + str(vpy))
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD of the aired episode to replay")
    ap.add_argument("--stage", default="all", choices=STAGES + ["all"])
    args = ap.parse_args()
    date = args.date
    TEST_DIR.mkdir(exist_ok=True)
    mp = TEST_DIR / f"{date}-single-pass-metrics{SUFFIX}.json"
    metrics = json.loads(mp.read_text()) if mp.exists() else {"date": date}
    metrics["stages"] = sorted(set(metrics.get("stages", [])) | {args.stage})
    mp.write_text(json.dumps(metrics, indent=1))
    # The Sonnet path never touches or_writer: it invokes the claude CLI against
    # a frozen bundle, so the production source-gatherer is not needed.
    need_or_writer = WRITER != "sonnet" and args.stage in ("all", "write", "report")
    writer = _load_modules() if need_or_writer else None
    run = STAGES if args.stage == "all" else [args.stage]
    for stage in run:
        if stage == "manifest":
            if BUNDLE:
                # The frozen bundle is the source of record for a Sonnet run:
                # fingerprint what the writer will actually read, not the live
                # .tmp/, which has drifted since the control was written.
                root = Path(BUNDLE)
                files = [f for f in sorted(root.rglob("*")) if f.is_file()]
            else:
                files = [LIVE / ".tmp" / "topic-brief.txt", LIVE / ".tmp" / "build-pitches.md",
                         LIVE / ".tmp" / f"covered-pending-{date}.json"]
                files += sorted((LIVE / ".tmp" / "transcripts").glob("*.txt"))
                files += sorted((LIVE / ".tmp" / "articles").glob("*.txt"))
                files += sorted((LIVE / "scripts").glob(".covered-*.json"))[-7:]
                files += sorted((LIVE / "scripts").glob("killen-time-*.txt"))[-3:]
            manifest = [sha(f) for f in files if f.exists()]
            (TEST_DIR / f"{date}-single-pass-sources{SUFFIX}.json").write_text(json.dumps(
                {"date": date, "root": BUNDLE or str(LIVE), "files": manifest}, indent=1))
            print(f"[manifest] {len(manifest)} source files fingerprinted")
        elif stage == "write":
            # KT_TEST_WRITER=sonnet takes the Sonnet one-pass path: the same
            # claude CLI invocation generate-episode.sh makes, the prompt changed
            # only so it writes the whole episode in one pass.
            if WRITER == "sonnet":
                stage_write_sonnet(date, metrics)
            else:
                stage_write(date, writer, metrics)
        elif stage == "qc":
            stage_qc(date, metrics)
        elif stage == "scan":
            stage_scan(date, metrics)
        elif stage == "judge":
            stage_judge(date, metrics)
        elif stage == "report":
            stage_report(date, metrics)
        mp.write_text(json.dumps(metrics, indent=1))


if __name__ == "__main__":
    main()
