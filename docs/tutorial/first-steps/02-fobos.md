---
title: 2. A fobos file
---

# 2. A fobos file

Command-line options are fine for one build; a project needs several (a debug build with run-time checks, an
optimised one) and should not depend on remembering their flags. The **fobos** file, in the project's root, holds
them as named **modes**:

<<< @/examples/tutorial/1-first-steps/02-fobos/files/fobos{ini}

- `[modes]` lists the modes; the first one is the default.
- A mode's keys are the long options of `fobis build` without the dashes: `compiler`, `cflags`, `src`, `build_dir`,
  `target`... Every option is documented in the [build reference](/reference/build).
- `target` names the program to build: only it and what it depends on are compiled.
- `help` describes the mode in the list:

<<< @/examples/output/1-first-steps/02/lmodes.txt{console}

## Building a mode

Without `--mode`, the default mode:

<<< @/examples/output/1-first-steps/02/debug.txt{console}

<<< @/examples/output/1-first-steps/02/release.txt{console}

Each mode builds in its own directory, so switching from one to the other never recompiles the other's objects:

<<< @/examples/output/1-first-steps/02/tree.txt{console}

![fobis build with a fobos, in the default mode and in release](/gifs/02_fobos_build.gif)

*Recorded on a small demo project, not quad.*

## Running

`fobis run` builds the mode's target when needed, then runs it:

<<< @/examples/output/1-first-steps/02/run.txt{console}

Arguments after the options go to the program: `fobis run --mode release -- ARG...`.

## Cleaning a mode

Now that the mode names its target, `fobis clean` removes the executable too:

<<< @/examples/output/1-first-steps/02/clean.txt{console}

::: tip What you learned
A fobos file with modes; `--mode`, `--lmodes`; per-mode build directories; `fobis run`. Reference: [the fobos
file](/fobos/), [`run`](/reference/run).
:::

Next: [3. A library](./03-library).
