---
title: 5. Rules
---

# 5. Rules

A project has chores besides building: running the program, packing a release, generating the documentation. A
**rule** is a named list of shell commands in the fobos, run by `fobis rule --execute NAME`:

```ini
[rule-smoke]
help = The last line of the program's output
rule = ./build/release/integrate | tail -n 1

[rule-errors]
help = The table of errors, from the release build
rule = fobis run --mode release

[rule-dist]
help     = A source archive
rule_rm  = rm -f quad-0.1.0.tar.gz
rule_tar = tar czf quad-0.1.0.tar.gz fobos src test
```

Every key starting with `rule` is a command, run in the order written (the keys of a section must differ:
`rule_rm`, `rule_tar`).

<<< @/examples/output/2-growing/05/list.txt{console}

<<< @/examples/output/2-growing/05/dist.txt{console}

## Hooks

A mode can run rules before and after its build: `pre_build = NAMES`, `post_build = NAMES` (after a successful build
only). The release mode now runs `smoke`, so every release build ends by running the program:

```ini
[release]
help          = Optimised
template      = template-gnu
build_profile = release
cflags        = -c
post_build    = smoke
```

<<< @/examples/output/2-growing/05/release.txt{console}

## Intrinsic rules

FoBiS has a few rules of its own: `--ford PROJECT` builds the documentation with FORD, `--gcov-analyzer` summarises
gcov files, and three questions about the compiler:

<<< @/examples/output/2-growing/05/float128.txt{console}

(`--is-ascii-kind-supported` and `--is-ucs4-kind-supported` ask about character kinds.)

## Parallel compiling

Not a rule, but a chore that grows with the project: `--jobs N` compiles independent files at the same time. Files of
the same level of the dependency tree are compiled together:

<<< @/examples/output/2-growing/05/jobs.txt{console}

::: tip What you learned
`[rule-NAME]`, `fobis rule --list` and `--execute`, `pre_build`/`post_build` hooks, intrinsic rules,
`--jobs`. Reference: [rules](/cookbook/libraries#run-project-commands-as-rules), [intrinsic rules](/cookbook/libraries#ask-the-fobos-from-a-script), [`rule`](/reference/rule).
:::

Next: [6. Continuous integration](./06-ci).
