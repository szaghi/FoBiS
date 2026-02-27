# fobos — the FoBiS makefile

A `fobos` file is FoBiS.py's project configuration file. It replaces makefiles entirely, using a simple INI-like syntax.

## Overview

When FoBiS.py runs, it automatically looks for a file named `fobos` in the current working directory. Options in the fobos file **override** the CLI defaults, and for `cflags`, `lflags`, and `preproc` they are combined with any additional values passed on the command line.

::: tip Design principle
Brevity is a design parameter. The fobos file uses the same option names as the CLI switches — there is nothing new to learn.
:::

## Basic structure

A minimal single-mode fobos file:

```ini
[default]
compiler  = gnu
cflags    = -c -O2
src       = ./src/
build_dir = ./build/
obj_dir   = ./obj/
mod_dir   = ./mod/
target    = src/main.f90
output    = myapp
```

A multi-mode fobos file:

```ini
[modes]
modes = debug release

[debug]
compiler  = gnu
cflags    = -c -O0 -g -Wall
build_dir = ./build/debug/

[release]
compiler  = gnu
cflags    = -c -O3
build_dir = ./build/release/
```

## Loading a fobos file

| Scenario | Command |
|---|---|
| Default name and location | Loaded automatically |
| Custom name or path | `FoBiS.py build -f /path/to/my_fobos` |
| Select a specific mode | `FoBiS.py build -mode release` |
| List available modes | `FoBiS.py build -lmodes` |

## Case sensitivity

By default fobos option names are case-sensitive. To make them case-insensitive:

```bash
FoBiS.py build -fci
```

Or in the fobos file itself, this is implicit for the option names (values remain as written).

## Available options

All CLI options accepted by `build` and `clean` are available in a fobos mode section with identical names (using the long form without the leading `--`). A representative set:

| Option | Description |
|---|---|
| `compiler` | Compiler identifier (gnu, intel, …) |
| `fc` | Compiler executable (for custom compiler) |
| `cflags` | Compilation flags |
| `lflags` | Linking flags |
| `preproc` | Preprocessor macro flags |
| `src` | Root source directory (space-separated list) |
| `build_dir` | Build output directory |
| `obj_dir` | Compiled objects directory |
| `mod_dir` | Module interface files directory |
| `lib_dir` | External library search directories |
| `include` | Include files search directories |
| `target` | Build target file |
| `output` | Output executable name |
| `exclude` | Files to exclude from the build |
| `libs` | External libraries (full paths) |
| `vlibs` | Volatile external libraries (full paths) |
| `ext_libs` | External libraries (by name, in linker path) |
| `ext_vlibs` | Volatile external libraries (by name) |
| `dependon` | Interdependent external fobos files |
| `mklib` | Build a library: `static` or `shared` |
| `ar` | Archiver executable for static libraries (default: `ar`) |
| `arflags` | Archiver flags (default: `-rcs`) |
| `ranlib` | Ranlib executable; set to empty string to skip (default: `ranlib`) |
| `mpi` | Enable MPI compiler variant |
| `openmp` | Enable OpenMP |
| `coarray` | Enable coarrays |
| `coverage` | Enable coverage instrumentation |
| `jobs` | Number of parallel compile jobs |
| `colors` | Coloured terminal output |
| `quiet` | Suppress verbose output |
| `log` | Write build log file |
| `cflags_heritage` | Track flag changes and force rebuild on change |

## Special sections

Beyond the mode sections, a fobos file can contain several top-level sections with fixed names:

| Section | Purpose | Documentation |
|---|---|---|
| `[modes]` | Lists the available named mode sections | [Many-mode fobos](/fobos/many-modes) |
| `[project]` | Project metadata: name, version, authors, … | [Project metadata](/fobos/project) |
| `[dependencies]` | GitHub-hosted build dependencies | [Fetch Dependencies](/advanced/fetch) |
| `[rule-NAME]` | Custom shell-command rules | [Rules](/fobos/rules) |

### `[dependencies]` section

Declares GitHub-hosted dependencies. Each entry maps a short name to a repository spec:

```ini
[dependencies]
deps_dir = .fobis_deps          # optional: where to clone deps (same as --deps-dir)
penf     = https://github.com/szaghi/PENF :: tag=v1.5.0
stdlib   = https://github.com/fortran-lang/stdlib :: tag=v0.5.0 :: use=fobos :: mode=gnu
```

The `use=` field selects the integration mode:
- **`sources`** (default) — dependency sources are compiled inline with your project
- **`fobos`** — dependency is built as a separate library and linked

See [Fetch Dependencies](/advanced/fetch) for the full syntax and workflow.

## Comments

Lines beginning with `#` are ignored:

```ini
[default]
# This is a comment
compiler = gnu  # inline comments are also supported
cflags   = -c -O2
```

## Further reading

- [Single-mode fobos](/fobos/single-mode) — the simplest configuration
- [Many-mode fobos](/fobos/many-modes) — multiple build configurations in one file
- [Templates](/fobos/templates) — share common settings across modes
- [Variables](/fobos/variables) — define reusable `$variable` values
- [Rules](/fobos/rules) — custom task automation (documentation, archives, …)
- [Intrinsic rules](/fobos/intrinsic-rules) — built-in automation rules
- [Project metadata](/fobos/project) — `[project]` section: name, version, authors, and more
- [Fetch Dependencies](/advanced/fetch) — `[dependencies]` section: GitHub-hosted build dependencies
