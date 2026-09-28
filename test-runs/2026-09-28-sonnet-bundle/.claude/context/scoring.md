# Scoring Algorithm (ingest.py)

`score = recency × feed_weight × topic_weight × keyword_boost`

- **Recency:** exponential decay, 6-hour half-life.
- **Feed weights:** per-feed in `feeds.json` (Event Horizon 3.0, Techmeme 2.0, …).
- **Topic weights:** agentic_systems=2.5, ai_and_tech=2.0, economics=1.5, …,
  prediction_markets=1.0 (demoted 2026-06-09).
- **Keyword boosts:** Claude Code / agent harness / subagents / multi-agent /
  context engineering (~1.25-1.3); prediction-market terms dropped to 1.0 (no
  longer boosted).
- **Dedup:** >40% title word overlap → merge (keep higher score).
- **Topic diversity:** at least 1 story per active topic guaranteed in the brief.
- **Age labels:** today / yesterday / this week / older — articles >48h marked
  NOT BREAKING.
