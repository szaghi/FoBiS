---
title: AI assistance
---

# AI assistance

## Set up a local model

```bash
fobis llm recommended
fobis llm runtime install
fobis llm pull coder-7b
fobis llm doctor
fobis llm serve start         # optional: one server for many commands
```

The model runs on your machine through llama.cpp; nothing leaves it. Tutorial: [a local model](/tutorial/ai/01-model).
Guide: [local models](/ai/models).

## On a cluster without internet

Pull the runtime and the model where there is network, copy `~/.fobis/llm` (relocatable) and `fobis.pyz`, then run
inside a GPU job:

```bash
python3 fobis.pyz llm serve start
python3 fobis.pyz build --explain
```

On a cluster whose C library is older than the pinned llama.cpp binaries need (glibc 2.38), build llama.cpp
there and point `runtime` in the `[llm]` section of the user configuration at its `llama-server`. Guide:
[the managed runtime](/ai/runtime).

## Explain a failed build or run

```bash
fobis build --explain
fobis build --explain-context    # what the model would receive; no model
fobis run --explain
fobis test --explain
```

Facts first (a missing module, an undefined symbol, a located crash); the model only for what the facts leave, with
cited sources. Tutorial: [build failures](/tutorial/ai/02-explain), [crashes](/tutorial/ai/03-crash).

## Ask about the code or the standards

```bash
fobis ask "is a loop variable private in an OpenMP parallel do?"
fobis ask -p src "which procedures write the solution array?"
fobis ask --show-context -p src "..."
```

Tutorial: [questions about the code](/tutorial/ai/04-ask).

## Generate a test

```bash
fobis testgen mymodule --skeleton    # no model: a compiled skeleton
fobis testgen mymodule --apply       # a model fills it; kept only if it builds, runs and checks
```

Tutorial: [generated tests](/tutorial/ai/05-testgen).

## A second reading of a change

```bash
fobis review --deep
fobis lint --deep --select OMP,ACC,MPI
```

Tutorial: [a second reader](/tutorial/ai/06-review).

## Commit messages

```bash
git add -p
fobis commit --show-facts
fobis commit --apply
```

Tutorial: [commit messages](/tutorial/ai/07-commit).

## Merge conflicts

```bash
fobis merge-assist --no-model   # deterministic resolutions only
fobis merge-assist              # proposals compiled before they are shown
fobis merge-assist --apply      # hunk by hunk
```

Tutorial: [merge conflicts](/tutorial/ai/08-merge).

## Let an agent use FoBiS

```bash
claude mcp add fobis -- fobis mcp
fobis agents-md
```

Tutorial: [an agent under the gate](/tutorial/ai/09-agent). Guide: [MCP server](/ai/mcp).
