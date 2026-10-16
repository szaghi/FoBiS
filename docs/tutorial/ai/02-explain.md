---
title: 2. Build failures, explained
---

# 2. Build failures, explained

A misspelt module name in `integrate.F90` (`quad_rule` for `quad_rules`):

<<< @/examples/output/6-ai/02/missing.txt{console}

`--explain` needed no model here. FoBiS knows the project's modules and the fetched dependencies, so a missing
module is diagnosed from facts: defined nowhere, defined in a file the mode does not compile, hidden by a
preprocessor branch, part of an unfetched dependency, or, as here, a close name of an existing one.

## When facts are not enough

An integer passed where `trapezoid` expects a `real(R8P)`: the compiler names the argument, but not why the code
is wrong. `--explain-context` prints what the model would receive, and runs no model:

::: details The model's input (`fobis build --explain-context`)
<<< @/examples/output/6-ai/02/context.txt{console}
:::

The compiler's message, the build, and numbered sources: the lines around the error, the declarations of the
enclosing program, and the interface of `trapezoid`, found by FoBiS because the failing line calls it. The
answer:

<<< @/examples/output/6-ai/02/explain.measured.txt{console}

Every statement cites the sources it rests on, and a statement citing none is dropped before you see it. The
model answers in a fixed JSON form whose citations can only be the labels it was given, so it cannot cite a
source that does not exist.

![fobis build --explain and fobis ask with coder-7b, run locally on the CPU](/gifs/13_llm_explain.gif)

*coder-7b on 6 CPU cores and no GPU; each answer takes about 45 s there, cut from the recording.*

::: tip What you learned
`--explain` on `build`, the deterministic diagnoses, `--explain-context`, cited answers. Reference:
[explaining failures](/cookbook/ai#why-the-build-failed).
:::

Next: [3. Crashes, located](./03-crash).
