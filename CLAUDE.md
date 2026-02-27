# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FoBiS.py (Fortran Building System for poor men) is a Python CLI tool that automatically builds modern Fortran projects by parsing source files and resolving inter-module dependency hierarchies. It eliminates the need to manually track module dependencies in makefiles.

## Build and Development Commands

### Building/Running the Project
```bash
# Run directly from source
python src/main/python/fobis/fobis.py build

# Or using pybuilder (creates release artifacts)
pyb

# Install for development (from release directory after pyb)
pip install -e release/FoBiS-<branch>/
```

### Testing
```bash
# Run the full test suite
python src/unittest/python/suite_tests.py

# Run a single test class
python -m unittest src.unittest.python.suite_tests.SuiteTest.test_buildings

# Tests require gfortran to be available in PATH
```

### Linting
```bash
# Via pybuilder (runs flake8 and pylint)
pyb analyze
```

## Architecture

### Core Components (src/main/python/fobis/)

- **fobis.py**: Main entry point with `run_fobis()` orchestrating all commands (build, clean, install, doctests, rule, fetch)

- **FoBiSConfig.py**: Configuration class that parses CLI arguments and fobos files, manages cflags heritage, and handles interdependent project builds. Contains version info (`__version__`, `__appname__`). The `_load_fetched_deps()` method auto-loads `.fobis_deps/.deps_config.ini` during `build`, appending fetched dependency paths to `cliargs.dependon`.

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
  - `[dependencies]` section parsed by `get_dependencies()` for the `fetch` command

- **Fetcher.py**: Handles fetching, building, and installing GitHub-hosted FoBiS dependencies:
  - `parse_dep_spec()` parses `"URL [:: branch=X] [:: tag=X] [:: rev=X] [:: mode=X]"` specs
  - `fetch()` clones repos on first run; with `--update` runs `git fetch` + checkout
  - `build_dep()` runs `FoBiS.py build` inside the cloned dependency directory (used by `fetch`)
  - `save_config()` / `load_config()` manage `.fobis_deps/.deps_config.ini`
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
- `fetch` command stores fetched deps in `.fobis_deps/` and writes `.fobis_deps/.deps_config.ini`; `build` auto-reads this file via `_load_fetched_deps()` before the normal `dependon` machinery runs — zero changes to the build engine

### fetch command

The `fetch` subcommand clones GitHub-hosted FoBiS projects, builds them, and saves a config file that `build` picks up automatically.

**Fobos `[dependencies]` section:**
```ini
[dependencies]
stdlib   = https://github.com/fortran-lang/stdlib :: tag=v0.5.0 :: mode=gnu
jsonfort = https://github.com/jacobwilliams/json-fortran :: branch=main
utils    = https://github.com/certik/fortran-utils :: rev=a1b2c3d
simple   = https://github.com/user/repo
```
Each entry: `name = URL [:: branch=X | tag=X | rev=X] [:: mode=X]`

**Workflow:**
```bash
FoBiS.py fetch             # clone + build all deps from [dependencies]
FoBiS.py fetch --update    # re-fetch (git pull/checkout) and rebuild
FoBiS.py fetch --no-build  # clone only, skip building
FoBiS.py build             # auto-detects .fobis_deps/.deps_config.ini -> adds to -dependon
```

**Storage:** deps are cloned into `.fobis_deps/<name>/`; the generated `.fobis_deps/.deps_config.ini` lists paths in `dependon` format so the existing interdependent build machinery handles include paths and library linking automatically.

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

Tests are in `src/unittest/python/` with subdirectories for each test type:
- `build-test{1-28}/`: Build scenarios with fobos files
- `clean-test1/`: Clean functionality
- `makefile-test{1-2}/`: Makefile generation
- `install-test{1-4}/`: Install functionality
- `doctest-test{1-3}/`: Doctest functionality
- `rule-test1/`: Custom rule execution

Each test directory contains a `fobos` file and Fortran sources.
