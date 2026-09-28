### 2026-09-28 17:30 — New Hire test harness set up

I-8 work includes a comparison: single-pass ~3,500 words vs current two-pass ~6,000 words on same-day sources.

**Infrastructure created:**
- `bin/test-single-pass.py` — test harness for running variants and capturing metrics
- `test-runs/` directory — holds manual episode tests (not published to feed)
- Test protocol: ingest → single-pass write → audio render → compare vs two-pass

**Metrics to track:**
- Word count, segment structure
- Token usage (ingest through render)
- Quality signals (sourcing, coherence, edits needed)
- Time to render

**Current status:** Harness ready. Test requires manual run on a chosen date with sufficient source material. Recommend running alongside a normal episode day to control variables (same ingest, trending, etc.).

**Next steps:**
1. Choose a test date (tomorrow or next episode day with normal source volume)
2. Run `python3 bin/test-single-pass.py --date YYYY-MM-DD --run-both`
3. Generate single-pass variant using custom prompt targeting ~3,500 words
4. Compare metrics with current two-pass episode
5. Log findings (quality trade-offs, token savings, segment retention)

A 1-pass variant could serve as a "New Hire" fallback for days when human editorial time is constrained, or as a baseline for further optimization (Gemini Flash, effort tiering on Claude, etc.).
