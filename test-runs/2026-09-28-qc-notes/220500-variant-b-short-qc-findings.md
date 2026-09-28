# QC findings — New Hire test, variant B-short (report only, script untouched)

Script: `.../worktrees/sonnet-onepass/test-runs/2026-09-28-variant-B-copy-short.txt` (3,168 words). Day of week Monday: correct.
QC VERDICT: FAIL

## MUST-FIX
1. L61 Build Pitch: "logged in the build-pitches folder ... so Kyle can point an agent at it and greenlight the build" — leaks private system (GUARDRAILS rows 1/7). Flagged by B and C.
2. L53-59 Build Pitch repeats 09-24 pitch (`build-pitch-opus55-effort-default-2026-09-24`, aired 09-24 L85). Duplicated story, no callback. (A)
3. L87 Economist "house prices survived the last round of rate rises" — already aired 09-24 (L183, ledger slug `economist-housing-vulnerable-to-higher-rates-2026-09-24`). (A, C)
4. L1 "half of AI Twitter is furious about it" — no source; Zvi never says it. (B, C)
5. L97 "a German election has the chancellor calling the results a disaster" — from a week-old blurb, mischaracterised, unsourced in brief. (B, C)
6. L67 Simmons/Cousin Sal: "undefeated", "most preseason lists didn't see coming", "bleakest 0-3 teams", "Dallas... disaster", "standings already strange" — specifics on "(no transcript)" items. (C)
7. L75 Call of the Wild: "public-domain title, rights conversation is easy... path of least resistance for the first wave" — Deadline blurb truncated, nothing on rights/why chosen; speculation as fact. (C)
8. L77 Engram: "treats the model's breakage as a texture, which is how a lot of good instruments get invented" — blurb truncated after "not a push-button device". (C)
9. L15 Threads/Muse: "reality check ... fair summary of where personal agents are. Fast adoption, unearned trust" — brief has only the title. (C)
10. L71 -> L75 BROOKE / [TRANSITION] / BROOKE: consecutive same-speaker blocks across the join (L77 is BASIL, so flip pair or merge). (B; verified by me)

## ADVISORY
- Harness note: Moonshots, Innermost Loop, Zvi-Quest, full Odd Lots, deBoer, Economist listing texts are in `.tmp/used/` but NOT in `single-pass-sources.json`. Every checked quote/number matched those files, but the manifest doesn't show the writer was given them; fix the manifest if they were.
- L41 "For us ... the same pipeline that ships the work", L45 "Count ... episodes ... a lot of us", L43/L47/L67 "the transcript we have / we haven't pulled / we don't have transcripts" — first-person pipeline talk; mild leak of setup.
- Innermost Loop incident recap (L17, L27) restates 09-22/24/26 facts (DNS "phoned a friend", pause, HF swarm); only 80k payloads/LOOT folder/German wiki are new. Add callback or trim.
- L47 "Prompting Claude Opus 5.5" near-overlaps 09-24 playbook coverage; script admits it hasn't read it.
- L3 "fight over whether superintelligence is a rebrand" overstates Moonshots; panelist attribution by inference (no speaker labels); insurance-stocks 15% was for stocks incl. one the speaker chairs; "seemed to like" is from a URL slug; L31 Nvidia "bet behind" motive and DNS/HF conflation are inference; L37 "more incidents went undisclosed" slight embellishment; L79 Swift "record" unspecified; closing thesis is writer's own.
- L1 opening callback is supportable (sandbox-escape stories aired 09-20..09-27); "who gets to stand inside the box" is rhetoric.
- L1 "This is the Killen Time Update..." differs slightly from convention ("The Killen Time Update for...").
- Verified clean: Moonshots quotes, Zvi/Quest specifics, Build Pitch figures vs build-pitches.md, Cloudflare, DAWO, Citrix, Red Queen, Norris/Colapinto, Assassin(s), deBoer, Odd Lots. Moonshots, Zvi-Quest, Muse numbers, Norris fallout are fresh (not in 09-22..09-27).
