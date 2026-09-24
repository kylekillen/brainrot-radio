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
| The router-pilot writer (router_writer.py) must assert its assembled prompt is free of internal fleet-state markers (STATUS.md, HANDOFF.md, calibration.md, INBOX.md, credentials/tokens) before dispatching to ANY router-picked model, since `sensitive=False` for `podcast_segment` permits a `trains_on_data` provider. | Extends the row above's guardrail to a new dispatch path (an external model, not just the audio file itself); Kyle ruled 2026-09-02 that trains_on_data models are fine for PUBLIC content only. | 2026-09-03 |
| Never put Kyle's PRIVATE system on air: no internal repo/role/launchd-job names, no internal file paths or config keys, and no uncited counts of his own launch sites, workers, credit balance or spend. Public audio explains the vendor's technique in general terms. The Build-Pitch writer prompt and the QC Coherence Skeptic enforce this; `tests/test_no_private_system_on_air.py` locks it. | The 09-24 Build-Pitch segment read the pitch's "local check" aloud ("observer-system had twenty-seven places that launch Claude … only eight pass an effort level"); measured at that day's commit it was 48 and 9. The number was wrong AND the setup should never have been public — an uncited count about the listener's private system both leaks it and goes stale. | 2026-09-24 |
