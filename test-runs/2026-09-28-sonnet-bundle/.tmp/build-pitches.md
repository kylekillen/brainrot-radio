**Build-Pitch of the Day: stop running every fleet worker at default effort.**

Claude now has an `effort` dial (low through max), and Anthropic's own docs say to sweep it per workload and use a "run cheap first, re-run failures harder" ladder. On Opus 5.5, which launched last week at $4/$20 per million tokens, their measured numbers on coding tasks: medium effort costs about 70% of high for roughly 2.5 points less accuracy, and low costs about a third. Their low-first-then-escalate ladder hit about 97% pass at 17 cents a task versus 95.3% at 29 cents running everything high. Anthropic also claims Opus 5.5 at low effort beats Sonnet 5 at default per solved task.

Who's saying it: Anthropic's "optimizing for cost and intelligence" docs, Matthew Berman's Opus 5.5 launch stream with an Anthropic Claude Code lead (medium effort under a dollar a task outscoring max effort at over five), and independent Artificial Analysis data: Opus 5.5 index scores of 42 at low, 51 at medium, 58 at max, with cost per task running from 55 cents to almost six dollars. An arXiv paper this month makes the same point: judge agents on cost per successful task, because more effort sometimes just adds cost.

Why it's real for us, and the honest caveats: those benchmarks are vendor-run, cover Opus 5.5 and Fable rather than Sonnet 5, and measure SWE-bench-style coding, not our biggest lane, PR review. So it's a strong hypothesis, not a proven saving.

Why it fits us: the task database shows about $1,380 of tracked cost in 14 days, roughly 54% on Sonnet-family workers, about 900 PR-review tasks, and Sonnet-authored PRs averaging 1.47 review cycles. The dispatched-worker runner passes a model but never an effort level, and no optimizer slate item covers it. This is different from last week's rejected multi-provider idea: it tunes spend inside the Anthropic pool.

How it'd upgrade our setup: record effort per task, run a shadow bake-off of Sonnet 5 default, Sonnet 5 medium, Opus 5.5 low and Opus 5.5 medium on about 50 tasks each, scored by cost per landed PR, then set the winning default and a low-first escalation ladder in the sweeper. It's a config change, not a new system.

Dropped as already covered: the Opus 5.5 silent safety-fallback, Jev, and the doctor prompt-audit.

Logged in build-pitches/2026-09-28.md for Kyle to greenlight.
