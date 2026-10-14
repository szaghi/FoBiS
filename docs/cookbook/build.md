---
title: Building
---

# Building

## Debug and release builds of the same sources

One mode per configuration, the common settings in a template:

```ini
[modes]
modes = debug release

[template-gnu]
compiler = gnu
src      = ./src/

[debug]
template      = template-gnu
build_profile = debug
cflags        = -c
build_dir     = ./build/debug/

[release]
template      = template-gnu
build_profile = release
cflags        = -c
build_dir     = ./build/release/
```

```bash
fobis build --mode debug
fobis build --lmodes          # the modes, with their help
```

`build_profile` adds the flags of a named profile for the mode's compiler (`fobis build --list-profiles`).
Tutorial: [templates and variables](/tutorial/growing/01-templates), [profiles](/tutorial/growing/02-profiles).

## Build one program out of many

```bash
fobis build --target src/solver.f90             # this program and what it uses
fobis build --target src/solver.f90 --output solver
```

or `target = src/solver.f90` in the mode. Only the files the program reaches through `use` are compiled. A target
outside the mode's `src` is an error. Several named programs in one mode: `[target.NAME]` sections, in the
[fobos reference](/fobos/#target-name-and-example-name-sections).

## A static or shared library

```ini
[shared]
compiler  = gnu
cflags    = -c -O2 -fPIC
src       = ./src/
build_dir = ./build/shared/
target    = src/mylib.f90
mklib     = shared
output    = libmylib.so
```

`mklib = static` builds an archive. `track_build = True` records what was built, for `fobis install`. Tutorial:
[a library](/tutorial/first-steps/03-library).

## Flags that differ by compiler

Keep the flags in the mode, one mode per compiler, and let a template hold the rest; or use a build profile, which
knows each compiler's flags for `debug`, `release`, `asan` and `coverage`:

```ini
[nvf-release]
compiler      = nvfortran
build_profile = release
cflags        = -c
src           = ./src/
build_dir     = ./build/nvf-release/
```

## Compile in parallel

```bash
fobis build --jobs 8
```

Files at the same level of the dependency graph compile at once. Tutorial: [rules and --jobs](/tutorial/growing/05-rules).

## Keep build products out of the sources

`build_dir` puts objects (`obj_dir`), module files (`mod_dir`) and programs under one directory; `--build-dir` on
the command line wins over the mode's.

```bash
fobis build --build-dir /scratch/me/build
fobis clean --mode debug
```

## Rebuild after changing the compiler

Nothing to do: FoBiS records the compiler's path and version in the object directory and rebuilds everything when
they change, a `module load` of another compiler version included. `--force-compile` rebuilds anyway.

## Preprocessor macros

```ini
[debug]
compiler = gnu
cflags   = -c -O0 -g
preproc  = -DDEBUG -DUSE_MPI
src      = ./src/
```

or switch groups of macros by name with `[features]` (`features = checks` in the mode, `--features` on the
command line). Guide: [feature flags](/advanced/features).

## A Makefile for people without FoBiS

```bash
fobis build --mode release --makefile Makefile
```

Tutorial: [other build systems](/tutorial/growing/07-export). `fobis fpm export` writes an `fpm.toml`.
