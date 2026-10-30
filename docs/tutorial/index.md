---
title: Tutorials
---

# Tutorials

The tutorials follow one project, `quad`: a small library of quadrature rules (the trapezoidal and Simpson rules) and
a program that uses it. It starts as three source files and no build script, and grows track by track: modes, a
library, tests, dependencies, then verified numerical results, a linted and reviewed code, and an AI assistant that
works under the same checks. The seventh track leaves `quad` for a lab's libraries, used by name through package
indexes.

Each track is a sequence of chapters, from the simplest to the most demanding; a track assumes the previous ones.
Every command output shown is the real one: the pages include what the commands printed when
`docs/scripts/docs_examples.py` ran them, and the CI reruns them and fails when an output changes.

## Tracks

| Track | Level | You learn |
|---|---|---|
| [1. First steps](./first-steps/01-first-build) | basic | build without configuration, a fobos with modes, a library, tests and coverage, dependencies |
| [2. Growing a project](./growing/01-templates) | intermediate | templates and variables, build profiles and feature flags, external libraries (MPI, OpenMP), rules, the cache, CI with machine-readable output, fpm and Makefile export, quad as a package found and used by name |
| [3. Many repositories](./ecosystem/01-register) | intermediate | an ecosystem of projects: dashboard, commands across all of them, checking the projects downstream, the release train |
| [4. Code quality](./quality/01-lint) | advanced | the linter, baselines and fixes, reviewing a change, querying the code, verified modernisation, C and Python bindings |
| [5. Verified numerics](./numerics/01-cases) | advanced | cases and references, shadow builds and the compiler matrix, error and uncertainty assessment, differential runs, benchmarks, the gate, profiling, clusters |
| [6. AI-assisted development](./ai/01-model) | expert | a local model, explained failures, questions answered from the sources, generated tests, merge conflicts, an agent working under the gate |
| [7. Packages and indexes](./packages/01-index) | intermediate | a lab's libraries as packages: an index of its own, finding and adding by name, versions, installing for a compiler, trust without a central server, fpm and CMake packages, fpm projects |


### 1. First steps

| Chapter | You learn |
|---|---|
| [1. A first build](./first-steps/01-first-build) | `fobis build` with no configuration: source discovery, dependency order, incremental rebuilds |
| [2. A fobos file](./first-steps/02-fobos) | modes, `--mode`, build directories, `fobis run` |
| [3. A library](./first-steps/03-library) | static and shared libraries, `fobis install`, linking an installed library |
| [4. Tests](./first-steps/04-tests) | `fobis test`, doctests, coverage |
| [5. Dependencies](./first-steps/05-dependencies) | `[dependencies]`, `fobis fetch`, the lock file |

```mermaid
flowchart LR
  A[1 first build] --> B[2 fobos] --> C[3 library] --> D[4 tests] --> E[5 dependencies]
```

### 2. Growing a project

| Chapter | You learn |
|---|---|
| [1. Templates and variables](./growing/01-templates) | `template`, `$variables`, `fobis introspect` |
| [2. Build profiles and features](./growing/02-profiles) | `build_profile`, `[features]`, `cflags_heritage` |
| [3. OpenMP and MPI](./growing/03-parallel) | `openmp = True`, `mpi = True` |
| [4. A project that depends on quad](./growing/04-dependon) | `dependon`, interface changes followed |
| [5. Rules](./growing/05-rules) | `[rule-NAME]`, `pre_build`/`post_build`, intrinsic rules, `--jobs` |
| [6. Continuous integration](./growing/06-ci) | `fobis check`, `--json`, a CI workflow |
| [7. Other build systems](./growing/07-export) | `fobis fpm export`, `--makefile` |
| [8. quad as a package](./growing/08-packages) | `fobis publish`, `index`, `search`, `info`, `add`, `transitive = true`, `pkg install`, `audit` |
| [9. One fobos, many machines](./growing/09-machines) | `[varset:NAME]`, `--varset`, `cflags.gnu`, `[include]`, `?fobos.local` |
| [10. Several programs and a library for others](./growing/10-targets) | `[target.NAME]`, `--target-filter`, `pkgconfig = True`, `--compile-commands` |

### 3. Many repositories

| Chapter | You learn |
|---|---|
| [1. An ecosystem](./ecosystem/01-register) | the registry, `discover`, `add`, `graph` |
| [2. The dashboard](./ecosystem/02-dashboard) | releases due, CI, drift, stale pins; JSON and HTML |
| [3. Acting on every project](./ecosystem/03-exec) | `exec`, `fetch`, in release order |
| [4. Before releasing](./ecosystem/04-check) | `check` (dependents against a working copy), `impact` |
| [5. Shared boilerplate](./ecosystem/05-scaffold) | `scaffold status` and `sync` |
| [6. The release train](./ecosystem/06-release) | `release`: plan, pre-flight, release in order |

### 4. Code quality

| Chapter | You learn |
|---|---|
| [1. The linter](./quality/01-lint) | `fobis lint`, `--explain`, `--select`, formats for CI |
| [2. Suppressions, baselines and fixes](./quality/02-fixes) | inline suppressions, `--diff`/`--fix`, the baseline |
| [3. Reviewing a change](./quality/03-review) | `fobis review`, findings on the changed lines only |
| [4. Querying the code](./quality/04-query) | `fobis query`: callers, writers, regions, MPI calls |
| [5. Verified modernisation](./quality/05-modernize) | `fobis modernize`: fixes kept only when tests pass |
| [6. C and Python bindings](./quality/06-bindings) | `fobis bindings`, a shared library, ctypes |
| [7. Instructions for agents](./quality/07-agents) | `fobis agents-md` |

### 5. Verified numerics

| Chapter | You learn |
|---|---|
| [1. Cases and quantities](./numerics/01-cases) | `[case:NAME]`, quantities, `fobis case run`, provenance |
| [2. References](./numerics/02-verify) | `fobis verify`, `--update`, a failure explained by its provenance |
| [3. Defects only some builds see](./numerics/03-shadows) | `--shadow checks/sanitize/strict`, `fobis matrix` |
| [4. How accurate is the result?](./numerics/04-assess) | `fobis assess`: refinement, precision and rounding families, budgets |
| [5. Is a refactoring harmless?](./numerics/05-diff-run) | `fobis diff-run REF`, `--assess`, tolerances |
| [6. Is it faster?](./numerics/06-bench) | `fobis bench`, `--compare`, `--record` |
| [7. One command for all of it](./numerics/07-gate) | `fobis gate`, `[gate]` |
| [8. Where the time goes](./numerics/08-profile) | `fobis profile`: gprof, callgrind |
| [9. On a cluster](./numerics/09-cluster) | `--runner slurm`, the login-node guard, nsys on a GPU |

### 6. AI-assisted development

| Chapter | You learn |
|---|---|
| [1. A local model](./ai/01-model) | `fobis llm`: runtime, models, `doctor` |
| [2. Build failures, explained](./ai/02-explain) | `build --explain`: diagnoses from facts, cited answers |
| [3. Crashes, located](./ai/03-crash) | `run --explain`, trusted locations |
| [4. Questions about the code](./ai/04-ask) | `fobis ask`, what a citation guarantees |
| [5. Generated tests](./ai/05-testgen) | `fobis testgen`: skeletons, accepted tests |
| [6. A second reader for a change](./ai/06-review) | `review --deep` |
| [7. Commit messages](./ai/07-commit) | `fobis commit`, `--show-facts` |
| [8. Merge conflicts](./ai/08-merge) | `fobis merge-assist`, compiled proposals |
| [9. An agent under the gate](./ai/09-agent) | `fobis mcp`, an agent calling the gate |

### 7. Packages and indexes

This track leaves `quad` for a lab's libraries and a project, `solver`, that uses them.

| Chapter | You learn |
|---|---|
| [1. An index of your own](./packages/01-index) | seed indexes, `fobis index build`, `index check`, `index add`, `follows` |
| [2. Find, add and remove](./packages/02-add) | `fobis search` (`--module`, `--build`), `info`, `add` (name, `INDEX:NAME`, `--module`, URL), `remove` |
| [3. Versions](./packages/03-versions) | tags and ranges, `fetch --update`, `add --semver --force`, `transitive = true`, minimal version selection |

## Running the examples yourself

The project of each chapter is in
[`docs/examples/tutorial`](https://github.com/szaghi/FoBiS/tree/master/docs/examples/tutorial): the `files/` of a
chapter are what it adds or changes, its `session.sh` the commands it runs. To rerun them all:

```bash
python docs/scripts/docs_examples.py          # regenerates docs/examples/output
python docs/scripts/docs_examples.py --check   # compares with the committed outputs
```

The outputs were produced with gfortran 13, the compiler of the CI; `DOCS_FC=gfortran-14` runs them with another.
Timings, profiles and the cluster chapter depend on the machine: they were recorded once (files named
`*.measured.txt`) and the CI checks only that their commands are unchanged.
