---
title: Guides
---

# Guides

One page per feature, grouped by what you are doing. The [tutorials](/tutorial/) show the features at work in
order; these pages hold the details.

## Building

| Guide | |
|---|---|
| [The fobos file](/fobos/) | modes, templates, variables, rules, project metadata ([complete example](/fobos/complete-example)) |
| [Build profiles](/advanced/build-profiles) | `debug`, `release`, `asan`, `coverage` flag presets per compiler |
| [Feature flags](/advanced/features) | named compile-time options, groups, requirements and conflicts |
| [Varsets](/advanced/varsets) | named bundles of `$variables`, for clusters and toolchains |
| [Includes](/advanced/includes) | fobos files pulling in other fobos files |
| [External libraries](/advanced/externals) | MPI, HDF5, NetCDF... found and linked by name |
| [Libraries by path](/advanced/libraries) | static and shared libraries linked by path or name |
| [Interdependent projects](/advanced/interdependent) | `dependon`: rebuild the libraries a program uses first |
| [Volatile libraries](/advanced/volatile-libs) | relink when a library changes |
| [Flag heritage](/advanced/cflags-heritage) | rebuild everything when the flags change |
| [Parallel compiling](/advanced/parallel) | `-j N` |
| [Build cache](/advanced/cache) | reuse objects across clean builds and branches |
| [Source discovery](/advanced/auto-discovery) | `src/`, `source/`, `app/` found without configuration |
| [PreForM](/advanced/preform) | template preprocessing |
| [GNU Makefile export](/advanced/makefile) | a Makefile for users without FoBiS |
| [fpm](/advanced/fpm) | import an `fpm.toml`, export one |
| [Compilers](/guide/compilers) | the supported compilers and their flags |

## Dependencies

| Guide | |
|---|---|
| [Fetching dependencies](/advanced/fetch) | `[dependencies]`, sources or libraries |
| [Lock file and semver](/advanced/lock-file) | reproducible fetches, version constraints |
| [Installing from GitHub](/advanced/install) | `fobis install user/repo` |

## Testing and verification

| Guide | |
|---|---|
| [Test runner](/advanced/testing) | `fobis test` |
| [Doctests](/advanced/doctests) | checks in the documentation comments |
| [Cases and provenance](/advanced/cases) | runs with quantities read from their outputs, and where they came from |
| [Verifying results](/advanced/verify) | references and tolerances |
| [Shadow modes and the matrix](/advanced/matrix) | checked rebuilds, every compiler and mode at once |
| [Assessing numerical error](/advanced/assess) | rounding, precision, refinement, input uncertainty |
| [Differential runs](/advanced/diff-run) | a change against a revision, case by case |
| [Benchmarks](/advanced/bench) | timings with confidence intervals, regressions located |
| [The gate](/advanced/gate) | every check in one verdict |
| [Clusters](/advanced/scheduler) | cases, tests and benchmarks through Slurm |
| [Profiling](/advanced/profile) | gprof, callgrind, Nsight Systems, mapped to the sources |

## Code quality

| Guide | |
|---|---|
| [Linting](/ai/lint) | the rules, suppressions, baselines, fixes, compiler feedback |
| [Lint rules](/lint-rules/) | every rule with examples |
| [Reviewing a change](/ai/review) | findings on the lines a change touches |
| [Querying the code](/advanced/query) | definitions, callers, writers, device data |
| [Verified modernisation](/advanced/modernize) | obsolescent constructs fixed, the fix proven by tests and cases |
| [C and Python bindings](/advanced/bindings) | `bind(c)` shims, headers, ctypes wrappers |

## AI-assisted development

| Guide | |
|---|---|
| [Overview](/ai/) | what needs a model, what does not |
| [Knowledge packs](/ai/knowledge-packs) | the standards and HPC practice, searchable |
| [Asking questions](/ai/ask) | answers from the packs and your sources, with citations |
| [Explaining failures](/ai/explain) | build, run and test failures |
| [Merge conflicts](/ai/merge-assist) | compiled resolutions |
| [Generating tests](/ai/testgen) | test programs kept only when they build, run and check |
| [Commit messages](/advanced/commit) | Conventional Commits from the staged changes |
| [Local runtime](/ai/runtime) and [models](/ai/models) | open models run by FoBiS |
| [MCP server](/ai/mcp) | FoBiS's tools for AI agents |
| [Instructions for agents](/advanced/agents-md) | an `AGENTS.md` written from the project's facts |
| [Claude Code skill](/guide/claude-skill) | the `/fobis` skill |

## Many projects

| Guide | |
|---|---|
| [Ecosystem](/advanced/ecosystem) | dashboard, commands across projects, checks downstream, release train |
| [Scaffold](/advanced/scaffold) | boilerplate kept in sync across repositories |
| [JSON output](/advanced/json-output) | machine-readable output for scripts and CI |
