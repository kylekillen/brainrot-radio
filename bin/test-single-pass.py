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


def stage_write(date, writer, metrics):
    src = writer._gather_sources()
    if not src["topic_brief"]:
        sys.exit("no .tmp/topic-brief.txt — nothing to write from")
    greeting = "This is a morning episode."
    prompt = single_pass_prompt(writer, src, greeting)
    metrics["writer"] = {"lane": f"ollama:{WRITER}", "prompt_chars": len(prompt)}
    print(f"[write] {WRITER}  prompt={len(prompt):,} chars", flush=True)

    body = ""
    t0 = time.time()
    payload = json.dumps({
        "model": WRITER, "prompt": prompt, "stream": False, "think": True,
        "options": {"num_ctx": 131072, "num_predict": 24000, "temperature": 0.7},
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


def stage_qc(date, metrics):
    """The production QC, run on both variants exactly as generate-episode.sh
    runs it (same command file, same 3 skeptics, same synthesis)."""
    variants = {
        "A": (LIVE / "scripts" / f"killen-time-{date}.txt",
              TEST_DIR / f"{date}-variant-A-copy.txt"),
        "B": (TEST_DIR / f"{date}-single-pass.txt", None),
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
        proc = subprocess.run(
            ["claude", "-p", "--model", "sonnet", "--permission-mode",
             "acceptEdits", prompt],
            cwd=str(LIVE), capture_output=True, text=True, timeout=5400)
        blob = proc.stdout or ""
        m = re.findall(r"QC VERDICT:\s*(PASS|FAIL)", blob)
        metrics["qc"][key] = {
            "verdict": m[-1] if m else "NO-VERDICT",
            "seconds": round(time.time() - t0, 1),
            "exit": proc.returncode,
            "script": str(target.relative_to(LIVE)) if str(target).startswith(str(LIVE)) else str(target),
        }
        (TEST_DIR / f"{date}-qc-{key}.log").write_text(blob + "\n" + proc.stderr)
        print(f"[qc] variant {key}: {metrics['qc'][key]['verdict']}", flush=True)


# ------------------------------------------------------------------ scan ---

SEAM_PATTERNS = [
    ("half_reference", r"\bthis half\b|\bfirst half\b|\bsecond half\b|\bback half\b|"
                       r"\bthe other half\b|\bfirst section\b|\bsecond section\b"),
    ("pass_number", r"\bpass (one|two|1|2)\b|\bthe first pass\b|\bthe second pass\b|"
                    r"\bpass-1\b|\bpass-2\b|\bpass 1\b|\bpass 2\b"),
    ("production_meta", r"\bthe draft\b|\bfirst draft\b|\brevised version\b|"
                        r"\bwe('ll| will) (expand|top up|top-up|pad)\b|"
                        r"\bword (count|target)s?\b|\bthis segment\b|\bas (I|we) (mentioned|said) (earlier|above)\b"),
    ("internal_name", r"observer-system|brainrot-radio|killen-time-podcast|"
                      r"\.observer/|status\.d|handoff\.md|inbox\.md|calibration\.md|"
                      r"launchd|launchctl|LaunchAgent|plist|\.venv|"
                      r"\bkt-podcast\b|\bfleet-optimizer\b|\bmodel-router\b|\bCOS\b|"
                      r"\bassay\b|\bkillen-time\b|\bkillen time\b|\bspotify-markets\b|"
                      r"\blocked on\b|\bblocked by\b|\bqueued for\b|\btask id\b|\btickler\b"),
    ("internal_metric", r"\b(our|my) (agents|roles|daemons?|workers?|repos?|registry|ledger)\b|"
                        r"\bI (dispatched|queued|greenlighted)\b|\bthe observer\b"),
    ("private_system", r"\bgreenlight the build\b|\bpoint an agent at\b|"
                       r"\bfleet budget\b|\bburn budget\b|\bcredit balance\b|"
                       r"\bfree lane\b|\brouter lane\b|\bthe pause flag\b|\bbuild-pitches folder\b"),
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


def b_tok_total(metrics):
    w = metrics.get("writer", {})
    return (w.get("prompt_tokens") or 0) + (w.get("completion_tokens") or 0)


def stage_scan(date, metrics):
    metrics["seam"] = {}
    paths = {"A": LIVE / "scripts" / f"killen-time-{date}.txt",
             "B": TEST_DIR / f"{date}-single-pass.txt"}
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
            "defects": len(hits),
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
            return json.loads(line)
    return {"ok": False, "error": f"unparsable dispatch output: {proc.stdout[-500:]}"}


def stage_judge(date, metrics):
    a = (LIVE / "scripts" / f"killen-time-{date}.txt").read_text(errors="replace")
    b = (TEST_DIR / f"{date}-single-pass.txt").read_text(errors="replace")
    seed = int(hashlib.sha256(date.encode()).hexdigest()[:8], 16)
    order = ["A", "B"]
    random.Random(seed).shuffle(order)
    first, second = order
    text = {"A": a, "B": b}
    prompt = JUDGE_PROMPT.format(x=text[first], y=text[second])
    print(f"[judge] {JUDGE}  blind order: X={first} Y={second} (seed {seed})", flush=True)
    res = _summon(JUDGE, prompt)
    (TEST_DIR / f"{date}-judge-raw.json").write_text(json.dumps(res, indent=1)[:20000])
    if not res.get("ok"):
        metrics["judge"] = {"ok": False, "lane": JUDGE, "error": res.get("error")}
        sys.exit(f"JUDGE LANE ERROR: {res.get('error')}")
    blob = res.get("reply", "")
    m = re.search(r"\{.*\}", blob, re.S)
    try:
        scores = json.loads(m.group(0))
    except Exception as e:                                    # noqa: BLE001
        metrics["judge"] = {"ok": False, "lane": JUDGE, "error": f"unparsable JSON: {e}",
                            "raw": blob[:2000]}
        sys.exit(f"JUDGE LANE ERROR: unparsable score JSON: {e}\n{blob[:800]}")
    got = {k: int(scores[k][first]) for k in ("SOURCING", "SUBSTANCE", "PITCH", "FLOW")}
    metrics["judge"] = {
        "ok": True, "lane": JUDGE, "seed": seed,
        "blind_order_XY": [first, second],
        "by_variant": {first: got, second: {k: int(scores[k][second])
                                            for k in ("SOURCING", "SUBSTANCE", "PITCH", "FLOW")}},
        "reason": scores.get("REASON", ""),
        "prompt_tokens": res.get("prompt_tokens"),
        "completion_tokens": res.get("completion_tokens"),
    }
    print(f"[judge] {metrics['judge']['by_variant']}", flush=True)


# ---------------------------------------------------------------- report ---


def stage_report(date, metrics):
    a_text = (LIVE / "scripts" / f"killen-time-{date}.txt").read_text(errors="replace")
    b_text = (TEST_DIR / f"{date}-single-pass.txt").read_text(errors="replace")
    a_words, b_words = spoken_words(a_text), spoken_words(b_text)
    w = metrics.get("writer", {})
    b_tok = b_tok_total(metrics)
    # A's writer tokens are not logged anywhere in the pipeline; estimate them
    # from the corpus A's two passes read, at B's MEASURED token rates.
    est = estimate_writer_A(date, metrics)
    out_per_word = (b_tok / b_words) if b_words else 0
    in_per_char = ((w.get("prompt_tokens") or 0) / w["prompt_chars"]) if w.get("prompt_chars") else 0
    a_tok = round(est["writer_input_chars"] * in_per_char
                  + (est["pass1_words"] + est["pass2_words"]) * out_per_word) or None
    est["tokens_estimate"] = a_tok
    metrics["writer_estimate_A"] = est

    seam_b, seam_a = metrics.get("seam", {}).get("B", {}), metrics.get("seam", {}).get("A", {})
    qc_b = (metrics.get("qc", {}).get("B") or {}).get("verdict")
    qc_a = (metrics.get("qc", {}).get("A") or {}).get("verdict")
    j = metrics.get("judge", {})
    jb, ja = (j.get("by_variant") or {}).get("B", {}), (j.get("by_variant") or {}).get("A", {})
    pitch_a, pitch_ea = detect_build_pitch(a_text)
    pitch_b, pitch_eb = detect_build_pitch(b_text)

    checks = [
        ("B has 0 seam/leak defects", seam_b.get("defects") == 0,
         f"{seam_b.get('defects')} hits ({', '.join(sorted({h['rule'] for h in seam_b.get('hits', [])})) or 'none'})"),
        ("B gets no QC FAIL", qc_b == "PASS", f"QC verdict {qc_b}"),
        ("B includes a Build Pitch of the Day", pitch_b,
         f"{pitch_eb.get('words', 0)}-word block, sources {pitch_eb.get('sources')}"
         if pitch_b else "no qualifying pitch block found"),
        (f"B is {B_MIN_WORDS}-{B_MAX_WORDS} spoken words",
         B_MIN_WORDS <= b_words <= B_MAX_WORDS, f"{b_words} spoken words"),
        ("B writer tokens <= 60% of A's (A = ESTIMATE)",
         bool(a_tok) and b_tok <= 0.60 * a_tok,
         f"B {b_tok:,} measured vs A ~{a_tok:,} estimated = "
         f"{100 * b_tok / a_tok:.0f}%" if a_tok else "n/a"),
        ("Judge scores B >= A on SOURCING", jb.get("SOURCING", 0) >= ja.get("SOURCING", 0),
         f"B {jb.get('SOURCING')} vs A {ja.get('SOURCING')}"),
        ("Judge scores B >= A on SUBSTANCE", jb.get("SUBSTANCE", 0) >= ja.get("SUBSTANCE", 0),
         f"B {jb.get('SUBSTANCE')} vs A {ja.get('SUBSTANCE')}"),
    ]
    hard_fail = any(not ok for _, ok, _ in checks[:3])
    judge_ok = (jb.get("SOURCING", 0) >= ja.get("SOURCING", 0)
                and jb.get("SUBSTANCE", 0) >= ja.get("SUBSTANCE", 0))
    if not j.get("ok"):
        verdict = "INCONCLUSIVE — judge lane errored"
    elif not w.get("ok"):
        verdict = "INCONCLUSIVE — writer lane errored"
    elif hard_fail or not judge_ok:
        verdict = "FAIL"
    elif all(ok for _, ok, _ in checks):
        verdict = "PASS"
    else:
        verdict = "INCONCLUSIVE — a soft criterion (word target / token budget) missed"

    metrics.update({
        "date": date, "verdict": verdict,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "A": {"script": f"scripts/killen-time-{date}.txt", "spoken_words": a_words,
              "writer": "claude sonnet, two passes (production, as aired)",
              "writer_tokens": a_tok, "writer_tokens_basis": "ESTIMATE — not logged",
              "qc": qc_a, "seam_defects": seam_a.get("defects"),
              "build_pitch": pitch_a, "build_pitch_evidence": pitch_ea},
        "B": {"script": f"test-runs/{date}-single-pass.txt", "spoken_words": b_words,
              "writer": f"ollama:{WRITER}, one pass",
              "writer_tokens": b_tok,
              "writer_tokens_basis": "MEASURED (ollama prompt_eval_count + eval_count)",
              "qc": qc_b, "seam_defects": seam_b.get("defects"),
              "build_pitch": pitch_b, "build_pitch_evidence": pitch_eb},
        "checks": [{"criterion": c, "pass": ok, "evidence": ev} for c, ok, ev in checks],
    })
    (TEST_DIR / f"{date}-single-pass-metrics.json").write_text(json.dumps(metrics, indent=1))
    print(f"[report] verdict: {verdict}")
    for c, ok, ev in checks:
        print(f"   [{'PASS' if ok else 'FAIL'}] {c} — {ev}")


# ------------------------------------------------------------------ main ---

STAGES = ["manifest", "write", "qc", "scan", "judge", "report"]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD of the aired episode to replay")
    ap.add_argument("--stage", default="all", choices=STAGES + ["all"])
    args = ap.parse_args()
    date = args.date
    TEST_DIR.mkdir(exist_ok=True)
    mp = TEST_DIR / f"{date}-single-pass-metrics.json"
    metrics = json.loads(mp.read_text()) if mp.exists() else {"date": date}
    metrics["stages"] = sorted(set(metrics.get("stages", [])) | {args.stage})
    mp.write_text(json.dumps(metrics, indent=1))
    writer = _load_modules() if args.stage in ("all", "write", "report") else None
    run = STAGES if args.stage == "all" else [args.stage]
    for stage in run:
        if stage == "manifest":
            files = [LIVE / ".tmp" / "topic-brief.txt", LIVE / ".tmp" / "build-pitches.md",
                     LIVE / ".tmp" / "covered-pending-2026-09-28.json"]
            files += sorted((LIVE / ".tmp" / "transcripts").glob("*.txt"))
            files += sorted((LIVE / ".tmp" / "articles").glob("*.txt"))
            files += sorted((LIVE / "scripts").glob(".covered-*.json"))[-7:]
            files += sorted((LIVE / "scripts").glob("killen-time-*.txt"))[-3:]
            manifest = [sha(f) for f in files if f.exists()]
            (TEST_DIR / f"{date}-single-pass-sources.json").write_text(json.dumps(
                {"date": date, "root": str(LIVE), "files": manifest}, indent=1))
            print(f"[manifest] {len(manifest)} source files fingerprinted")
        elif stage == "write":
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
