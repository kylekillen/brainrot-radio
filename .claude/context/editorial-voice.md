# Editorial Voice & Sourcing

**Show target: 60 minutes (~14,000-18,000 words). Cover everything — at minimum,
hit highlights of every story.**

## Voice
This is a conversation, not a news ticker. Hosts should:
- Dig deeper into implications, offer counterpoints.
- Be opinionated but grounded — editorial must be rooted in source material.
  "Here's what this means" = good. "Here's what I imagine despite no evidence" = bad.
- Connect stories only when the connection is genuinely there — same company,
  same regulation, direct cause and effect. Don't force connections between
  unrelated stories. One good connection per episode is plenty; don't repeat the
  same linking move multiple times.
- The outro can briefly recap and highlight the most interesting thread, but keep
  it short — don't weave every story into a single thesis. A quick sign-off beats
  a forced synthesis.
- **Include at least one direct quote per segment** from a podcast transcript,
  article, or stream.

**General principle:** Don't reach for easy/shallow framing when a more informed,
more interesting perspective exists. The audience has deep domain knowledge.
Engage at that level.

## Topic diversity
Every episode should touch at least 4 different topic areas. The per-beat
guidelines live in `.claude/context/beats/`.

## Podcasts and Substacks are the backbone
Generic RSS news feeds (Techmeme, TechCrunch, Verge) provide awareness, but DEPTH
comes from podcast transcripts and Substack essays.
- **Lead with podcast/Substack material.** If you have a transcript discussing a
  topic AND a news headline about it, build the segment around the podcast
  discussion (quotes, arguments, analysis) and use the headline as context.
- **Allocate at least 60% of episode time to podcast and Substack content.** News
  headlines get brief mentions unless there's no podcast/Substack coverage.
- **Every podcast transcript you received should be covered.** If a transcript was
  provided, it scored high enough — give it airtime. Extract the interesting
  arguments and quotes; don't mention it in passing.

**Substack deep coverage:** Full articles from 25+ Substacks are saved to
`.tmp/articles/` — the richest material (Zvi's AI roundups, Dean Ball's policy
analysis, Noah Smith on economics). When an article shows `Type: substack (full
text, N words)` in the brief, read the full article and integrate key insights and
quotes. Listeners get the takeaways without reading 10,000+ word posts.

**Signal detection:** When the same story appears across multiple high-weight
feeds AND is getting discussion on X (Techmeme cross-references, HN comment
counts), that's a signal to FEATURE it, not just mention it. High engagement
across circles Kyle follows = lead segment material.

## Time-of-day awareness
The episode prompt includes a TIME OF DAY line (morning/afternoon/evening). Use
the matching greeting ("good morning" / "good afternoon" / "good evening"). NEVER
say "tonight's episode" for a morning show or "this morning's episode" for an
evening show.
