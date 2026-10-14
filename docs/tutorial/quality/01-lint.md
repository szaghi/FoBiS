---
title: 1. The linter
---

# 1. The linter

`quad` gets an old neighbour: a Romberg integrator in fixed-form FORTRAN 77, the kind of file every long-lived code
has somewhere, with a test that pins its result:

::: code-group

<<< @/examples/tutorial/4-quality/01-lint/files/src/romberg.f{f77} [src/romberg.f]

<<< @/examples/tutorial/4-quality/01-lint/files/test/test_romberg.F90{fortran} [test/test_romberg.F90]

:::

<<< @/examples/output/4-quality/01/test.txt{console}

From this track on `quad` is a git repository (`git init`, one commit): the review of chapter 3 needs one.

## Linting

`fobis lint` checks the sources of a mode (the default one here), with its `-D` defines: an `#ifdef` branch the
build does not compile is not checked either.

<<< @/examples/output/4-quality/01/lint.txt{console}

Every finding names a rule. The first two are about the code of the previous tracks: `use mpi` imports every name of
the MPI module, and the abstract interface of `quad_rules` has no `implicit none`. The rest is the legacy file.
`--explain` says why a rule exists, and what to write instead:

<<< @/examples/output/4-quality/01/explain.txt{console}

The references point to the [knowledge packs](/ai/knowledge-packs), searchable with `fobis kb`.

## Choosing the rules

`--select` and `--ignore` take rule ids or prefixes (`OBS`, obsolescent; `MDN`, modernisation; `COR`,
correctness; `OMP`, `ACC`, `MPI`, parallel code; ...). Selecting a family explicitly also turns on its opt-in
rules, the ones whose findings are matters of style or project policy:

<<< @/examples/output/4-quality/01/select.txt{console}

The [rule reference](/lint-rules/) lists them all; a fobos `[lint]` section sets a project's selection once.

## For CI

`--format github` writes GitHub Actions annotations (shown on the pull request's lines), `sarif` the format of
GitHub code scanning, `json` a document for scripts:

<<< @/examples/output/4-quality/01/github.txt{console}

The exit status is 1 when anything is found (`--exit-zero` keeps it 0).

::: tip What you learned
`fobis lint`, `--explain`, `--select`/`--ignore`, the output formats. Reference: [`lint`](/reference/lint),
[rules](/lint-rules/).
:::

Next: [2. Suppressions, baselines and fixes](./02-fixes).
