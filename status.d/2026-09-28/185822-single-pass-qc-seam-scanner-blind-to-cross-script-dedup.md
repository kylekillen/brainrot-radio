### 2026-09-28 12:58 — single-pass New Hire test's seam scanner is blind to cross-script dedup

QC'ing `test-runs/2026-09-28-single-pass.txt` (variant B of the single-pass vs
two-pass New Hire test) found it duplicates most of the content already aired
that same day in `scripts/killen-time-2026-09-28.txt` — same Nvidia Open Agent
Safety item, same Alexandr Wang/Muse quote, same MIT Tech Review liability
piece, same Red Queen Bio, same DAWO, same Engram, same Cloudflare/Prince
segment, same Build Pitch of the Day (effort dial), same Bill
Simmons/Fantasy-Football/Nets sports block. `bin/test-single-pass.py --stage
scan` reported variant B as only 1 defect (a private-system leak on line 31)
— it never flags this, because the seam scanner only pattern-matches within a
single script (speaker collisions, back-to-back transitions, private-system
strings); it has no cross-check against `scripts/.covered-*.json` or the
aired 09-28 script. If the New Hire test's PASS criteria lean on "0 seam
defects" as a quality signal, that signal says nothing about dedup — a
variant that re-airs 90% of the day's already-published content would still
score 0 defects. Worth knowing before trusting the seam-scan number alone in
future single-pass/two-pass comparisons.
