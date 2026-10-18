---
title: Continuous integration and machine output
---

# Continuous integration and machine output

A CI job runs the commands you run, and reads their results. With `--json` a command writes one JSON document on its
standard output and its messages on the standard error, so a script, a later job step or an agent reads facts, not log
lines. The exit status carries the verdict on its own: a step fails when the command fails.

How it works:

1. **One document on stdout.** With `--json` (or `--format json`/`sarif`, or `--print` on the commands that generate
   files), FoBiS's progress lines, warnings and errors go to stderr; stdout holds the document and nothing else.
2. **The facts of a failure in the document.** A failed build carries the compiler's messages parsed and FoBiS's
   diagnosis; a failed test, the crash located in the sources; a failed verification, the worst point.
3. **The exit status does not change with `--json`.** 0 when the command succeeds, 1 when it fails (a build, a test,
   a finding, a result out of tolerance), 2 when the command is declared wrongly (an unknown case, mode key or stage).
   The document is printed before FoBiS exits, whatever the status.

Tutorial: [continuous integration](/tutorial/growing/06-ci), [one command for all of it](/tutorial/numerics/07-gate).
Reference: [`build`](/reference/build), [`test`](/reference/test), [`gate`](/reference/gate),
[`introspect`](/reference/introspect).

## A GitHub Actions workflow

Install, fetch, build, test, coverage:

<<< @/examples/tutorial/2-growing/06-ci/files/.github/workflows/ci.yml{yaml}

- **`fobis fetch` clones the dependencies at the tags the fobos pins.** The lock file lives in `.fobis_deps/`, which
  is not committed: a fresh checkout has none, so `fetch --frozen` belongs on machines that keep their fetched
  dependencies, not on a fresh CI runner. Pin with `tag=` or `rev=` in the fobos instead. More in
  [Dependencies](./dependencies).
- **The coverage step fails the job** below 90% of the lines (`--fail-under`). gcovr 7.2 with gcov 13 reports
  Fortran module procedures; gcovr 8.6 reports 0 lines for them. The upload to Codecov is in [Testing](./testing).
- **`tests.json` is a file a later step reads**, or an artifact to upload: `fobis test --json` still exits 1 when a
  test fails, so the step fails too.
- **Several compilers:** a job matrix over `--mode` (one mode per compiler) or over `--compiler`; for the compilers
  of a workstation or a cluster loaded by environment modules, see [HPC and clusters](./hpc).

A first step that fails fast, before compiling anything: `fobis check` resolves every file's dependencies.

<<< @/examples/output/2-growing/06/check.txt{console}

## Cache between runs

Cache the fetched dependencies, keyed on the fobos that pins them:

```yaml
- uses: actions/cache@v4
  with:
    path: .fobis_deps
    key: fobis-deps-${{ runner.os }}-${{ hashFiles('fobos') }}
- run: fobis fetch            # an existing clone is checked out at the pin, not cloned again
```

- **The key must change with the pins.** `fobis fetch` without `--update` does not fetch new commits into an existing
  clone: a tag added upstream after the cache was saved is not in it. Keying on `fobos` makes a new pin a new cache.
- **Caching the build directory does not save compile time.** FoBiS rebuilds an object older than its source, and a
  fresh checkout makes every source newer than any restored object.

## One command for a pull request

`fobis gate` runs every applicable check, each as a nested `fobis` command with `--json`, and gives one verdict: build,
review of the changed lines, tests, verification against the references, differential execution against the base,
benchmarks, numerical assessment, the matrix of compilers and shadows. A stage that does not apply (no case, no
benchmark, no change) is skipped with its reason; a failed build skips the stages that need it.

<<< @/examples/output/5-numerics/07/section.txt{ini}

<<< @/examples/output/5-numerics/07/gate.txt{console}

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0            # the merge base must be in the clone
- run: pip install FoBiS.py
- run: fobis fetch
- run: fobis gate --base origin/main --json > gate.json
```

- **`--base REF`** compares with the merge base of HEAD and `REF`: review sees the branch's changes, uncommitted ones
  included, and `diff-run` runs the cases on both sides. Without `--base`, the working tree is compared with HEAD.
- **Skip what is noise on a shared runner:** benchmark timings (`skip = bench`). `advisory = ...` keeps a stage in the
  report without letting it fail the gate; `--fail-fast` stops at the first failing stage.
- **Exit status:** 0 pass, 1 a non-advisory stage failed or gave no JSON, 2 a declaration error or an unknown base.
- **The gate runs locally.** On a cluster its nested commands do not take `--runner slurm`: see
  [HPC and clusters](./hpc).

Every stage and key: [Verifying results](./verification). Reference: [`gate`](/reference/gate).

## Lint and review on pull requests

Annotations on the changed lines, and the job fails on a finding:

```bash
fobis lint --format github                            # every finding of the project
fobis review --base origin/main --format github       # only the lines the branch changed
```

<<< @/examples/output/4-quality/01/github.txt{console}

The report in the job summary, or as a comment with your usual action:

```yaml
- run: fobis review --base origin/${{ github.base_ref }} --format markdown --exit-zero >> "$GITHUB_STEP_SUMMARY"
```

<<< @/examples/output/4-quality/03/markdown.txt{console}

GitHub code scanning (findings tracked across commits in the repository's *Security* tab):

```yaml
- run: fobis lint --format sarif --exit-zero > fobis-lint.sarif
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: fobis-lint.sarif
```

- **Exit status:** 1 when a warning- or error-level finding remains or a file cannot be read; `--exit-zero` always 0,
  for a step that only uploads a report.
- **`review` needs the merge base in the clone:** `fetch-depth: 0` on the checkout.
- **Old code:** `review` judges only the changed lines; for `lint`, a baseline keeps the existing findings out of the
  verdict, so only new ones fail the job.

Rules, baselines, suppressions and fixes: [Code quality](./analysis).

## Keep the agents' instructions current

`fobis agents-md` writes the project's facts (modes, commands, kinds, parallel models, cases) into a marked block of
`AGENTS.md`. In CI, check that the committed block matches the fobos and the sources:

```yaml
- run: fobis agents-md --check
```

Exit 0 when every file's block is current; 1 when one is stale (the unified diff is printed), has no block, or the
file does not exist; 2 for broken markers or a fobos error. The block holds no date, version or machine state, so it
changes only when the project does. `--check --json` gives each file's status and diff. More in
[Models, knowledge and agents](./ai-setup).

## Read the results in a script

```bash
fobis build --json            # status, objects compiled, errors; on failure diagnostics and diagnoses
fobis check --json            # unresolved dependencies, cycles, warnings
fobis test --json -j 4        # every test's status; with -j the document adds jobs and elapsed
fobis tree --json             # the dependency tree, each dependency with its own version
fobis introspect --buildoptions --mode release   # JSON always: a mode's effective settings
fobis verify --json           # each case against its reference, with the worst point
fobis gate --json             # every stage's verdict and its first failing fact
```

A successful build:

<<< @/examples/output/2-growing/06/build.txt{console}

A file using a module nobody defines: the compiler's message parsed (`diagnostics`), and what FoBiS establishes from
the project's facts (`diagnoses`, the same as [`build --explain`](/reference/build) without a model):

<<< @/examples/output/2-growing/06/failed.txt{console}

The tests, with standard error thrown away to show that stdout is the document alone:

<<< @/examples/output/2-growing/06/test.txt{console}

In a script:

```bash
result=$(fobis build --json)
if [ "$(echo "$result" | jq -r .status)" != ok ]; then
  echo "$result" | jq -r '.diagnoses[].summary'
  exit 1
fi
```

- **Which commands:** `--json` on `build`, `clean`, `fetch`, `check`, `tree`, `test`, `new`, `case list`, `case run`,
  `provenance`, `verify`, `matrix`, `assess`, `diff-run`, `bench`, `gate`, `profile`, `query`, `modernize`,
  `bindings`, `agents-md`, `fpm import`, `fpm export`, `ecosystem dashboard`, `ecosystem graph`, `kb search`,
  `llm list`, `llm serve status`, and `commit --show-facts`, `ask --show-context`. `lint`, `review`, `merge-assist`,
  `testgen` and `ecosystem impact` take `--format json`. `introspect` prints JSON unless `--format toml`.
- **Statuses differ by command:** `ok`/`error` for build, check and test; `pass`/`fail` for verify and gate; per test
  `passed`, `failed`, `build-failed`, `timeout`, `error`. Read the exit status for the verdict, the document for the
  facts.
- **Exit 2 means the declaration is wrong**, not the code: an unknown case, stage or `[scheduler]` key, a launcher
  not on the PATH. Several of these print `Error: ...` on stderr and no document.
- **Progress lines of long commands** (`gate: ...`, `slurm: job ...`, the matrix's cells) go to stderr too.
- **The fields** are those of the outputs on this page and in the tutorials: read the ones a script needs and ignore
  the others, so a field added later breaks nothing.

Agents read the same documents through the MCP server, `fobis mcp`: see [Models, knowledge and agents](./ai-setup).

## Review before every commit

`fobis review --staged` as a pre-commit hook, with [pre-commit](https://pre-commit.com) or a plain git hook: the
rules only, no model, as fast as `fobis lint`. The hook files:
[Code quality](./analysis#review-in-a-pre-commit-hook-and-in-pull-requests).

## The same CI in every project

`fobis scaffold` keeps a project's CI workflows, release script and documentation boilerplate in line with a
template (`status` lists the files `OK`, `OUTDATED` or `MISSING`, `sync` updates them after showing the diff), and
`fobis ecosystem` does it for every project of a group. Tutorial: [shared boilerplate](/tutorial/ecosystem/05-scaffold).
More in [Many projects](./ecosystem).
