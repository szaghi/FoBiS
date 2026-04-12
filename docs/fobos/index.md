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
| Custom name or path | `fobis build -f /path/to/my_fobos` |
| Select a specific mode | `fobis build -mode release` |
| List available modes | `fobis build -lmodes` |

## Case sensitivity

By default fobos option names are case-sensitive. To make them case-insensitive:

```bash
fobis build -fci
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
| `build_profile` | Named compiler flag preset: `debug`, `release`, `asan`, `coverage` |
| `cache_dir` | Build cache directory (default: `.fobis_cache`) |
| `no_cache` | Disable build cache (`true`/`false`) |
| `no_auto_discover` | Disable convention-based source discovery (`true`/`false`) |
| `pre_build` | Shell command to run before the build |
| `post_build` | Shell command to run after a successful build |

## Special sections

Beyond the mode sections, a fobos file can contain several top-level sections with fixed names:

| Section | Purpose | Documentation |
|---|---|---|
| `[modes]` | Lists the available named mode sections | [Many-mode fobos](/fobos/many-modes) |
| `[project]` | Project metadata: name, version, authors, … | [Project metadata](/fobos/project) |
| `[features]` | Named compile-time option sets, activated with `--features` | [Feature Flags](/advanced/features) |
| `[dependencies]` | GitHub-hosted build dependencies | [Fetch Dependencies](/advanced/fetch) |
| `[test]` | Test runner defaults: suite, timeout, jobs | [Test Runner](/advanced/testing) |
| `[coverage]` | Coverage report settings: output dir, fail threshold, excludes | [Coverage](/reference/coverage) |
| `[externals]` | External library flags via `pkg-config` and MPI auto-detection | [External Libraries](/advanced/externals) |
| `[pkgconfig]` | Generate a `.pc` file for your own project | [External Libraries](/advanced/externals) |
| `[target.NAME]` | Named build target with per-target flag overrides | [build reference](/reference/build) |
| `[example.NAME]` | Named example target (same syntax as `target.NAME`) | [build reference](/reference/build) |
| `[rule-NAME]` | Custom shell-command rules | [Rules](/fobos/rules) |

### `[features]` section

Defines named compile-time option sets that map to flags:

```ini
[features]
default = mpi                     ; active when none are explicitly requested
mpi     = -DUSE_MPI
hdf5    = -DUSE_HDF5 -I/opt/hdf5/include
omp_defs = -DUSE_OMP              ; define only — pair with --features openmp
```

Flags are routed to `cflags` or `lflags` automatically by pattern.

Well-known compiler capabilities (`openmp`/`omp`, `mpi`, `coarray`, `coverage`,
`profile`) are **implicit features** — they work without a `[features]` section
and resolve to the correct compiler-specific flag automatically. See [Feature Flags](/advanced/features).

### `[dependencies]` section

Declares GitHub-hosted dependencies. Each entry maps a short name to a repository spec:

```ini
[dependencies]
deps_dir = .fobis_deps          # optional: where to clone deps (same as --deps-dir)
penf     = https://github.com/szaghi/PENF :: tag=v1.5.0
stdlib   = https://github.com/fortran-lang/stdlib :: semver=>=0.5,<1.0 :: use=fobos :: mode=gnu
```

The `use=` field selects the integration mode:
- **`sources`** (default) — dependency sources are compiled inline with your project
- **`fobos`** — dependency is built as a separate library and linked

See [Fetch Dependencies](/advanced/fetch) and [Lock File & Semver](/advanced/lock-file) for the full syntax and workflow.

### `[test]` section

Sets defaults for `fobis test`:

```ini
[test]
suite   = unit     ; only run tests tagged with this suite
timeout = 120      ; seconds per test
jobs    = 4        ; parallel compile jobs
```

### `[coverage]` section

Sets defaults for `fobis coverage`:

```ini
[coverage]
output_dir = coverage/
source_dir = src/
fail_under = 75
exclude    = test/*
            examples/*
```

### `[target.NAME]` and `[example.NAME]` sections

Named targets allow per-target flag overrides without separate fobos modes:

```ini
[target.solver]
target = src/solver.F90
output = solver
cflags = -c -O3 -DSOLVER

[example.demo]
target = examples/demo.F90
output = demo
```

```bash
fobis build --target-filter solver
fobis build --examples
```

## Comments

Lines beginning with `#` are ignored:

```ini
[default]
# This is a comment
compiler = gnu  # inline comments are also supported
cflags   = -c -O2
```

## Further reading

- [Complete example](/fobos/complete-example) — annotated fobos with every section and option
- [Single-mode fobos](/fobos/single-mode) — the simplest configuration
- [Many-mode fobos](/fobos/many-modes) — multiple build configurations in one file
- [Templates](/fobos/templates) — share common settings across modes
- [Variables](/fobos/variables) — define reusable `$variable` values
- [Rules](/fobos/rules) — custom task automation (documentation, archives, …)
- [Intrinsic rules](/fobos/intrinsic-rules) — built-in automation rules
- [Project metadata](/fobos/project) — `[project]` section: name, version, authors, and more
- [Feature Flags](/advanced/features) — `[features]` section: named compile-time option sets
- [Build Profiles](/advanced/build-profiles) — `build_profile` key: named compiler flag presets
- [Fetch Dependencies](/advanced/fetch) — `[dependencies]` section: GitHub-hosted build dependencies
- [Lock File & Semver](/advanced/lock-file) — reproducible builds and version constraints
- [Test Runner](/advanced/testing) — `[test]` section: test discovery and execution
- [Coverage](/reference/coverage) — `[coverage]` section: HTML/XML coverage reports
- [External Libraries](/advanced/externals) — `[externals]` and `[pkgconfig]` sections
