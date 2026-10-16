# Changelog

All notable changes to FoBiS.py are documented here.
Versions follow [Semantic Versioning](https://semver.org/).
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [3.9.9] — 2026-10-16
### Added
- **lint**: Add fobis lint with correctness and obsolescent-feature rules

- **lint**: Add OpenMP, OpenACC, MPI and modernisation rules with autofix

- **kb**: Add knowledge packs and fobis kb search

- **lint**: Add compiler feedback rules and fobis mcp server

- **lint**: Add Fortitude G4 rules and data-flow OpenMP, OpenACC and MPI rules

- **llm**: Add the model store and fobis llm pull, list, rm and recommended

- **llm**: Add the managed llama.cpp runtime and structured commit output ⚠ BREAKING CHANGE

- **llm**: Add fobis llm serve and make the model store relocatable

- **ai**: Add fobis ask with cited answers from the knowledge packs and project facts

- **build**: Add build --explain to diagnose failed builds from project facts and a cited LLM explanation

- **run**: Add run and test --explain to diagnose runtime failures without trusting optimised backtraces

- **lint**: Add lint --deep for cited LLM verdicts on findings and lint --ask for questions about a region

- **commit**: Infer the commit scope from repository history and Fortran line facts, and stop git colour codes reaching the model

- **review**: Add fobis review to report lint findings on changed lines only, with a cited risk summary

- **merge-assist**: Add fobis merge-assist to propose compiler-checked resolutions of merge, rebase and cherry-pick conflicts

- **ecosystem**: Add ecosystem impact to list the dependent code using a project's changed public Fortran interfaces

- **testgen**: Add fobis testgen to generate a module's tests from a compile-checked skeleton, kept only when they build, run and check

- **mcp**: Expose every FoBiS feature to agents as annotated tools over new structured JSON outputs, and fix tree reporting the root version for every dependency

- **verification**: Add declared cases whose runs extract numerical quantities with full provenance, as the base of fobis verification

- **verification**: Add fobis verify to compare case quantities with committed references within per-quantity tolerances, and rebuild case programs when the compiler or flags change

- **verification**: Add shadow modes and fobis matrix to build, test and verify every mode with checking flags across the machine's compilers, and fix fobis test building the mode's target instead of the test

- **verification**: Add fobis assess to estimate numerical error and uncertainty from ensembles of precision, rounding, compiler, parallel, input and refinement variants of a case, with budgets

- **verification**: Add fobis diff-run to run the declared cases on a revision and on the working tree in scratch copies and compare their quantities, with the changed procedures and an optional judgement against the numerical spread

- **analysis**: Add fobis query for deterministic code-graph answers (callers, callees, uses, writers, readers, defines, regions, device residency, MPI calls, interfaces) from the static analysis of the mode's sources

- **agents**: Add fobis agents-md to generate the build, test and verification instructions for coding agents from the fobos and the sources, kept current by --check

- **verification**: Add fobis bench to measure run time with a distribution-free interval of the median, compare with history or a revision only when the intervals do not overlap, and diff the compiler's vectorisation and data-movement reports; strip colour codes from compiler-feedback logs

- **verification**: Add fobis gate to run build, review, tests, verify, diff-run, bench, assess and the declared matrix as stages with one verdict and the first failing fact of each, and review --worktree to include uncommitted changes since a base

- **verification**: Run cases, tests, assessments and benchmarks as Slurm jobs with --runner slurm, from [scheduler] settings and the case's ranks, threads, GPUs and timeout, and refuse MPI and GPU runs on declared login nodes

- **verification**: Add fobis profile to map gprof time and callgrind instructions to the project's procedures and source lines, with inlined procedures found through their lines, the project callers of runtime routines, and per-rank load imbalance

- **fpm**: Add fobis fpm import and export to translate between fpm.toml and fobos with notes for what does not translate, and resolve a version file next to the fobos outside a git repository

- **bindings**: Add fobis bindings to generate bind(c) shims with explicit kind conversions, a C header and a Python ctypes wrapper for the public procedures of the modules, reporting why the others cannot be bound

- **verification**: Add fobis modernize to apply lint fixes in scratch copies and keep them only when build, tests and cases are unchanged, add automatic fixes for specific intrinsics, character*n and labelled DO loops, name duplicate test programs after their files, and report a stdout probe that reads nothing

- **kb**: Add compilers, libraries and numerics knowledge packs written from measurements on gfortran, ifx, nvfortran, Open MPI, Intel MPI and HDF5 and from the cited literature, check every compiler flag they name against the compiler, name the method section of each assess family, and route ask questions to the new packs

- **verification**: Add an nsys backend to fobis profile that maps GPU kernel time to the OpenACC/OpenMP directive lines and reports host-device transfers per direction and per source line and kernel time per rank, run every profiler through --runner slurm, record the compute node's facts in the provenance of Slurm runs, and stop reporting job ids, node names and GPU serial numbers as provenance changes

- **build**: Rebuild everything when the compiler behind the mode's command changes (another path or --version, e.g. after a module swap), recording it in the object directory after each successful build

- **merge-assist**: Replay historical merges with the configured model (merge_replay.py --model) and measure how its proposals compare with the committed resolutions

- **build**: Write the compilation database compile_commands.json on request and print it with introspect --compile-commands

- **run**: Start programs and tests through a launcher such as mpirun, gdb or valgrind with --launcher and --ranks

- **test**: Run test programs in parallel with fobis test -j N, and find the built programs with --no-build

- **fetch**: Mark test-only dependencies with :: dev, used by fobis test, doctests and check and left out of every other build

- **fetch**: Use a local directory as a dependency with path=DIR, compiled with the project or built by its own fobos, with no fetch needed

- **fobos**: Warn when a value holds an inline comment, which a fobos keeps as part of the value

- **build**: Compile C sources with the compiler family's C compiler and link them with the Fortran objects

- **fpm**: Import an fpm package with fpm's own flags: features, profiles, library types, path and dev dependencies

- **new**: Create a ready-to-build project with fobis new

- **config**: Warn when a user config value holds an inline comment, as a fobos does


### Changed
- **commit**: Route LLM access through a provider-agnostic layer

- **build**: Remove remove_other_main, which never removed anything


### Documentation
- Rewrite the docs in reading order with generated tutorial outputs

- Generate the command reference, every fobos mode key and the user configuration from FoBiS itself

- Add concept pages, redirect moved pages and check every link and anchor


### Fixed
- **commit**: Authenticate hosted LLM endpoints and raise typed errors

- **llm**: Bound every structured answer so small models cannot loop until the context is full, and name testgen's code field so models return code

- **run**: Exit with 128 + the signal number when the program is killed by a signal, as a shell does (139 for a segmentation fault instead of 245)

- **build**: Let an explicit --build-dir win over the mode's build_dir in build, clean, doctests, install and rule, and build the compiler-feedback report apart from the user's build tree

- **lint**: Stop reporting MPI004 when every branch calls the same collectives and OMP001/OMP002 for writes guarded by the thread number; feat(testgen): wrap over-long model lines before building and name the public generic of a private specific in the feedback

- **build**: Repair dependon, build profiles and machine output

- **build**: Parse sources in natural path order on every machine

- Report each compiler error once and mark only breaking API changes

- Compile bindings shims for imported kinds and skip C headers

- **bot**: Resolve ruff errors and use PyPI JSON API URL

- **ai**: Ask for the answer before the verdict, search doc comments, and lower the confidence of merges that do not compile

- **test**: Honour the [test] timeout and suite, and accept --preprocessor without a value

- **docs**: Check documented commands without importing click

- **check**: Report circular dependencies instead of crashing, honour --strict, and keep the lock file with the dependencies

- **build**: Give files named alike in several directories objects of their own


## [3.9.8] — 2026-10-08
### Fixed
- **scaffold**: Render templated sources of init-only and patched files


## [3.9.7] — 2026-10-06
### Fixed
- **scaffold**: Pin fpm v0.13.0 in the install smoke test


## [3.9.6] — 2026-10-06
### Fixed
- **scaffold**: Fetch fobos dependencies for make and cmake installs


## [3.9.5] — 2026-10-06
### Fixed
- **scaffold**: Build the install smoke test in the CI environment


## [3.9.4] — 2026-10-06
### Fixed
- **scaffold**: Run the install smoke test from the release workflow


## [3.9.3] — 2026-10-06
### Fixed
- **scaffold**: Extract release notes and fetch deps in install.sh


## [3.9.2] — 2026-10-04
### Fixed
- **fetch**: Fast-forward branch deps on --update so the lock tracks the remote head


## [3.9.1] — 2026-10-03
### Added
- **scaffold**: Check expected results and cap memory in run_tests.sh


## [3.9.0] — 2026-10-03
### Added
- **ecosystem**: Manage interconnected projects as a whole


### Documentation
- **ecosystem**: Show the whole dependency diagram in the dashboard screenshots


## [3.8.25] — 2026-10-03
### Fixed
- Preserve dash-prefixed option values and fail on doctest errors


## [3.8.24] — 2026-10-02
### Fixed
- **scaffold**: Keep the version of fpm.toml aligned on release


## [3.8.23] — 2026-10-02
### Fixed
- **rule**: Run fobos rule commands through the system shell


## [3.8.22] — 2026-07-08
### Added
- **scaffold**: Add `patched` category for additive config fragments


## [3.8.21] — 2026-07-07
### Fixed
- **scaffold**: Set vite build target to es2022 in docs template


## [3.8.20] — 2026-06-30
### Fixed
- **scaffold**: Use npm install in docs.yml to tolerate lockfile drift


## [3.8.19] — 2026-06-30
### Added
- **scaffold**: Auto-dispatch MPI test binaries in run_tests.sh


## [3.8.18] — 2026-06-30
### Added
- **scaffold**: Ship full API-docs generation in package.json


## [3.8.17] — 2026-06-30
### Fixed
- **fobos**: Don't warn on an intentionally-empty varset


## [3.8.16] — 2026-06-30
### Added
- **scaffold**: Parametrize via [scaffold] fobos section and MPI test runner


## [3.8.15] — 2026-06-30
### Added
- **scaffold**: Add symlink category and absorb project-led artifacts


### Documentation
- Sync CLAUDE.md with current CLI and module surface

- Correct CLI/API drift and refactor fobis skill


## [3.8.14] — 2026-06-23
### Added
- **build**: Add standalone offline zipapp distribution


### Fixed
- **docs**: Pin markdown-it-mathjax3 to ^4 for vitepress peer compat


## [3.8.13] — 2026-06-21
### Added
- **compiler**: Add first-class lfortran support


### Fixed
- **docs**: Resolve vite/esbuild advisories and add dependabot config


## [3.8.12] — 2026-05-11
### Added
- **scaffold**: Support xfail tests via *_xfail_* naming


## [3.8.11] — 2026-05-10
### Added
- **scaffold**: Extend install.sh with fpm build support and improve run_tests.sh


## [3.8.10] — 2026-05-09
### Fixed
- **scaffold**: Update release script to handle trunk branch detection and fetch errors


## [3.8.9] — 2026-05-08
### Fixed
- **test**: Regenerate build-test2 precompiled fixture at test-time


## [3.8.8] — 2026-05-08
### Fixed
- **scaffold**: Remove trailing comma in docs/package.json template


## [3.8.7] — 2026-05-06
### Fixed
- **build**: Print builder options header before submodule compilation


## [3.8.6] — 2026-05-06
### Fixed
- **scaffold**: Ship dot-directory files (.github/, .vitepress/) in wheel


## [3.8.5] — 2026-05-06
### Added
- **parser**: Filter compiler-supplied intrinsic modules


### Security
- **deps**: Bump uuid and postcss in /docs


## [3.8.4] — 2026-05-05
### Added
- **fobos**: Add [include] directive for splitting fobos files


## [3.8.3] — 2026-05-05
### Added
- **fobos**: Add varsets for invocation-time $variable binding


## [3.8.2] — 2026-05-05
### Added
- **features**: Add composable feature flags with constraints


### Fixed
- **commit**: Improve LLM prompt accuracy and remove redundant code


## [3.8.1] — 2026-04-14
### Fixed
- **commit**: Refine LLM prompt to prevent content inference from commit history


## [3.8.0] — 2026-04-12
### Added
- **core**: Implement build profiles, feature flags, and caching

- Add new subcommands, build profiles, and feature flags ⚠ BREAKING CHANGE


## [3.7.10] — 2026-04-10
### Added
- **commit**: Enhance commit lifecycle logic and test coverage

- **docs**: Improve commit message generation documentation


### Fixed
- **commit**: Streamline staged diff and prompt building logic


### chore
- **release**: Enforce structured argument parsing and failure recovery ⚠ BREAKING CHANGE


## [3.7.9] — 2026-04-10
### Added
- **commit**: Enable iterative prompt refinement for commit generation


### Performance
- **doc**: Normalize en dash to hyphen in docstrings


### chore
- **release**: Adopt trunk-based workflow for versioning ⚠ BREAKING CHANGE


## [3.7.7] — 2026-04-01
### Fixed
- **scaffold**: Adjust ford.md src_dir path and update package.json dependencies


## [3.7.6] — 2026-04-01
### Added
- **commit**: Introduce LLM-assisted conventional commit messages ⚠ BREAKING CHANGE


## [3.7.5] — 2026-04-01
### Added
- **scaffold**: Implement boilerplate synchronization across Fortran repos

- **scaffold**: Add init-only category and auto-discover fpm dependencies


### Documentation
- **index**: Add GIF showcase grid and rename projects section

- **scaffold**: Rename bump.sh to release.sh in all references


### Fixed
- **cli**: Rename _COMPLETION_FLAGS to lowercase to satisfy ruff N806

- **cli**: Rename app name from "FoBiS.py" to "fobis"


## [3.7.4] — 2026-03-17
### Documentation
- Standardize all command examples to use fobis instead of FoBiS.py

- Rework hero section in README and docs/index to highlight key features

- **readme**: Replace pipe table with html table in hero section

- Add animated GIF tutorials with VHS tapes and demo project

- **fetch-demo**: Pin PENF to v1.3.0 and add use penf to main.f90


### Fixed
- **cli**: Restore tab-completion broken by CliRunner env isolation


## [3.7.3] — 2026-03-16
### Added
- **skill**: Add /fobis Claude Code skill for expert FoBiS.py assistance


## [3.7.2] — 2026-03-16
### Added
- **cli**: Add --json structured output flag to build, clean, and fetch


## [3.7.1] — 2026-03-16
### Documentation
- **advanced**: Add architecture guide with module map and data-flow diagrams


## [3.7.0] — 2026-03-16
### Changed
- Drop Python 3.9, modernize type hints to PEP 604/585 syntax ⚠ BREAKING CHANGE


## [3.6.13] — 2026-03-16
### Fixed
- **cli**: Resolve ruff lint failures in fobis/cli sub-package


## [3.6.12] — 2026-03-16
### Changed
- **cli**: Split monolithic cli_parser.py into per-command subpackage


## [3.6.11] — 2026-03-16
### Fixed
- **cliff**: Fix regex and catch-all parser silencing all git-cliff warnings


## [3.6.10] — 2026-03-16
### Fixed
- Replace X | None union syntax with Optional for Python 3.9 compat


## [3.6.9] — 2026-03-16
### Changed
- Remove Python 2 dead code, add type hints, and enable coverage


### Documentation
- **changelog**: Make git-cliff write directly to docs/guide/changelog.md


### Fixed
- Eliminate shell injection, resource leaks, and stale test artifacts


## [3.6.8] — 2026-03-16
### Fixed
- **cli**: Restore -v / --version flag broken since version migration


## [3.6.6] — 2026-03-16
### Fixed
- **release**: Handle pipx-installed build module in release script


## [3.6.5] — 2026-03-16
### Changed
- Flatten source layout to standard Python conventions


## [3.6.2] — 2026-03-15
### Fixed
- **deps**: Remove deprecated typer[all] extra


## [3.6.0] — 2026-03-15
### Added
- **cli**: Replace argparse with Typer; add shell autocomplete ⚠ BREAKING CHANGE


## [3.5.4] — 2026-03-05
### Fixed
- **builder**: Include transitive deps of submodules in link command


## [3.5.3] — 2026-02-27
### Fixed
- **fetch**: Fix deps_dir treated as dependency and missing update


## [3.5.2] — 2026-02-27
### Added
- **fetch**: Add per-dependency use=sources|fobos integration mode


## [3.5.1] — 2026-02-27
### Added
- **builder**: Add configurable archiver and ranlib for static libraries


## [3.5.0] — 2026-02-27
### Added
- **fobos**: Support multiple templates and detect circular references


## [3.4.1] — 2026-02-27
### Added
- **fobos**: Add optional [project] section with name and authors

- **fobos**: Add version option to [project] section with git tag sync

- **fobos**: Add summary option to [project] section

- **fobos**: Add repository option to [project] section for remote url

- **fobos**: Add website option to [project] section

- **fobos**: Add email option to [project] section


### Documentation
- **fobos**: Add [project] section reference page with all options


## [3.4.0] — 2026-02-27
### Added
- **install**: Add GitHub-hosted project install via fobis install `repo`


## [3.3.4] — 2026-02-26
### Documentation
- **readme**: Add link to github pages documentation site


## [3.3.3] — 2026-02-26
### Documentation
- **readme**: Rewrite readme to mirror the vitepress landing page


## [3.3.2] — 2026-02-26
### Documentation
- Add vitepress documentation site with gh pages deployment


## [3.3.1] — 2026-02-26
### Fixed
- **ci**: Fix FoBiS.py command not found on Windows runners


## [3.3.0] — 2026-02-26
### Added
- **fetch**: Add fetch subcommand for GitHub Fortran dep management


## [3.2.2] — 2026-02-26
### Added
- **setup**: Add fobis console script entry point


## [3.2.1] — 2026-02-20
### Fixed
- **gcov**: Remove unused past.utils import that broke CI

- **bump.sh**: Prevent mid-release failure due to stale branches and PyPI filename change


## [3.2.0] — 2026-02-20
### Added
- **gcov**: Add mermaid pie charts to markdown coverage reports


## [3.1.0] — 2025-05-20
### Added
- Add AMD flang support

- **fobos**: Refactor fobos templates handling



