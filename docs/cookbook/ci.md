---
title: Continuous integration
---

# Continuous integration

## A GitHub Actions workflow

<<< @/examples/tutorial/2-growing/06-ci/files/.github/workflows/ci.yml{yaml}

Tutorial: [continuous integration](/tutorial/growing/06-ci).

## Machine-readable results

```bash
fobis build --json
fobis test --json -j 4          # tests run four at a time; the document adds jobs and elapsed
fobis check --json
fobis verify --json
```

Every `--json` prints one document on the standard output (messages go to the standard error), with the facts of
a failure: compiler diagnostics, the diagnosis, the crash location. Guide: [JSON output](/advanced/json-output).

## Lint annotations on pull requests

```bash
fobis lint --format github
fobis review --base origin/main --format github
```

## One verdict for a pull request

```bash
fobis gate --base origin/main
```

```ini
[gate]
skip           = bench          ; timings on a shared runner are noise
matrix_modes   = debug
matrix_shadows = none checks
```

Tutorial: [one command for all of it](/tutorial/numerics/07-gate).

## The same CI in every project

`fobis scaffold` keeps a project's CI, release script and docs boilerplate in line with a template, and
`fobis ecosystem` with the others of a group. Tutorial: [shared boilerplate](/tutorial/ecosystem/05-scaffold).
