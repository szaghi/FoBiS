---
title: 7. Instructions for agents
---

# 7. Instructions for agents

A coding agent (Claude Code, Codex, Copilot...) reads an `AGENTS.md` (or `CLAUDE.md`) to learn how to build and
check a project. Written by hand, it goes stale with the first new mode. `fobis agents-md` writes it from the facts:
the fobos modes with their flags, the commands, the tests, the code's kinds and parallelism.

<<< @/examples/output/4-quality/07/print.txt{console}

`fobis agents-md` writes the block into `AGENTS.md` (`-o CLAUDE.md` for another file), between the markers: text
around them is yours and is kept. `fobis agents-md --check` exits 1 when the block is stale, for CI. The content is
deterministic: no dates, no machine state.

::: tip What you learned
`fobis agents-md`, `--print`, `-o`, `--check`. Reference: [instructions for agents](/cookbook/ai-setup#agents-md-and-claude-md-from-facts).
:::

This is the end of the fourth track. The [fifth](../#tracks) asks the question the linter cannot answer: are the
results right?
