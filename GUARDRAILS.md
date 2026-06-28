# GUARDRAILS — brainrot-radio (podcast pipeline)

*Behavioral invariants any worker on this repo must not violate — distinct from
task goals. An episode can render successfully and still break one of these.
Before calling a task done, review each row; if a NEW failure class appears, add
a row with the invariant, rationale, and date. Seeded 2026-06-28 from the daily
build pitch (Encoded Guardrail Documents, Latent Space "Extreme Harness
Engineering") + this pipeline's documented failures. Reversible: delete this file.*

| Invariant | Rationale | Added |
|---|---|---|
| Never include internal fleet state (STATUS.md, HANDOFF.md, calibration.md, INBOX contents) in a public audio script or episode file. | Build-pitch reporter loaded internal STATUS into a public audio segment, 2026-06-25. | 2026-06-28 |
| Audio must receive QC `VERDICT: PASS` before the render step runs. Abort on FAIL or UNCERTAIN; never publish a QC-FAIL episode. | Episodes shipped FLAGGED sub-par (06-23/24/25/27 qc-FAIL flags); QC is "MANDATORY" in CLAUDE.md. | 2026-06-28 |
| Report / family deliveries route only to the PRIVATE feed (publish_private.py / render_report.py private target), never the world-public killen-time-podcast feed. | render_report.py once published private/family reports to the public feed. | 2026-06-28 |
| Beat reporters must pull full source articles/transcripts — never write a segment from RSS summaries alone. | Established editorial rule (CLAUDE.md). | 2026-06-28 |
| Any repo that runs from its working-tree checkout (this one) must be verified synced to main after a PR merges — merged ≠ deployed. | Recurring deploy-gap class across the fleet. | 2026-06-28 |
