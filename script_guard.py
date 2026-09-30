#!/usr/bin/env python3
"""script_guard.py — deterministic gate for three defect classes the 3-skeptic
QC either finds late, finds by hand every time, or orders into the script itself.

Stdlib-only, no network, no model. Run it on the combined script before QC (so
the skeptics get hard evidence, the same way dedup_guard.py feeds them) and again
after the QC verdict (so anything the skeptics left behind is logged loudly and
written to a flag file). It NEVER aborts the pipeline on its own: an episode that
a heuristic dislikes must still ship, because 09-25, 09-27 and 09-29 were all
lost to a hard gate. Findings are evidence, the verdict is still QC's.

    collision — two blocks in a row spoken by the same host (BASIL/BASIL,
      BROOKE/BROOKE), including across a [TRANSITION] join. Recurred on 07-04,
      07-31, 08-02, 08-14, 08-22, and in the 09-28 single-pass test, where it
      doubled Basil's sign-off. QC's Coherence Skeptic is told to hunt these and
      repairs each by hand; nothing stops a new one being written.

    leak — private-system markers in a PUBLIC audio script. GUARDRAILS "Never put
      Kyle's PRIVATE system on air" (2026-09-24). Until 2026-09-29 the pass-1
      build-pitch prompt ORDERED the worst instance of this: it told the writer
      to say the pitch "is logged in the build-pitches folder so Kyle can point an
      agent at it and greenlight the build", which the Coherence Skeptic then
      deleted as a MUST-FIX under the same guardrail — a writer edit, every
      episode, for a line the prompt had just requested. The prompt no longer
      says it; this keeps a future drift from getting to the mic.

    byline — analysis credited to a named reporter the topic brief carries ONLY as
      a byline on a truncated RSS blurb. A Techmeme item's body is the headline
      restated and cut mid-word; it contains no analysis, so "Cheng Ting-Fang at
      Nikkei Asia notes the plant is a bet on ..." (09-28 variant B, caught by the
      Sourcing Skeptic) is an invention with a real person's name on it.

Usage:
    python3 script_guard.py check SCRIPT [--brief .tmp/topic-brief.txt]
        [--sources .tmp/transcripts .tmp/articles] [--json]

Exit 3 if anything is found, 0 if clean, 2 on bad usage.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# GUARDRAILS "Never include internal fleet state" / "Never put Kyle's PRIVATE
# system on air". Trimmed from the tuned set in bin/test-single-pass.py
# (SEAM_PATTERNS) to the markers that describe Kyle's setup rather than the
# show: the public name "the Killen Time Update" is allowed, the repo is not.
LEAK_PATTERNS = (
    ("internal_name",
     r"observer-system|brainrot-radio|killen-time-podcast|\.observer/|status\.d\b|"
     r"handoff\.md|inbox\.md|calibration\.md|launchd|launchctl|LaunchAgent|"
     r"\bplist\b|\.venv\b|\bsweeper\b|\bworktree\b|kt-podcast|fleet-optimizer|"
     r"model-router|\btickler\b|tasks?\.db\b"),
    ("internal_metric",
     r"\b(our|my) (agents|roles|daemons?|workers?|repos?|registry|ledger)\b|"
     r"\bI (dispatched|queued|greenlighted)\b|\bthe observer\b"),
    ("private_system",
     r"\bfleet budget\b|\bburn budget\b|\bcredit balance\b|\bfree lane\b|"
     r"\brouter lane\b|\bthe pause flag\b|\bdurable record\b|\bsignals folder\b|"
     # The locator is the leak. "so he can point an agent at it and greenlight the
     # build" is the ON-AIR-SAFE pointer the writer prompt now asks for, so the
     # phrase pair alone is NOT flagged — flagging it would just move the
     # contradiction this guard exists to end. What leaked, every time, was the
     # *where*: "in today's build-pitches folder, dated August third",
     # "build-pitches/2026-06-13.md", "in the durable record".
     r"\bbuild-pitches\b|\bbuild pitches\b"),
)

_TAG_RE = re.compile(r"^\[(BASIL|BROOKE|TRANSITION)\]", re.MULTILINE)
_SENT_RE = re.compile(r"(?<=[.!?])\s+")
# "Name / Outlet" byline, or "(Name/Outlet)" at the end of a brief headline.
_BODY_BYLINE_RE = re.compile(r"^([A-Z][\w'’\-]+(?:\s+[A-Z][\w'’\-]+)+)\s*/\s*([^:\n]{2,40}?)\s*:")
_HEAD_BYLINE_RE = re.compile(r"\(([A-Z][\w'’\-]+(?:\s+[A-Z][\w'’\-]+)+\s*/\s*[^)]{2,40})\)")
_ATTRIB_RE = re.compile(
    r"\b(notes?|noted|says?|said|argues?|argued|writes?|wrote|writing|"
    r"points? out|pointed out|reports? that|thinks?|warns?|warned|claims?|"
    r"tells?|told|explains?|reckons?|calculates?)\b", re.IGNORECASE)
_ITEM_RE = re.compile(r"^##\s+\d+\.\s", re.MULTILINE)
_SENTENCE_END = ".!?\"'’”)]"


def speaker_collisions(text):
    """Consecutive blocks by the same host. A [TRANSITION] does NOT reset the
    run: BASIL / [TRANSITION] / BASIL is the join defect QC is told to fix."""
    out, prev, prev_line = [], None, None
    run = 0
    for m in _TAG_RE.finditer(text):
        tag, line = m.group(1), text.count("\n", 0, m.start()) + 1
        if tag == "TRANSITION":
            run += 1
            if run > 1 and (not out or out[-1]["line"] != line):
                out.append({"rule": "back_to_back_transition", "line": line,
                            "speaker": "TRANSITION", "previous_line": line - 1})
            continue
        if tag == prev:
            out.append({"rule": "speaker_collision", "line": line,
                        "previous_line": prev_line, "speaker": tag})
        prev, prev_line, run = tag, line, 0
    return out


def leaks(text):
    out = []
    for rule, pat in LEAK_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            out.append({"rule": rule,
                        "line": text.count("\n", 0, m.start()) + 1,
                        "match": m.group(0),
                        "context": " ".join(text[max(0, m.start() - 60):m.end() + 60].split())})
    return out


def _items(brief):
    """[(headline, body)] per `## N. <headline>` item in the topic brief."""
    bounds = [m.start() for m in _ITEM_RE.finditer(brief)] + [len(brief)]
    out = []
    for a, b in zip(bounds, bounds[1:]):
        chunk = brief[a:b]
        lines = chunk.split("\n")
        headline = _ITEM_RE.sub("", lines[0]).strip()
        body = "\n".join(lines[1:]).strip()
        out.append((headline, body))
    return out


def _truncated(body):
    """An RSS blurb cut mid-word: no sentence-ending punctuation at the tail."""
    tail = body.rstrip()[-1:] if body.strip() else ""
    return bool(tail) and tail not in _SENTENCE_END


def _name_pattern(name):
    return re.compile(r"\b" + re.escape(name).replace(r"\-", r"[‑-]") + r"\b",
                      re.IGNORECASE)


def unsourced_bylines(text, brief, extra_sources=()):
    """Named reporters credited with analysis the sources do not contain.

    A name is only reported when it survives NOWHERE except as a byline on a
    truncated blurb: not in the rest of the brief, not in any fetched transcript
    or article. That keeps the check quiet on ordinary attribution."""
    items = _items(brief)
    truncated_blurbs = []
    for _headline, body in items:
        if _truncated(body):
            truncated_blurbs.append(body)
    # Everything the brief says that is NOT a truncated blurb body: headlines,
    # metadata, link lines, and any full-text item.
    residual = brief
    for chunk in truncated_blurbs:
        residual = residual.replace(chunk, "\n")
    # Bylines on a truncated item are exactly what we are testing.
    for headline, body in items:
        if _truncated(body):
            residual = residual.replace(headline, "\n")
    residual_low = residual.lower()
    haystacks = [residual_low] + [
        p.read_text(errors="replace").lower() for p in extra_sources if p.is_file()
    ]

    suspects = {}
    for headline, body in items:
        if not _truncated(body):
            continue
        names = [m.group(1) for m in _HEAD_BYLINE_RE.finditer(headline)]
        names += [m.group(1) for m in _BODY_BYLINE_RE.finditer(body)]
        for name in names:
            surname = name.split()[-1]
            if len(surname) < 3:
                continue
            suspects.setdefault(surname, name)

    out = []
    for surname, full in suspects.items():
        if any(_name_pattern(surname).search(h) for h in haystacks):
            continue  # the person is somewhere real — QC can trace the words
        pat = _name_pattern(surname)
        for line_no, line in enumerate(text.split("\n"), 1):
            if not pat.search(line):
                continue
            for sentence in _SENT_RE.split(line):
                if pat.search(sentence) and _ATTRIB_RE.search(sentence):
                    out.append({"rule": "unsourced_byline", "line": line_no,
                                "match": surname,
                                "context": " ".join(sentence.split())[:220]})
                    break
    return out


def check(script, brief=None, extra_sources=()):
    text = script.read_text(errors="replace")
    findings = speaker_collisions(text) + leaks(text)
    if brief is not None and brief.is_file():
        findings += unsourced_bylines(text, brief.read_text(errors="replace"),
                                     extra_sources)
    findings.sort(key=lambda f: (f["line"], f["rule"]))
    return findings


def _fmt(findings):
    lines = []
    for f in findings:
        if f["rule"] == "speaker_collision":
            lines.append(f"  L{f['previous_line']}/L{f['line']} {f['speaker']}: "
                         f"two {f['speaker']} blocks in a row — merge them into one "
                         f"block (do NOT flip the tag, it cascades).")
        elif f["rule"] == "back_to_back_transition":
            lines.append(f"  L{f['line']}: two [TRANSITION] tags back to back — "
                         f"spoken aloud as a divider.")
        elif f["rule"] == "unsourced_byline":
            lines.append(f"  L{f['line']} unsourced_byline: {f['context']} — "
                         f"'{f['match']}' appears in the brief only as a byline on "
                         f"a truncated blurb. Cut the analysis back to the blurb.")
        else:
            lines.append(f"  L{f['line']} {f['rule']}: \"{f['match']}\" — "
                         f"private system on public air. {f['context']}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--brief", default=str(ROOT / ".tmp" / "topic-brief.txt"),
                    help="topic brief (default .tmp/topic-brief.txt); the "
                         "byline check is skipped if it is absent")
    ap.add_argument("--sources", nargs="*", default=[],
                    help="extra source files/dirs searched for the named reporter")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("command", choices=["check"])
    ap.add_argument("script")
    a = ap.parse_args(argv)

    script = Path(a.script)
    if not script.is_file():
        print(f"script_guard: no such script: {script}", file=sys.stderr)
        return 2
    extra = [Path(p) for d in a.sources for p in
             (sorted(Path(d).rglob("*")) if Path(d).is_dir() else [Path(d)])]
    findings = check(script, Path(a.brief), extra)

    if a.json:
        print(json.dumps(findings, indent=2))
    elif findings:
        print(f"script_guard: {len(findings)} finding(s) in {script.name}")
        print(_fmt(findings))
    else:
        print(f"script_guard: clean ({script.name})")
    return 3 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
