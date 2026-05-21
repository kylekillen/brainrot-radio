#!/usr/bin/env python3
"""
Killen Time -- Gemini Managed Agent experiment runner.

Hands BRIEF.md to a Gemini Managed Agent (the Antigravity agent announced at
Google I/O 2026), which spins up its own sandboxed Linux box, browses the web to
pull our sources, and builds a finished ~1-hour podcast episode. We then download
the sandbox contents and hand the MP3 to our own publish.py.

STATUS: This is staged but UNRUN. As of 2026-05-21 the only Google key on this
machine (the nanobanana free-tier key) returns HTTP 429 "not enough quota" on the
Managed Agents endpoint -- the feature is a PAID-TIER preview. The basic Gemini
endpoint works fine on the same key, so it's purely a billing/quota gate.

TO RUN once a billing-enabled key exists:
    export GOOGLE_AI_API_KEY=AIza...        # a key from a project with billing on
    python3 run.py

What's VERIFIED against Google's live docs (ai.google.dev, 2026-05-21):
  - endpoint:  POST https://generativelanguage.googleapis.com/v1beta/interactions
  - auth:      x-goog-api-key header  +  Api-Revision: 2026-05-20
  - body:      {agent, input:[{type:text,text}], environment:{type:remote}, stream}
  - agent id:  antigravity-preview-05-2026
  - the Interaction response carries: id, environment_id, output_text, steps
  - file pull: GET .../v1beta/files/environment-{ENV_ID}:download?alt=media (tar)

What's NOT verified (couldn't test -- no quota): the exact long-poll / completion
semantics for a build that takes many minutes. The code below streams the
response and also stores the environment_id so you can re-pull files. If Google's
async shape differs at run time, the streaming loop and the IDs we capture are
enough to adapt against the live docs. Marked UNVERIFIED inline.
"""

import json
import os
import pathlib
import sys
import time
import urllib.request
import urllib.error

HERE = pathlib.Path(__file__).resolve().parent
BASE = "https://generativelanguage.googleapis.com/v1beta"
AGENT = "antigravity-preview-05-2026"
API_REVISION = "2026-05-20"


def get_key() -> str:
    key = os.environ.get("GOOGLE_AI_API_KEY")
    if key:
        return key
    # fall back to the nanobanana .env (free tier -- will 429 on this endpoint)
    env = pathlib.Path.home() / "nanobanana-mcp" / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("GOOGLE_AI_API_KEY="):
                return line.split("=", 1)[1].strip()
    sys.exit("No GOOGLE_AI_API_KEY found. export one from a billing-enabled project.")


def post(path: str, body: dict, key: str, stream: bool = False):
    req = urllib.request.Request(
        f"{BASE}/{path}",
        data=json.dumps(body).encode(),
        headers={
            "x-goog-api-key": key,
            "Api-Revision": API_REVISION,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    return urllib.request.urlopen(req, timeout=900) if stream else urllib.request.urlopen(req, timeout=900)


def main():
    key = get_key()
    brief = (HERE / "BRIEF.md").read_text()

    body = {
        "agent": AGENT,
        "input": [{"type": "text", "text": brief}],
        "environment": {"type": "remote"},
        "stream": True,
    }

    print("→ launching managed agent with Killen Time brief...")
    try:
        resp = post("interactions", body, key, stream=True)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        print(f"✗ HTTP {e.code}: {detail}")
        if e.code == 429:
            print("\nThis is the known quota gate. Enable billing on the key's "
                  "Google Cloud project (or use a paid-tier key) and re-run.")
        sys.exit(1)

    interaction_id = None
    environment_id = None

    # Stream the step deltas so we can watch it browse / write / render.
    # UNVERIFIED: exact SSE chunk shape -- we print raw lines and best-effort
    # parse any JSON object carrying id/environment_id/output_text.
    print("→ streaming agent steps (this can take many minutes):\n")
    for raw in resp:
        line = raw.decode(errors="replace").strip()
        if not line or line == "data: [DONE]":
            continue
        payload = line[6:] if line.startswith("data: ") else line
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            print("   ", line[:200])
            continue
        interaction_id = obj.get("id", interaction_id)
        environment_id = obj.get("environment_id", environment_id)
        # surface reasoning / tool / text deltas if present
        for k in ("output_text", "text", "reasoning", "step", "tool"):
            if k in obj:
                print(f"   [{k}] {str(obj[k])[:300]}")
        if obj.get("output_text"):
            print("\n=== agent final reply ===\n", obj["output_text"])

    print(f"\n→ interaction_id={interaction_id}  environment_id={environment_id}")
    if not environment_id:
        print("✗ no environment_id captured -- check the live response shape and "
              "adjust the parser. Nothing to download.")
        sys.exit(1)

    # save the IDs so a follow-up turn / re-pull is trivial
    (HERE / "last-run.json").write_text(json.dumps(
        {"interaction_id": interaction_id, "environment_id": environment_id,
         "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=2))

    # download the whole sandbox as a tar
    out_tar = HERE / "pulled" / f"env-{environment_id}.tar"
    out_tar.parent.mkdir(exist_ok=True)
    dl = f"{BASE}/files/environment-{environment_id}:download?alt=media"
    print(f"→ downloading sandbox tar → {out_tar}")
    req = urllib.request.Request(dl, headers={"x-goog-api-key": key,
                                              "Api-Revision": API_REVISION})
    with urllib.request.urlopen(req, timeout=900) as r, open(out_tar, "wb") as f:
        f.write(r.read())
    print(f"✓ saved {out_tar.stat().st_size} bytes")
    print("\nNext: extract the tar, find output/killen-time.mp3, give it a listen,"
          "\nthen publish with:  python3 ../publish.py <path-to-mp3> "
          "--title \"<from show-notes.md>\"")


if __name__ == "__main__":
    main()
