#!/usr/bin/env python3
"""One-off: generate a FULL Killen Time episode entirely on Gemini (free offload),
PER-SEGMENT so it clears voice.py's 6000-word floor by covering MORE material
(Gemini Flash writes concise per call, so we ask it for several segments instead of
one giant pass). Reuses or_writer's context-gathering + system prompt + format.
Output: scripts/killen-time-gemini-<date>.txt
"""
import datetime
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import or_writer as ow          # noqa: E402
import or_complete              # noqa: E402

TODAY = datetime.date.today().isoformat()
# GEMINI_OUT lets the daily pipeline write to the standard episode path so QC/render/
# publish find it; standalone defaults to a -gemini- name.
OUT = (pathlib.Path(os.getenv("GEMINI_OUT")) if os.getenv("GEMINI_OUT")
       else ow.SCRIPTS_DIR / f"killen-time-gemini-{TODAY}.txt")

src = ow._gather_sources()
if not src.get("topic_brief"):
    print("FATAL: no .tmp/topic-brief.txt — run ingest first", file=sys.stderr)
    sys.exit(1)
block = ow._sources_block(src, include_recent_scripts=True)

# Faithful port of the original write-pass beats (or_writer._pass1/_pass2 / CLAUDE.md
# editorial guide) — same anchors, same framing, model swapped to Gemini. Split per
# beat (not one giant pass) only to reach length, since Gemini writes concise.
SEGMENTS = [
    ("intro+ai/tech",
     f"Write the SHOW INTRO and the AI & TECHNOLOGY block (Killen Time, {TODAY}). "
     "Cold-open on the single biggest story, then the show name and date; greeting matches the "
     "time of day above. AI & Technology (~2500-3500 words): LEAD with the highest-signal AI "
     "discussion in the sources — anchor on the AI Daily Brief (Nathaniel Whittemore) and Moonshots "
     "(Peter Diamandis) framing and their actual arguments/quotes whenever a fresh episode exists, "
     "and use the RSS news headlines (Techmeme, TechCrunch, Ars) only as context around that "
     "discussion, not the spine. Skip generic news-summary filler. [BASIL]/[BROOKE]/[TRANSITION] "
     "tags, alternate speakers. END with a [TRANSITION]. Do NOT write an outro."),
    ("agents+building",
     "Write the AGENTS & BUILDING WITH AI block — THE FEATURED BEAT (~3500-4500 words). How people "
     "actually run agents: harness/CLAUDE.md/context engineering, subagents and multi-agent "
     "orchestration, evals, MCP/tooling, dev-loop optimization. Pull concrete, STEALABLE practices "
     "(Claude Code releases, Latent Space, Simon Willison, One Useful Thing, AI & I, The Cognitive "
     "Revolution, No Priors, a16z, Dwarkesh, Karpathy). Frame every story as 'what can WE learn for "
     "our own multi-agent setup' — Kyle is building a team of delegated AIs. Quote actual techniques, "
     "not vibes. BUILD PITCH OF THE DAY: if the build-pitch summary provided above exists AND its "
     "first line is NOT 'NO_VERIFIED_PITCH', give the top pitch its own dedicated ~400-700 word "
     "exchange (what it is, who's doing it by name, the evidence it's real, exactly how it'd upgrade "
     "Kyle's setup), then have a host say it's logged in the build-pitches folder to greenlight. If "
     "the summary is missing or says NO_VERIFIED_PITCH, SKIP it — do NOT invent a pitch. "
     "[BASIL]/[BROOKE]/[TRANSITION], alternate speakers. Begin and end with a [TRANSITION]. No outro."),
    ("sports",
     "Write the SPORTS block — LEAD WITH NFL FOOTBALL (NBA is winding down) (~2500-3500 words). Build "
     "around the Ringer Fantasy Football Show (Kyle's named anchor) plus the Fantasy Footballers and "
     "Bill Barnwell — rankings, values/busts, roster strategy, real roster moves and league trends, "
     "with specific analyst quotes from the transcripts. Then cover NBA only for genuinely notable "
     "storylines (Finals, draft, major trades/FA), tighter. Don't force a connection between them. "
     "[BASIL]/[BROOKE]/[TRANSITION], alternate speakers. Begin and end with a [TRANSITION]. No outro."),
    ("entertainment+economics",
     "Write the ENTERTAINMENT and ECONOMICS/CULTURE blocks (~2000-3000 words each). Entertainment: "
     "industry news, deals, box office — engage at a SCREENWRITER/PRODUCER level. Economics/Culture: "
     "the best pieces from the rationalist/policy blogosphere in the sources. Include specific quotes "
     "from the transcripts/articles. [BASIL]/[BROOKE]/[TRANSITION], alternate speakers. Begin and end "
     "with a [TRANSITION]. No outro."),
    ("quick-hits+outro",
     "Write 2-3 QUICK HITS (shorter items that didn't warrant full segments), then the OUTRO: a brief "
     "recap of the most interesting thread and a short sign-off. Keep it tight. [BASIL]/[BROOKE]. "
     "Begin with a [TRANSITION]."),
]
DEDUP = ("DEDUP (critical): the sources block above includes RECENT EPISODE SCRIPTS "
         "and the .covered-*.json record of facts already said on air. Do NOT repeat "
         "ANY story, argument, quote, or fact already covered in a PREVIOUS episode — "
         "if a topic was covered before, SKIP it unless there's a genuinely new "
         "development. When in doubt, SKIP; a fresh story beats a retread.\n")

# Why this exists: each segment used to be generated INDEPENDENTLY from the same
# sources with no awareness of the others, so every segment grabbed the biggest
# stories and the episode repeated the same content 2-3x (the now-working QC caught
# this on 2026-06-21). Each segment now sees the EPISODE SO FAR and must cover only
# NEW material — segments written sequentially, each aware of the prior ones.
NO_REPEAT = (
    "NO INTERNAL REPETITION (critical): the EPISODE SO FAR (already written earlier in "
    "THIS episode) is shown below. Do NOT repeat ANY story, fact, quote, or argument "
    "already present in it — cover only DIFFERENT, new material in your segment.\n")

# Why this exists: with a word target and thin sources, the writer invented specifics
# (fake trades, invented projects, embellished bare headlines) to hit length. Reach
# length by covering MORE real stories, never by fabricating.
NO_FABRICATION = (
    "ACCURACY OVER LENGTH (critical): cover ONLY stories and facts actually present in "
    "the SOURCE MATERIAL above. Do NOT invent specifics, quotes, numbers, company "
    "announcements, product or project names, trades, deaths, or events to fill the "
    "word target. If a story is only a brief headline with no detail in the sources, "
    "give it one or two sentences — never embellish a thin source into a fabricated "
    "deep-dive. Reach length by covering MORE distinct real stories from the brief, NOT "
    "by padding or inventing. A shorter fully-sourced segment is required; a longer "
    "fabricated one is a failure.\n")

parts = []
for key, instr in SEGMENTS:
    episode_so_far = "\n\n".join(parts).strip()
    cross = ""
    if episode_so_far:
        cross = ("\n=== EPISODE SO FAR (already written — do NOT repeat any of this) ===\n"
                 + episode_so_far[-120000:] + "\n=== END EPISODE SO FAR ===\n")
    prompt = (block + cross + "\n\n=== YOUR TASK ===\n"
              "This is today's PRODUCTION episode — morning tone.\n"
              + DEDUP + (NO_REPEAT if episode_so_far else "") + NO_FABRICATION + instr)
    print(f"[gemini] generating segment: {key} ...", file=sys.stderr, flush=True)
    try:
        text = or_complete.complete(prompt, system=ow.SYSTEM, max_tokens=16000)
    except Exception as e:  # noqa: BLE001
        print(f"FATAL: segment {key} failed: {e}", file=sys.stderr)
        sys.exit(1)
    cleaned = ow._clean_script(text)
    parts.append(cleaned)
    print(f"  segment {key}: {len(cleaned.split())} words", file=sys.stderr, flush=True)

script = "\n\n".join(parts).strip() + "\n"


def _fix_joins(s: str) -> str:
    """Deterministic QC for the segment seams (no model): collapse doubled
    [TRANSITION] and break consecutive same-speaker blocks at segment boundaries —
    the recurring two-pass/segment-join defects QC exists to catch."""
    lines = [ln for ln in s.split("\n")]
    out, last_speaker = [], None
    for ln in lines:
        t = ln.strip()
        if t == "[TRANSITION]":
            # collapse doubled transition even across blank lines (each segment is
            # told to begin AND end with [TRANSITION], so seams produce a blank-line-
            # separated pair) — compare against the last NON-BLANK emitted line.
            prev = next((x.strip() for x in reversed(out) if x.strip()), "")
            if prev == "[TRANSITION]":
                continue
            last_speaker = None
            out.append(ln); continue
        m = re.match(r"\[(BASIL|BROOKE)\]", t)
        if m:
            sp = m.group(1)
            if sp == last_speaker:  # collision at a seam → flip to the other host
                other = "BROOKE" if sp == "BASIL" else "BASIL"
                ln = ln.replace(f"[{sp}]", f"[{other}]", 1); sp = other
            last_speaker = sp
        out.append(ln)
    return "\n".join(out)


script = _fix_joins(script)
OUT.write_text(script)
wc = len(script.split())
print(f"DONE: {OUT} ({wc} words)" + ("" if wc >= 6000 else "  ⚠️ UNDER 6000 — voice.py will refuse"))

# Covered-story saving — so TOMORROW's episode dedups against today (Gemini emits
# which brief stories it covered; we save via ingest.save_covered_stories). Non-fatal.
try:
    titles = re.findall(r"^##\s+\d+\.\s+(.+)$", src["topic_brief"], re.M)
    if titles:
        ask = ("Below is today's list of candidate story TITLES, then the episode "
               "script that was written. Return ONLY a JSON object mapping each title "
               "that was ACTUALLY covered in the script to a one-sentence summary of "
               "the specific facts/quotes used. Titles not covered are omitted.\n\n"
               "TITLES:\n" + "\n".join(f"- {t}" for t in titles) +
               "\n\nSCRIPT:\n" + script[:60000] + "\n\nJSON only:")
        raw = or_complete.complete(ask, max_tokens=4000)
        raw = raw[raw.find("{"): raw.rfind("}") + 1]
        covered = __import__("json").loads(raw)
        segments = {re.sub(r"[^\w]", "-", k.lower())[:60]: v for k, v in covered.items()}
        from ingest import save_covered_stories
        save_covered_stories(list(segments.keys()), segments)
        print(f"  saved {len(segments)} covered stories for tomorrow's dedup")
except Exception as e:  # noqa: BLE001
    print(f"  [WARN] covered-story save failed (dedup may miss today): {e}", file=sys.stderr)
