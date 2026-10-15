---
title: 1. A first build
---

# 1. A first build

## Starting from scratch

`fobis new` writes a project that builds and tests at once: a module, a program, a test, a fobos with a debug and a
release mode, a `.gitignore` and a git repository (nothing committed). It never overwrites a file.

<<< @/examples/output/1-first-steps/01/new.txt{console}

<<< @/examples/output/1-first-steps/01/newtree.txt{console}

<<< @/examples/output/1-first-steps/01/newbuild.txt{console}

`--lib` makes a library (no program, static and shared library modes), `fobis new .` fills the current directory,
`--scaffold` adds CI, documentation and release scripts. Reference: [`new`](/reference/new).

The rest of this track builds `quad`, a project written by hand, to show what FoBiS does with no configuration and
how a fobos grows from there.

## The quad project

`quad` is a small library of quadrature rules, and a program that uses it. It has no build script: FoBiS reads the
sources and works out the rest.

<<< @/examples/output/1-first-steps/01/tree.txt{console}

::: code-group

<<< @/examples/tutorial/1-first-steps/01-first-build/files/src/quad_rules.F90{fortran} [quad_rules.F90]

<<< @/examples/tutorial/1-first-steps/01-first-build/files/src/integrands.F90{fortran} [integrands.F90]

<<< @/examples/tutorial/1-first-steps/01-first-build/files/src/integrate.F90{fortran} [integrate.F90]

:::

The program uses two modules, and `integrands` uses `quad_rules`: that order must be respected by whatever
compiles them, because a module has to be compiled before the files that use it.

## Building

<<< @/examples/output/1-first-steps/01/build.txt{console}

- With no configuration, FoBiS looks for the conventional source directories (`src/`, then `source/`, then `app/`)
  and scans the first one it finds; without any of them it scans the current directory.
- **Builder options** is the configuration in use: the default compiler (`gnu`, that is `gfortran`), flags, and where
  objects (`obj/`) and module files (`mod/`) go.
- Every program found is a target. FoBiS parsed each file for `module`, `use`, `include` and `program` statements
  and compiled `quad_rules`, then `integrands`, then the program, whatever the file names.

The build left the objects, the module files and the executable, named after the program's file:

<<< @/examples/output/1-first-steps/01/after.txt{console}

`obj/.fobis-compiler.json` records which compiler built the objects: when it changes (another `gfortran` after a
`module load`, for example), the next build recompiles everything instead of mixing objects of two compilers.

<<< @/examples/output/1-first-steps/01/run.txt{console}

Both errors fall as the number of intervals grows; how fast is the subject of a test in chapter 4.

## Rebuilding

FoBiS compiles only what is out of date. Run again, nothing is compiled:

<<< @/examples/output/1-first-steps/01/rebuild.txt{console}

Change `quad_rules.F90` (here `touch` stands for an edit) and everything that depends on it is recompiled, through
the chain of `use` statements; `--quiet` drops the options block:

<<< @/examples/output/1-first-steps/01/touch.txt{console}

## Cleaning

<<< @/examples/output/1-first-steps/01/clean.txt{console}

`fobis clean` removes objects and module files. The executable stays: with no target named, FoBiS does not know which
file it built (the next chapter names one).

::: tip What you learned
`fobis build` with no configuration: source discovery, dependency order from `use` statements, incremental
rebuilds, `fobis clean`. Reference: [`build`](/reference/build), [`clean`](/reference/clean).
:::

Next: [2. A fobos file](./02-fobos).
