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

- **fobis.py**: Main entry point with `run_fobis()` orchestrating all commands (build, clean, install, doctests, rule)

- **FoBiSConfig.py**: Configuration class that parses CLI arguments and fobos files, manages cflags heritage, and handles interdependent project builds. Contains version info (`__version__`, `__appname__`).

- **cli_parser.py**: Argparse-based CLI with subcommands (build, clean, rule, install, doctests). Defines supported file extensions and compilers.

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

## Test Structure

Tests are in `src/unittest/python/` with subdirectories for each test type:
- `build-test{1-28}/`: Build scenarios with fobos files
- `clean-test1/`: Clean functionality
- `makefile-test{1-2}/`: Makefile generation
- `install-test{1-4}/`: Install functionality
- `doctest-test{1-3}/`: Doctest functionality
- `rule-test1/`: Custom rule execution

Each test directory contains a `fobos` file and Fortran sources.
