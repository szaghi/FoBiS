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
```

### Releasing a new version
```bash
# Requires: git-cliff installed (pipx install git-cliff)
./release.sh --patch    # X.Y.Z → X.Y.Z+1
./release.sh --minor    # X.Y.Z → X.Y+1.0
./release.sh --major    # X.Y.Z → X+1.0.0
./release.sh 3.7.0      # explicit version

# What release.sh does:
# 1. Creates release/vX.Y.Z branch
# 2. Bumps __version__ in fobis/__init__.py
# 3. Regenerates docs/guide/changelog.md via git-cliff (CHANGELOG.md is a symlink to it)
# 4. Runs pytest
# 5. Commits + merges to master + tags vX.Y.Z + pushes
# 6. Merges master back to develop + pushes
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

- **fobis.py**: Main entry point with `run_fobis()` orchestrating all commands (build, clean, install, doctests, rule, fetch)

- **FoBiSConfig.py**: Configuration class that parses CLI arguments and fobos files, manages cflags heritage, and handles interdependent project builds. Contains app metadata (`__appname__`, `__author__`, etc.); `__version__` is imported from `fobis/__init__.py` (single source of truth for `pyproject.toml`). The `_load_fetched_deps()` method auto-loads `.fobis_deps/.deps_config.ini` during `build`: `dependon` entries are appended to `cliargs.dependon` (and their directories added to `cliargs.exclude_dirs` to prevent source-scan overlap); `src` entries are appended to `cliargs.src` when not already covered by an existing source path.

- **cli_parser.py**: Argparse-based CLI with subcommands (build, clean, rule, install, doctests, fetch). Defines supported file extensions and compilers.

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

- **Compiler.py**: Compiler abstraction supporting: gnu, intel, intel_nextgen, g95, opencoarrays-gnu, pgi, ibm, nag, nvfortran, amd, custom. Handles MPI, OpenMP, coarray, coverage, and profile flags.

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

## Test Structure

Tests use **pytest** and live in `tests/`:

| File | Description |
|------|-------------|
| `tests/helpers.py` | Shared helpers: `run_build`, `run_clean`, `make_makefile`, `run_install`, `run_doctest`, `run_rule`, `TESTS_DIR`, `OPENCOARRAYS` |
| `tests/conftest.py` | pytest configuration/fixtures |
| `tests/test_build.py` | 32 parametrized build scenarios |
| `tests/test_clean.py` | 1 clean scenario |
| `tests/test_makefile.py` | 2 Makefile generation scenarios |
| `tests/test_install.py` | 4 install scenarios |
| `tests/test_doctest.py` | 3 doctest scenarios |
| `tests/test_rules.py` | 1 custom rule scenario |
| `tests/test_template.py` | Circular template detection |
| `tests/test_fetch.py` | Fetcher unit tests + 4 integration scenarios |

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
