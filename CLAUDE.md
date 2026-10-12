# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FoBiS.py is a Python CLI tool that automatically builds modern Fortran projects by parsing source files and resolving inter-module dependency hierarchies. It eliminates the need to manually track module dependencies in makefiles.

## Build and Development Commands

### Common tasks (via Makefile)
```bash
make dev    # pip install -e ".[dev]"
make test   # pytest
make lint   # ruff check + format check (no fixes)
make fmt    # ruff check --fix + ruff format
make clean  # remove dist/, *.egg-info/, .pytest_cache/, .ruff_cache/, __pycache__/
make standalone  # build dist/fobis.pyz — single-file offline zipapp (FoBiS + full typer closure) for air-gapped clusters
```

The `standalone` target vendors the full runtime dependency closure into one `dist/fobis.pyz` (stdlib `zipapp`) so it can be `scp`'d to clusters with no pip/PyPI and run as `python3 fobis.pyz build`. The tag-push CI (`python-package.yml`, `standalone` job) attaches the same archive to each GitHub Release. Requires `fobis/__main__.py` (the package + zipapp entry shim).

### Releasing a new version
```bash
# Requires: git-cliff installed (pipx install git-cliff)
./release.sh --patch    # X.Y.Z → X.Y.Z+1
./release.sh --minor    # X.Y.Z → X.Y+1.0
./release.sh --major    # X.Y.Z → X+1.0.0
./release.sh 3.7.0      # explicit version

# What release.sh does (trunk-based — must be on master):
# 1. Runs ruff lint + format checks (abort if failing)
# 2. Bumps __version__ in fobis/__init__.py
# 3. Regenerates docs/guide/changelog.md via git-cliff (CHANGELOG.md is a symlink to it)
# 4. Runs pytest
# 5. Commits version bump + tags vX.Y.Z
# 6. git push --follow-tags origin master
# 7. Tag push triggers CI: lint → test → build → publish (PyPI via OIDC)
```

### CI / release pipeline

The `python-package.yml` workflow has four jobs:

| Job | Trigger | What it does |
|-----|---------|--------------|
| `lint` | push/PR to master, tag `v*` | ruff check + format |
| `test` | push/PR to master, tag `v*` | pytest on ubuntu + gfortran |
| `build` | push/PR to master, tag `v*` | smoke-test entry points across 3 OS × 4 Python |
| `publish` | tag `v*` only | `python -m build` + PyPI OIDC publish |

PyPI publishing uses [OIDC Trusted Publisher](https://docs.pypi.org/trusted-publishers/) — no API token required. The PyPI project must have a Trusted Publisher configured:
- Repository: `szaghi/FoBiS`
- Workflow: `python-package.yml`
- Environment: `release`

### Building/Running the Project
```bash
# Run directly from source
python fobis/fobis.py build

# Install for development (editable install)
pip install -e ".[dev]"

# Build a distribution (sdist + wheel)
python -m build
```

### Testing
```bash
# Run the full test suite
pytest

# Run a single test file
pytest tests/test_build.py

# Run a specific parametrized case
pytest tests/test_build.py::test_build[1]

# Run with coverage
pytest --cov=fobis --cov-report=term-missing

# Tests require gfortran to be available in PATH
```

### Linting
```bash
# Check for lint issues
ruff check fobis/ tests/

# Check formatting
ruff format --check fobis/ tests/

# Auto-fix lint issues
ruff check --fix fobis/ tests/

# Apply formatting
ruff format fobis/ tests/
```

## Architecture

### Core Components (fobis/)

- **fobis.py**: Main entry point with `run_fobis()` orchestrating all commands (build, clean, install, doctests, rule, fetch, plus the newer commands below)

- **FoBiSConfig.py**: Configuration class that parses CLI arguments and fobos files, manages cflags heritage, and handles interdependent project builds. Contains app metadata (`__appname__`, `__author__`, etc.); `__version__` is imported from `fobis/__init__.py` (single source of truth for `pyproject.toml`). The `_load_fetched_deps()` method auto-loads `.fobis_deps/.deps_config.ini` during `build`: `dependon` entries are appended to `cliargs.dependon` (and their directories added to `cliargs.exclude_dirs` to prevent source-scan overlap); `src` entries are appended to `cliargs.src` when not already covered by an existing source path.

- **cli/** (package): **Typer-based** CLI (migrated from argparse, March 2026). The root Typer `app` lives in `cli/_app.py`; each subcommand is its own module that registers via `@app.command(...)` (or `app.add_typer(...)` for sub-apps). `cli/_options.py` holds shared `Annotated` option types (`FobosOpt`, `FciOpt`, ...), `cli/_completions.py` holds shell-completion callbacks, `cli/_constants.py` holds constants. Each command function assembles an `argparse.Namespace` and stores it in `ctx.obj['cliargs']`; all downstream core code reads `cliargs.*` unchanged. **Command set:** build, clean, rule, install, doctests, fetch, scaffold (sub-app: status/sync/init/list), **check, lint, kb (sub-app: list/search/show/notice/build/add/remove), mcp, llm (sub-app: recommended/pull/list/rm), test, coverage, tree, introspect, run, cache (sub-app: list/clean/show), commit, ecosystem (sub-app: discover/add/remove/dashboard/graph/exec/fetch/check/scaffold/release)**.

- **cli_parser.py**: Legacy argparse module retained for the backward-compat shim. `_normalize_args()` converts legacy single-dash multi-char options (`-compiler`, `-mode`, `-ex`) to double-dash and normalizes `--build_dir` → `--build-dir` before Typer/Click sees them, preserving 100% CLI back-compat and the test `fake_args` interface. Also defines supported file extensions and compilers.

- **ParsedFile.py**: Parses Fortran source files using regex to extract:
  - Module definitions and submodule relationships
  - `use` statements (filters intrinsic modules like iso_fortran_env)
  - `include` statements
  - Program declarations
  - Creates dependency graphs (optional graphviz output)

- **Builder.py**: Orchestrates compilation with:
  - Parallel compilation via multiprocessing Pool
  - Dependency hierarchy ordering
  - Preprocessor integration (PreForM.py supported)
  - GNU Make file generation
  - Support for static/shared library creation

- **Compiler.py**: Compiler abstraction supporting: gnu, intel, intel_nextgen, g95, opencoarrays-gnu, pgi, ibm, nag, nvfortran, amd, lfortran, custom. Handles MPI, OpenMP, coarray, coverage, and profile flags.

- **Fobos.py**: Parses fobos configuration files (INI format). Supports:
  - Multiple modes (build configurations)
  - Templates for mode inheritance
  - Local variable substitution ($var syntax)
  - Custom rules execution
  - `[dependencies]` section parsed by `get_dependencies()` for the `fetch` command; `get_deps_dir(default='.fobis_deps')` reads an optional `deps_dir` key from this section
  - `[project]` section (optional) parsed by `get_project_info()` → returns `{'name': str, 'authors': [str], 'version': str}` (raw fobos values); authors are newline-separated (configparser continuation lines)
  - `get_version()` resolves the effective version: reads `[project] version` (literal or file path relative to git root), falls back to `git describe --tags --abbrev=0`, warns with fix suggestions when both sources disagree

- **Fetcher.py**: Handles fetching, building, and installing GitHub-hosted FoBiS dependencies:
  - `parse_dep_spec()` parses `"URL [:: branch=X] [:: tag=X] [:: rev=X] [:: mode=X] [:: use=sources|fobos]"` specs
  - `fetch()` clones repos on first run; with `--update` runs `git fetch` + checkout
  - `build_dep()` runs `FoBiS.py build` inside the cloned dependency directory; called only for `use=fobos` deps
  - `save_config()` writes `.fobis_deps/.deps_config.ini`: `use=fobos` deps → `dependon` key; `use=sources` deps → `src` key
  - `load_config()` returns `{'dependon': [...], 'src': [...]}` (keys absent when no entries of that type)
  - `_resolve_url()` converts `user/repo` GitHub shorthand to a full HTTPS URL
  - `install_from_github()` orchestrates clone → build (with `--track_build`) → artifact install (used by `install <repo>`)
  - `_build_dep_tracked()` runs `fobis build --track_build` inside the cloned dir
  - `_install_artifacts()` walks dep dir for `.track_build` files and copies executables/libraries/mod files to prefix

- **Dependency.py**: Simple class representing a single dependency (module or include)

- **Doctest.py**: Extracts and runs inline doctests from Fortran module comments

#### Modules backing the newer commands

- **TestRunner.py** (`TestResult`, `TestRunner`): first-class test runner behind `fobis test`; `--suite` tag filtering; passthrough args
- **Coverage.py** (`CoverageReporter`) + **Gcov.py**: coverage reporting behind `fobis coverage` (html/xml/text/all); gcov markdown reports embed mermaid pie charts
- **Cache.py**: build-artifact cache behind the `fobis cache` sub-app (`list`/`clean`/`show`)
- **Commit.py**: LLM-assisted Conventional-Commit message generation behind `fobis commit` (`--provider ollama|openai` (`--backend` alias), `--url`, `--model`, `--api-key-env`; iterative prompt refinement). Task logic only: `generate(provider, ...)` builds the prompts and calls `provider.chat()`; git failures raise `GitError`/`NothingStagedError` (`CommitError`), never `sys.exit`
- **llm/** (package): provider-agnostic LLM layer (plan: `PLAN-llm.md`, features: `PLAN-ai-features.md`). `Provider` protocol (`chat(messages, *, schema, temperature, seed, max_tokens, on_token) -> Completion`); `OllamaProvider` (native `/api/chat`, schema -> `format`) and `OpenAICompatProvider` (`/v1/chat/completions`, schema -> `response_format.json_schema`) over the stdlib streaming client `http.post_stream`; `FakeProvider` (scripted replies, records calls) for tests; `LLMConfig.from_user_config()` + `get_provider()`; errors under `LLMError` (`ConfigError`/`ApiKeyError`, `ProviderUnavailableError`, `ProviderResponseError`). API keys only via an explicitly named env var (`api_key_env`), never an implicit default. Stdlib only: the zipapp must keep working
- **llm/models.py** + `cli/llm.py`: the model store behind `fobis llm` (harness phase P2, `PLAN-llm.md`). Spec `hf:<org>/<repo>[@<rev>]/<file>.gguf`, a local path, or an alias of `RECOMMENDED` (pinned to full commits, Apache-2.0 only; sizes and files verified against the Hub API when added). `HubClient` (stdlib): `resolve_revision` (`/api/models/<repo>/revision/<rev>` -> commit), `file_info` (tree API of the file's folder, sha256 = `lfs.oid`), `download` (`resolve/<commit>/<file>` answers 302 to a CDN on another host; resume via `.part` + `Range`, restart when the server answers 200; an early end of stream is NOT an error in urllib (read returns b"") so `done < size` -> `DownloadError` keeping `.part`; sha256/size mismatch -> `ChecksumMismatchError`, `.part` deleted). `HF_TOKEN` is added with `add_unredirected_header`, so urllib never forwards it to the CDN; `HF_ENDPOINT` for mirrors. `ModelStore(root=$FOBIS_LLM_DIR or ~/.fobis/llm)`: `<root>/models/<org>/<repo>/<commit>/<file>` + `manifest.json` (resolved spec -> repo, revision, file, parts[{path, sha256, size}], pulled_at), atomic writes; `pull` (idempotent, split GGUFs, disk-space check), `locate` (never downloads: `ModelMissingError` with the pull command), `remove` (prunes empty dirs), `entries`. Nothing downloads implicitly. `fobis.main()` dispatches `fobis llm` directly (progress must stream). Errors: `ModelMissingError`, `DownloadError`, `ChecksumMismatchError(DownloadError)`
- **analysis/** (package): statement-level Fortran analysis, NOT a parser (fparser2 cannot parse F2008+ OOP codes; tree-sitter would break the zipapp). `preprocessor.py` resolves `#if/#ifdef/#elif/#define` with the mode's `-D` flags (`parse_defines(_merged_preproc_flags(cliargs))`), unevaluable conditions assumed true + warning; `lexer.py` -> `SourceFile` of logical `Statement`s (continuations joined, comments dropped, `;` split, labels detached, `masked` = lower-case with string contents blanked; `!$omp`/`!$acc` directives as statements with `sentinel`; fixed form truncated at col 72; inline `! fobis: ignore[ID] reason` suppressions); `units.py` -> `FileUnits` tree (module/submodule/program/subroutine/function/module procedure/block data/interface + bodies/fragment) with per-unit facts: args, result, prefixes, implicit none (type/external), decls (`Decl`: type_spec, attrs, dims, init, pointer_init), uses, default access. Tolerant by design: unknown syntax is skipped statement by statement; derived-type and enum bodies are not unit specifications; macro-typed declarations (`VARTYPE(KKP), intent(in) :: q`) are recognised; `regions.py`: OpenMP/OpenACC directive parsing (`parse_directive` -> construct + `{clause: [vars]}`), `regions()` (block constructs to the matching `end`, loop constructs to the following DO nest via `loop_end`, `atomic` to the next statement), helpers `assignment`/`call_name`/`strip_if`; `project.py`: `ProjectIndex` built over ALL linted files before any rule runs (procedures by name + `procedure(name)` when unique, `!$acc routine`/`declare target` device routines, `!$acc declare create` module variables, callees of parallel regions, `mpi_init` vs `mpi_init_thread`, integer kind constants + `real_precision(kind)` (selected_real_kind/real64/kind(1.d0)/chains; PENF `R4P/R8P/R16P` fallback for kind modules outside the linted tree), module arrays, type -> final procedures, `enter data` variables, `mpi_comm_rank` rank variables)
- **lint/** (package): rule engine behind `fobis lint`. `rule.py`: `Rule` registry filled by the `@rule(...)` decorator (id `FAMnnn`, kebab name, severity, summary/rationale/bad/good docs, `equivalent` Fortitude code, `default`), `select_rules(select, ignore)` (prefixes, `ALL`; explicit selection enables opt-in rules); `rules/correctness.py` (COR, G1 + G4), `rules/obsolescent.py` (OBS, G2 + OBS014), `rules/modernisation.py` (MDN/PRT, G3; MDN011/MDN021 carry `Edit` fixes), `rules/style.py` (STY, G4: structure only, never formatting), `rules/fortran.py` (FOR, NUM001), `rules/parallel.py` (OMP/ACC/MPI001), `rules/mpi.py` (MPI002-006: source-order data flow within one unit, whole-array buffers only, rank branches from `ProjectIndex.rank_variables`); `rules/_common.py` helpers (`replacements` builds column-exact `Edit`s on physical lines, comments/strings untouched; `do_loops`/`innermost_loop`, `lookup`/`is_array`). Medium-confidence rules ship opt-in (`default=False`); every default-on rule was checked against the 19-repo corpus noise budget (see PLAN-ai-features.md "A3 as built"); rules get `ctx.project` (cross-file facts); `engine.py`: `analyse`/`check_units`/`lint_text` (one-file project)/`lint_files` (two passes: analyse all, `build_index`, then check)/`discover_files` (always skips `.fobis_deps`, VCS dirs; `.h` files with C markers are skipped into `LintResult.skipped`), `apply_fixes` (`--diff`/`--fix` in `run_fobis_lint._lint_fixes`), suppressions + meta rules LNT001-004, baseline (`fingerprint` = rule|path|normalised statement text, line-independent; count-matched); `report.py`: text/json/sarif 2.1.0/github. Generic rules reimplement the Fortitude catalogue natively (user decision; no dependency). Run with the fobos mode (sources, exclusions, defines); fobos `[lint]` (`Fobos.get_lint_config`: select/ignore/baseline); default baseline `.fobis-lint-baseline.json` when present
- **kb/** (package): knowledge packs behind `fobis kb` (`cli/kb.py` sub-app; never sets `cliargs`). `pack.py`: a pack = `pack.ini` + `NOTICE` + `index.json` (chunks `{id: "pack:doc#slug", doc, heading, text, symbols}`); scopes project `.fobis/kb` > user `$XDG_CONFIG_HOME/fobis/kb` > shipped; shipped packs are read through `importlib.resources` (`shipped_root()`), never `os.listdir`, so they load from the zipapp (regression test with `zipfile.Path`); `PackPath`/`Traversable` is type-only (`importlib.resources.abc` is 3.11+). `build.py`: markdown/skill dir -> pack (drops front matter, "How to Use This Skill", assistant-directed lines; heading chunks capped ~1800 chars; symbols from code spans + constraint ids; `rewrites` regex list). `search.py`: BM25 (heading words x2) + exact-symbol bonus, `neighbours()`. Shipped packs (`fobis/kb/packs/`: fortran-std, openmp, openacc, mpi, hpc-practice; CC-BY-4.0, attribution in pack.ini/NOTICE) are GENERATED by `python scripts/sync_kb.py ~/dotfiles` from the maintainer's skills (records the dotfiles rev; `REWRITES` redirect the skills' references to CLAUDE-*.md / memory notes to the hpc-practice pack). Rule -> pack section links live in `fobis/lint/references.py` (`Rule.refs`, shown by `--explain` and on rule pages); `tests/test_kb.py` fails on a stale reference or on assistant-directed leftovers, and holds the retrieval eval (expected chunk in top 5). After rebuilding packs: re-run the tests, fix references, regenerate `docs/lint-rules`
- **lint/feedback.py** + **lint/rules/feedback.py**: compiler feedback (`fobis lint --compiler-feedback LOG`). `parse_log` reads nvfortran `-Minfo` (`procedure:` headers + `LINE, msg` + indented continuations; no file names) and gfortran `-fopt-info` (`file:line:col: kind: msg`); `attribute` maps nvfortran messages to files through `ProjectIndex.procedures` (line must fall inside the procedure; duplicate names disambiguated by the log's `Compiling <files>` lines) and counts the rest as unattributed. Rules ACC001 implicit data movement, ACC012 sequential device loop, OMP008 implicit target map, PRF001 loop not vectorized (opt-in) read `LintContext.feedback` only. FoBiS never runs the feedback build itself: with a fobos mode the mode's `build_dir` overrides `--build-dir`, so it would overwrite the user's build tree; a missing log prints the exact `fobis build --cflags ... | tee` command. `tests/compiler-feedback/` holds GENUINE logs (nvfortran 26.5, gfortran) captured with `fobis build`
- **mcp_server.py** + `cli/mcp.py`: `fobis mcp`, an MCP server (newline-delimited JSON-RPC 2.0 over stdio; protocol 2025-06-18/2025-03-26/2024-11-05). Tools: lint, list_rules, explain_rule, kb_search, kb_show, introspect, check, build, test. fobos-reading tools run `fobis` as a subprocess (`fobis_command()`: `python -m fobis`, or `python fobis.pyz` from the zipapp) so nothing can print into the protocol stream; rules/kb answered in process; `Server(run=...)` injectable for tests. `fobis.main()` dispatches `fobis mcp` directly (like `ecosystem`): the CliRunner would replace stdin and buffer stdout
- **Cleaner.py**: cleaning-phase controller
- **Externals.py** (`ExternalFlags`): resolved compiler/linker flags for one or more external libraries
- **PkgConfig.py** (`PkgConfigSpec`): generates `.pc` pkg-config files
- **SemVer.py** (`Version`): parsed `major.minor.patch` triple
- **Ecosystem.py** (`Ecosystem`, `Project`, `ProjectStatus`, `Pin`): behind the `fobis ecosystem` sub-app (`cli/ecosystem.py`). Manages a set of interconnected Fortran projects registered in the user config (`[ecosystem] root/projects`, read by `UserConfig.ecosystem_root`/`ecosystem_projects`): dependency graph from each fobos `[dependencies]` (topological levels, cycle report), per-repo status collected concurrently (git with `git -C`, never `chdir`; latest tag + Conventional-Commits bump; CI via `gh`; scaffold drift via `Scaffolder.drift()`; pins = `<deps_dir>/fobos.lock` commit vs the dependency's remote default-branch head), terminal/JSON/HTML (Mermaid) renderers. Self-contained on purpose: it uses the rest of FoBiS only through public interfaces, so it can later be extracted into a separate tool. Like `cache`, the sub-app never sets `ctx.obj['cliargs']`, so no fobos is loaded from the cwd; and `fobis.main()` dispatches `fobis ecosystem ...` to the Typer app directly, bypassing `FoBiSConfig`'s `CliRunner` (which buffers stdout until the end and replaces stdin, so prompts abort) — `run_fobis(fake_args)` still goes through the runner. Release rule: a commit is releasable when it touches a path outside `DEFAULT_RELEASE_EXCLUDE` (`docs/* .github/* *.md scripts/*`, overridable per project with fobos `[ecosystem] release_exclude`); the bump comes from the Conventional-Commits types of the releasable commits only. HTML dashboard: palettes in `Ecosystem.THEMES` (light+dark variant each), `--theme/--mode` or config `[ecosystem] theme/mode`; the page template uses `@@NAME@@` placeholders (not `str.format`) and computes all colours in JS (hue-preserving 4.5:1 contrast fix-up), so pytest cannot see JS bugs — exercise the page script under Node with a stub DOM when changing it. Phase 2 (acting): `run_step` (bash -c, streamed output, signal -> `crashed`), `FobisShim` (PATH launchers so `fobis`/`FoBiS.py` in commands and fobos rules run this FoBiS via `sys.executable -m fobis`), `exec_all`/`fetch_all` in release order, `check_dependents` (stages each transitive dependent in a tempdir from `git ls-files -co --exclude-standard`, with the changed project's working copy in its deps_dir; commands from fobos `[ecosystem] check`, else `rule --ex makecoverage`, else `build`), `scaffold_for` (honours fobos `[scaffold] skip`, also honoured by `fobis scaffold` itself via `Fobos.get_scaffold_config()['skip']`). Phase 3 (release train): `plan_release` (releasable projects in release order, version computed and passed explicitly to each repo's `scripts/release.sh`, pre-flight blockers for the whole train), `run_release_train` (release.sh with inherited stdin so its own prompt reaches the user; verifies tag locally + on remote because release.sh exits 0 when declined -> `aborted`; waits for the GitHub release via `gh release view`; `fetch_all` on direct dependents; stops at first failure, CLI prints a `--from` resume hint). `Scaffolder._confirm`: a prompt that cannot be answered (EOF/no tty) now means NO — never write without consent. Registry editing: `ecosystem add/remove` write through `UserConfig.set_ecosystem_projects()`, a line-based edit of the `projects` key only (configparser.write would drop every comment of the user's config), atomic replace
- **Profiles.py**, **UserConfig.py**, **Colors.py**, **Coverage.py**: supporting infrastructure (build profiles, user config, terminal coloring)

### Data Flow
1. `FoBiSConfig` parses CLI + fobos file -> `cliargs` namespace
2. `parse_files()` creates list of `ParsedFile` objects by scanning source directories
3. `dependency_hierarchy()` (in utils.py) resolves module dependencies between files
4. `Builder.build()` compiles in dependency order, then links

### Key Design Patterns
- Uses `fake_args` parameter in `run_fobis()` to enable programmatic invocation (used heavily in tests)
- Fobos file serves as project-specific makefile replacement (INI format with modes, templates, rules)
- Timestamps used to skip up-to-date objects; volatile libraries trigger rebuilds via MD5 hashing
- `fetch` command stores fetched deps in `.fobis_deps/` and writes `.fobis_deps/.deps_config.ini`; `build` auto-reads this file via `_load_fetched_deps()` before the normal `dependon` machinery runs
- Two per-dependency integration modes (`use=sources` default, `use=fobos`): source mode compiles the dep inline with the project; fobos mode builds the dep as a library and links against it via the `dependon` mechanism

### fetch command

The `fetch` subcommand clones GitHub-hosted FoBiS projects and saves a config file that `build` picks up automatically.

**Fobos `[dependencies]` section:**
```ini
[dependencies]
deps_dir = .fobis_deps                          # optional; overrides --deps-dir default
penf     = https://github.com/szaghi/PENF :: tag=v1.5.0
stdlib   = https://github.com/fortran-lang/stdlib :: tag=v0.5.0 :: use=fobos :: mode=gnu
jsonfort = https://github.com/jacobwilliams/json-fortran :: branch=main :: use=fobos
utils    = https://github.com/certik/fortran-utils :: rev=a1b2c3d
simple   = https://github.com/user/repo
```
Each entry: `name = URL [:: branch=X | tag=X | rev=X] [:: mode=X] [:: use=sources|fobos]`

**Per-dependency `use` option (mutually exclusive, default `sources`):**

| `use=` | `fobis fetch` | `fobis build` | Typical use |
|--------|--------------|---------------|-------------|
| `sources` (default) | clone only | dep dir added to source scan if not already covered; no library build | small/header-like deps compiled inline with the project |
| `fobos` | clone + `FoBiS.py build` | dep fobos added to `dependon`; dep dir added to `exclude_dirs` to prevent double-compile | deps that must be built as a separate library |

**Workflow:**
```bash
FoBiS.py fetch             # clone deps; pre-build use=fobos deps only
FoBiS.py fetch --update    # re-fetch (git pull/checkout) and re-build use=fobos deps
FoBiS.py fetch --no-build  # clone only (skips build even for use=fobos deps)
FoBiS.py build             # auto-reads .fobis_deps/.deps_config.ini:
                           #   src entries  -> appended to cliargs.src
                           #   dependon entries -> appended to cliargs.dependon
                           #                      + dep dir added to exclude_dirs
```

**Storage:** deps are cloned into `deps_dir/<name>/` (default `.fobis_deps/`); `deps_dir` can be set in fobos `[dependencies]` section or via `--deps-dir` CLI flag (CLI takes precedence). The generated `.deps_config.ini` has a `src` key for source-mode deps and a `dependon` key for fobos-mode deps.

### install command (GitHub mode)

When `install` receives a positional `repo` argument it behaves like a package manager: clone → build (with `--track_build`) → install artifacts to a prefix. The existing `install` behaviour (installing previously built local files) is fully preserved when no `repo` is given.

**Usage:**
```bash
fobis install szaghi/FLAP                        # install latest default branch to ./
fobis install szaghi/FLAP --tag v2.0.0 -p ~/.local  # pin to tag, install to ~/.local
fobis install szaghi/FLAP --branch develop --mode gnu
fobis install https://github.com/user/repo --rev a1b2c3d
fobis install szaghi/FLAP --no-build            # clone only
fobis install szaghi/FLAP --update              # re-pull before building
```

**Options added to `install`:** `repo` (positional, optional), `--branch`, `--tag`, `--rev`, `--update`, `--no-build`, `--deps-dir` (default: `~/.fobis/`).

**How it works:** `Fetcher.install_from_github()` calls `fetch()` to clone/update, then `_build_dep_tracked()` to build with `fobis build --track_build`, then `_install_artifacts()` scans for `.track_build` files and copies executables → `prefix/bin/`, libraries → `prefix/lib/`, mod files → `prefix/include/`.

## Documentation infrastructure

- `docs/.vitepress/theme/index.ts` + a markdown fence hook in `docs/.vitepress/config.mts` render ```` ```mermaid ```` blocks client-side with the `mermaid` devDependency (re-rendered on dark-mode toggle). `vitepress-plugin-mermaid` (used by StringiFor/PENF) does NOT support VitePress 2: do not add it. `vite.build.target = 'es2022'` is required by mermaid 11.16+.
- `docs/demo/ecosystem-demo/setup.sh DIR` builds a private 3-project ecosystem (core <- mathx <- app, local bare remotes, fetched deps, tags, scaffolded, a releasable `feat`); `source DIR/env.sh` selects its registry and rewrites `https://github.com/demo/*` to the local remotes via git `url.<base>.insteadOf`, so `fetch`/`release` work offline.
- Lint rule reference: `docs/lint-rules/*.md` + `sidebar.json` are GENERATED from the rule registry by `python docs/scripts/gen_lint_rules.py` and committed (a docs CI job builds with Node only); `tests/test_lint_docs.py` fails when they are stale, so regenerate after any rule change. The fobos *rules* (custom commands) live in `docs/fobos/rules.md`: different concept, hence the `/lint-rules/` path.
- GIFs: `docs/make_gifs.sh` + VHS tapes in `docs/public/gifs/tapes/`; tapes named `*_ecosystem_*` get a fresh demo ecosystem. Record unreleased features with the dev FoBiS first on PATH: `PATH=../.venv/bin:$PATH bash make_gifs.sh 09 10 11`. HTML-dashboard screenshots in `docs/public/images/` were taken with the headless Chromium VHS ships (`~/.cache/rod/browser/chromium-*/chrome --headless=new --screenshot`): `--window-size` includes the browser chrome, so the viewport is shorter than asked and a tight height clips the page — capture tall (`--window-size=1200,1000`), then crop (`ffmpeg -vf crop=1200:630:0:0`), and look at the result.

## Test Structure

Tests use **pytest** and live in `tests/`:

| File | Description |
|------|-------------|
| `tests/helpers.py` | Shared helpers: `run_build`, `run_clean`, `make_makefile`, `run_install`, `run_doctest`, `run_rule`, `TESTS_DIR`, `OPENCOARRAYS`, `PREFORM` |
| `tests/conftest.py` | pytest configuration/fixtures |
| `tests/unit/` | Unit tests for individual modules |
| `tests/test_build.py` | 32 parametrized build scenarios |
| `tests/test_clean.py` | 1 clean scenario |
| `tests/test_makefile.py` | 2 Makefile generation scenarios |
| `tests/test_install.py` | 4 install scenarios |
| `tests/test_doctest.py` | 3 doctest scenarios |
| `tests/test_rules.py` | 1 custom rule scenario |
| `tests/test_template.py` | Circular template detection |
| `tests/test_fetch.py` | Fetcher unit tests + 4 integration scenarios |
| `tests/test_scaffold.py` | `scaffold` subcommand (GH #164) |
| `tests/test_tree.py` | `tree` inter-project dependency rendering (GH #167) |
| `tests/test_externals.py` | `Externals` — automatic external library detection (GH #169) |
| `tests/test_semver.py` | `SemVer` — version constraint resolution (GH #171) |
| `tests/test_cache.py` | `Cache` — build artifact cache (GH #172) |
| `tests/test_testrunner.py` | `TestRunner` — first-class test runner (GH #173) |
| `tests/test_run.py` | `run` — build and execute a target (GH #174) |
| `tests/test_multitarget.py` | multi-target builds / `Fobos.get_targets()` (GH #175) |
| `tests/test_profiles.py` | `Profiles` — named build profiles (GH #176) |
| `tests/test_auto_discover.py` | convention-based source-dir auto-discovery (GH #177) |
| `tests/test_pkgconfig.py` | `PkgConfig` — automatic pkg-config file generation (GH #179) |
| `tests/test_coverage.py` | `Coverage` — coverage report generation (GH #180) |
| `tests/test_gcov.py` | `Gcov` — gcov file analysis and reporting |
| `tests/test_features.py` | feature flags — conditional compilation (GH #168) |
| `tests/test_includes.py` | `[include]` directive in fobos files |
| `tests/test_variables.py` | `$variable` substitution + `[varset:NAME]` mechanism |
| `tests/test_compiler_lfortran.py` | first-class LFortran compiler support |
| `tests/test_commit.py` | `Commit` — LLM-assisted commit-message generation |
| `tests/test_analysis.py` | `fobis.analysis` — cpp conditional evaluation, free/fixed-form lexing, directives, suppressions, unit tree and declaration facts |
| `tests/test_lint.py` | `fobis.lint` — positive and negative case per rule (`CASES`; a test fails if a rule has no positive case), suppressions, selection, baseline, the four report formats, CLI via `run_fobis` |
| `tests/test_feedback.py` | compiler feedback — parsing the genuine logs in `tests/compiler-feedback/`, attribution (duplicate names, unattributable), ACC001/ACC012/OMP008/PRF001, CLI |
| `tests/test_mcp.py` | `fobis mcp` — handshake/version negotiation, notifications, errors, tool command lines (fake runner), in-process rule/kb tools, stream serving, one real subprocess lint |
| `tests/test_kb.py` | `fobis.kb` — cleaning/chunking/build guards, scope precedence, BM25 + symbols, shipped-pack quality gates (licence, NOTICE, no assistant-directed text, rule references resolve), retrieval eval, zip loading, `fobis kb` CLI |
| `tests/test_lint_docs.py` | the committed `docs/lint-rules/` pages match the rule registry |
| `tests/test_llm_models.py` | model store against a real local fake Hub + CDN (two loopback HTTP servers): revision pinning, subfolders, split GGUFs, resume with `Range` (and restart when ignored), interrupted stream keeps `.part`, checksum mismatch, token never reaches the CDN, gated/404/non-LFS errors, disk space, `fobis llm` CLI |
| `tests/test_llm.py` | `fobis.llm` — streaming client, providers' payloads, `FakeProvider`, `LLMConfig`/`get_provider`, API-key resolution |
| `tests/test_userconfig.py` | `UserConfig` — user-level LLM configuration |
| `tests/test_ecosystem.py` | `Ecosystem` — `fobis ecosystem` (graph, status, pins, CI via mocked `gh`, renderers, CLI) on temporary git repos |
| `tests/test_release_script.py` | the scaffolded `scripts/release.sh` run for real (local bare origin, git-cliff stub, failures injected via `gpg.program=false` or a bad push URL): each failure stage prints a recovery hint that, followed, really recovers |

Fixture directories in `tests/`:
- `build-test{1-32}/`: Build scenarios with fobos files
- `clean-test1/`: Clean functionality
- `makefile-test{1-2}/`: Makefile generation
- `install-test{1-4}/`: Install functionality
- `doctest-test{1-3}/`: Doctest functionality
- `rule-test1/`: Custom rule execution
- `fetch-dep-test{1-4}/`: Fetch dependency integration
- `template-circular-test1/`: Circular template detection

Each fixture directory contains a `fobos` file and Fortran sources.
