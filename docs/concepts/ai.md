# The AI design

The AI commands of FoBiS follow one rule: **the model is the last step, never the first**. FoBiS states
the facts it can establish itself, gives the model only what it may use, and checks the answer before showing
it. The [AI-assisted development track](/tutorial/ai/01-model) shows each command on a real project; this page
is the design they share.

## Facts first

Before any model runs, a deterministic step does what it can:

- `build --explain` diagnoses a missing module, an unlinked object, a library missing at link time, objects of
  another compiler, an internal compiler error;
- `run --explain` and `test --explain` locate the crash, and say when a backtrace of an optimised build cannot be
  trusted;
- `review` and `lint` find what their rules find; `commit` lists the changed procedures and the scopes the history
  uses; `merge-assist` resolves the hunks that need no judgement (one side unchanged, `use` lists, version pins).

Often that is the whole answer, and no model is started. The model is asked only about what is left, and its
answer is printed apart from the facts.

## A context you can read

What the model sees is assembled by FoBiS, not searched for by the model: the error and the code around it, the
declarations and interfaces it names, the build mode and its flags, a few sections of the
[knowledge packs](/ai/knowledge-packs). The same inputs give the same context, and `--show-context` (or
`--explain-context`, `--deep-context`) prints it without running a model.

## Cited claims, checked

The answer is a JSON object of claims, each citing the sources of the context by label (`S1`, `S2`, ...). The
schema lists the labels as an enumeration, so a model run with a grammar cannot invent one; FoBiS still checks
every citation, drops the claims citing nothing it gave, and says how many it dropped. When nothing survives, the
answer is "the sources do not answer this".

A citation proves that the source exists and was given to the model, **not** that it supports the claim. Read
the cited source when the claim matters.

## Outputs that can be checked are checked

Where a tool can judge the model's output, it does, and the output is kept only when it passes:

| Command | The model proposes | Kept when |
|---|---|---|
| `testgen` | a test program | it builds, runs, passes and checks something |
| `merge-assist` | a resolution of a conflict | the file compiles (else it is shown with low confidence) |
| `lint --deep` | a verdict on a finding | it cites the code or a rule (else it is marked uncertain) |
| `commit` | a message | its scope is one the facts allow |

The exit status of `lint` and `review` never depends on a model's verdict.

## Local, explicit, bounded

- The default provider is a model run on your machine by FoBiS itself: a pinned llama.cpp build and pinned models,
  checked against their checksums. Nothing is downloaded implicitly: `fobis llm runtime install` and
  `fobis llm pull` do it, when you ask. Another server (Ollama, any OpenAI-compatible endpoint) is a configuration
  line; its API key is read only from an environment variable you name.
- Every answer has bounded lengths and a token cap, so a small model that starts repeating itself stops early
  instead of filling its context.
- The model never writes to your files or to git by itself: proposals are applied only with `--apply` (and, for
  merges, after you accept them).

## For agents: facts, not answers

`fobis mcp` serves the same deterministic facts to an AI agent (lint findings, build diagnoses, test results,
knowledge-pack sections, the verification gate) and never the local model's answers: the agent is a model itself
and does its own reasoning on facts it can cite. See [an agent under the gate](/tutorial/ai/09-agent).

## Further reading

- [Analysis & AI overview](/ai/), [knowledge packs](/ai/knowledge-packs), [local models](/ai/models)
- [AI recipes](/cookbook/ai)
