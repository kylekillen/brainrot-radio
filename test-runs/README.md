# test-runs

Manual episode-format experiments. **Nothing here is ever rendered, mixed or
published** — these are script + metrics only, and the harness refuses any
TTS/publish path.

| file | what |
|---|---|
| `YYYY-MM-DD-single-pass.md` | the New Hire test report (protocol, criteria, numbers, verdict) |
| `YYYY-MM-DD-single-pass-metrics.json` | machine-readable: words, tokens, QC verdicts, seam hits, judge scores |
| `YYYY-MM-DD-single-pass-sources.json` | sha256 + size of every source file the variants were written from |

Harness: `bin/test-single-pass.py` (see `--help`).
