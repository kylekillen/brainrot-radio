# Killen Time

The charter for this project is `CLAUDE.md` in this directory. It applies to
every model that runs this repo, whatever its provider. Read it in full before
doing anything.

This file used to be a hand-made copy of `CLAUDE.md`. It was added on
2026-09-28 (commit `810b01b`) and was byte-for-byte identical to the charter
except for three lines, where a Claude→Codex find-and-replace had rewritten:

- `.claude/commands/` → `.Codex/commands/`
- `.claude/context/` → `.Codex/context/`
- "a Claude Code session" → "a Codex session"

Both `.Codex/` paths have never existed in this repo — the directories are
`.claude/commands/` and `.claude/context/` — so the file pointed every reader
at two directories that were not there. It was replaced with this pointer on
2026-10-06.

Do not restore a copy; one charter cannot contradict itself, and a copy is how
this one came to name directories that do not exist.

Prior art, both from this fleet:

- `scripts/.covered-2026-09-19.json`, this repo's own harvested news: "Claude
  Code 2.1.277 checks AGENTS.md when no CLAUDE.md; **CLAUDE.md wins if both**;
  advice: one canonical instruction file per repo, avoid drift."
- `~/model-router/AGENTS.md`, collapsed to this same pointer shape on
  2026-10-03 for the same reason.
