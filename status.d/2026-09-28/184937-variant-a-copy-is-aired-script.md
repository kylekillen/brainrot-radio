### 2026-09-28 12:49 — New Hire test "variant-A-copy" is byte-identical to the aired 09-28 script
`wt/brainrot-single-pass/test-runs/2026-09-28-variant-A-copy.txt` cmp-matches `scripts/killen-time-2026-09-28.txt`, so QC of it also QCs the aired episode; its dedup check must exclude the 09-28 ledger entry (self-reference), and any MUST-FIX found is a defect that already shipped.
