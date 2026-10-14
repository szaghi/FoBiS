---
title: 2. Suppressions, baselines and fixes
---

# 2. Suppressions, baselines and fixes

Three ways to deal with a finding, besides fixing the code by hand.

## Fixing by hand

The abstract interface gets its `implicit none` (an interface body is a separate scoping unit: it does not inherit
the module's):

```fortran
abstract interface
   pure function integrand(x) result(y)
   !< A function of one real variable.
   import :: R8P
   implicit none
```

## Suppressing one finding, with a reason

`use mpi` stays as it is: the module's names all start with `mpi_`, so importing them all hides nothing. An inline
comment says so, and silences that rule on that line only:

```fortran
use mpi ! fobis: ignore[COR040] the mpi module's names are all prefixed mpi_
```

<<< @/examples/output/4-quality/02/lint.txt{console}

A suppression without a reason, or one that suppresses nothing, is itself reported.

## Automatic fixes

Some rules know their fix. `--diff` shows them, `--fix` applies them:

<<< @/examples/output/4-quality/02/diff.txt{console}

Labelled `DO` loops become block loops (`DO 30` too, although a `GOTO` jumps out of it: the label it jumps to is
another one), `DABS` becomes `ABS`, `.LT.` becomes `<`. Chapter 5 applies them only after the tests confirmed
them.

## A baseline for the rest

An old file can have more findings than anyone will fix this week. A **baseline** records the current ones; from then
on only new findings are reported, so the linter can run in CI today:

<<< @/examples/output/4-quality/02/baseline.txt{console}

<<< @/examples/output/4-quality/02/clean.txt{console}

A finding is recorded by its rule, file and the text of its statement, not by its line: code added above it does not
bring it back. `.fobis-lint-baseline.json` is read by default; commit it.

::: tip What you learned
Inline suppressions with a reason, `--diff`/`--fix`, `--update-baseline`. Reference: [linting](/ai/lint).
:::

Next: [3. Reviewing a change](./03-review).
