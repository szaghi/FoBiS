---
title: Code analysis
---

# Code analysis

## Lint in CI

```bash
fobis lint --format github     # annotations on the pull request
fobis lint --format sarif > lint.sarif
```

```ini
[lint]
; rules or families never reported
ignore = STY
```

Tutorial: [the linter](/tutorial/quality/01-lint). Rules: [lint rules](/lint-rules/).

## Adopt the linter on old code

```bash
fobis lint --update-baseline    # record today's findings; commit .fobis-lint-baseline.json
fobis lint                      # only new findings from now on
```

Tutorial: [suppressions, baselines and fixes](/tutorial/quality/02-fixes).

## Silence one finding, with a reason

```fortran
use mpi ! fobis: ignore[COR040] the mpi module's names are all prefixed mpi_
```

## Fix what can be fixed automatically

```bash
fobis lint --diff      # what would change
fobis lint --fix
fobis modernize --apply  # only fixes that leave the build, the tests and the cases unchanged
```

Tutorial: [verified modernisation](/tutorial/quality/05-modernize).

## Review only what changed

```bash
fobis review                 # the working tree against HEAD
fobis review --base main     # a branch
fobis review --staged        # as a pre-commit hook
```

Tutorial: [reviewing a change](/tutorial/quality/03-review).

## Who calls a procedure, who writes a variable

```bash
fobis query callers simpson
fobis query writers mymodule::counter
fobis query region src/sweep.F90:15
fobis query mpi
```

From a parse of the code, not a text search: generics, type-bound procedures and renamed imports are followed.
Tutorial: [querying the code](/tutorial/quality/04-query).

## Call Fortran from C or Python

```bash
fobis bindings quad_rules
```

A `bind(c)` shim, a C header and a Python ctypes module, for the public procedures that can be bound (the others
are listed with the reason). Tutorial: [C and Python bindings](/tutorial/quality/06-bindings).

## Brief an AI agent on the project

```bash
fobis agents-md
```

Tutorial: [instructions for agents](/tutorial/quality/07-agents).
