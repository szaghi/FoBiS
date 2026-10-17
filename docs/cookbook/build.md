---
title: Building
---

# Building

`fobis build` compiles a Fortran project without a makefile: it reads the sources, finds which file defines each
module and which files use it, compiles them in that order and links every program. A `fobos` file in the project
root holds the configurations (modes) when the defaults are not enough. This page covers building programs; libraries,
external libraries, Makefile export and editor integration are in [Libraries and integration](./libraries),
dependencies in [Dependencies](./dependencies), tests in [Testing](./testing).

How it works:

1. **Settings.** The command line's options, then one mode of the fobos: `--mode`, else the first one listed in
   `[modes]`, else the `[default]` section. The mode's templates are applied, then its `$variables` substituted. A
   key the mode sets replaces the command line's value, except `cflags`, `lflags` and `preproc` given on the command
   line, which are appended, and an explicit `--target` or `--build-dir`, which wins. A key FoBiS does not know is
   ignored without a word.
2. **Sources.** The source directories are walked and every Fortran file is read for what matters to a build:
   `module` and `submodule` definitions, `use` statements, `include` lines, `program` statements. Intrinsic modules
   (`iso_fortran_env`, `iso_c_binding`, `ieee_*`, `omp_lib`, `openacc`, `mpi`, the compiler's own) are skipped. The
   files are read in the same order on every machine.
3. **Graph.** A `use` of a project module makes the file depend on the file defining it, an `include` on the
   included file. Every module is compiled before its users; the files of one level do not depend on each other and
   compile in parallel with `-j`. A circular dependency stops the build. A module no project file defines is left to
   the compiler, which must find its `.mod` in an include directory.
4. **Rebuilds.** A file is compiled again when its object is missing or older than the source, or when a file it
   depends on, directly or not, changed. Changing the flags recompiles nothing unless `cflags_heritage` is on;
   changing the compiler recompiles everything.
5. **Link.** Each program is linked with the objects of the files it reaches through `use`, plus every file that
   defines no module (external procedures, C files). A module no program uses is compiled but not linked.
6. **Outputs.** Objects in `<build_dir>/<obj_dir>`, module files in `<build_dir>/<mod_dir>`, programs in
   `<build_dir>`.

Tutorial: [a first build](/tutorial/first-steps/01-first-build), [a fobos](/tutorial/first-steps/02-fobos),
[templates and variables](/tutorial/growing/01-templates), [profiles and features](/tutorial/growing/02-profiles).
Reference: [`build`](/reference/build), [`clean`](/reference/clean), [`run`](/reference/run),
[`check`](/reference/check), [`introspect`](/reference/introspect), [`new`](/reference/new),
[every mode key](/fobos/), [compilers](/guide/compilers).

## Start a new project

```bash
fobis new demo                  # ./demo: a module, a program, a test
fobis new kit --lib             # a library: lib<name>.a in release, lib<name>.so in shared
fobis new . --name my_tool      # fill the current directory
fobis new demo --compiler intel_nextgen
fobis new demo --scaffold       # then fobis scaffold init --yes: CI, docs, release script
```

<<< @/examples/output/1-first-steps/01/new.txt{console}

<<< @/examples/output/1-first-steps/01/newbuild.txt{console}

What it writes: `src/NAME.f90` (a module), `app/main.f90` (program `main`, linked as `build/<mode>/NAME`; not with
`--lib`), `test/test_NAME.f90`, a `.gitignore` (`/build/`, `/.fobis_deps/`, `/.fobis/`, `/compile_commands.json`)
and a fobos: `[project]` (name, version 0.1.0, authors from `git config user.name`/`user.email`), modes `debug`
(sources and tests, `build_profile = debug`) and `release` (`build_profile = release`; with `--lib` the static
library, plus a `shared` mode), `[test] test_dir = test`.

- **NAME** is the directory's name, or `--name`; it must be a Fortran name (a letter, then letters, digits, `_`).
- **Any compiler family:** the modes use build profiles, so `--compiler` gets that compiler's flags.
- **Never overwrites.** When any of the files exists, nothing is written and the files are listed (exit 2).
- **git:** a repository is initialised, nothing committed, unless the directory is inside one or `--no-git` is given.
- **Exit codes:** 0 created, 2 invalid name or existing files, 1 `--scaffold` failed (the project is written).
  `--json` prints `status`, `name`, `path`, `files`, `git`.

## Build without a fobos

In a project with no fobos, `fobis build` scans the source directory, compiles every module in order and links every
program it finds:

<<< @/examples/output/1-first-steps/01/build.txt{console}

<<< @/examples/output/1-first-steps/01/after.txt{console}

![a first build](/gifs/01_basic_build.gif)

*No fobos: the sources found, compiled in dependency order and linked, then `fobis clean`.*

- **Source discovery.** Without `src` (in the mode or on the command line), FoBiS scans every one of `src/`,
  `source/` and `app/` that holds a Fortran file, and says so (`[auto-discover] src not set; scanning: ./src`); none
  of them, the current directory. `--no-auto-discover` (mode key `no_auto_discover = True`) scans the current
  directory instead. A project laid out as `fobis new` makes (`src/` and `app/`) is found as a whole.
- **Defaults:** `gnu` (`gfortran`), `cflags = -c`, objects in `./obj/`, modules in `./mod/`, programs in `./`, named
  after their file.
- **Everything on the command line works too:** `fobis build --compiler intel_nextgen --cflags "-c -O2" -j 4`.

## Write a fobos

One configuration, in a section named `[default]`:

```ini
[default]
compiler  = gnu
cflags    = -c -O2
src       = ./src/
build_dir = ./build/
target    = src/main.f90
output    = myapp
```

Several configurations, each a mode, listed in `[modes]`:

<<< @/examples/tutorial/1-first-steps/02-fobos/files/fobos{ini}

```bash
fobis build                     # the first mode listed: debug
fobis build --mode release
fobis build --lmodes            # the modes, with their help line
fobis build -f fobos.intel      # a fobos with another name or path
```

<<< @/examples/output/1-first-steps/02/lmodes.txt{console}

<<< @/examples/output/1-first-steps/02/tree.txt{console}

![a fobos with modes](/gifs/02_fobos_build.gif)

*A fobos with two modes: `fobis build` in the first one, then `--mode release`.*

- **Mode keys are the command-line options** without the leading `--` and with underscores (`--build-dir` is
  `build_dir`). Every key is in the [fobos reference](/fobos/).
- **A misspelt key is ignored without a warning.** Check it with `fobis introspect --buildoptions` (below).
- **`cflags` must hold `-c`**: a mode writing `cflags = -O2` compiles and links each file, and the build fails at
  the first module. A mode without `cflags` gets `-c`.
- **Comments go on lines of their own**, starting with `;` or `#`. A comment after a value is part of the value:
  `compiler = gnu ; laptop` names a compiler `gnu ; laptop`. FoBiS warns when a value holds ` ;` or ` #`, except in
  the shell commands run by bash: `[rule-*]` sections and the `setup` and `check` keys. The same holds for the
  [user configuration](/reference/configuration).
- **Values span lines** when the next lines are indented (a long `modes` list, several `src` directories).
- **Key names are case-sensitive.** `--fci` makes them case-insensitive (values stay as written).
- **Which section is used:** `--mode NAME` needs a `[modes]` section listing NAME. Without `[modes]` only
  `[default]` is read; a fobos with neither warns `fobos file has not "modes" section neither "default" one`.
- **An unknown `--mode`** prints an error and the defined modes, and exits 1.

## Name and version the project

```ini
[project]
name       = quad
summary    = Quadrature rules
version    = VERSION
repository = https://github.com/me/quad
website    = https://me.github.io/quad
email      = me@example.org
year       = 2020
authors    = Ada Fortran
             Charles Babbage
```

Every key is optional; authors go one per line. `fobis introspect --projectinfo`, `fobis tree`, pkg-config files,
`fobis fpm export` and `fobis scaffold` (`{{YEAR}}`, default the current year) read it.

- **`version`** is a literal, or a file holding it: a path relative to the git repository root (outside a git
  repository, next to the fobos). The result gets a leading `v` (`1.2.3` -> `v1.2.3`).
- **Without `version`**, the latest git tag (`git describe --tags --abbrev=0`) is the version.
- **Both set and different:** a warning names both and the two fixes (change the fobos, or tag).

## Debug and release builds

One mode per configuration; a build profile writes the flags for the mode's compiler:

```ini
[modes]
modes = debug release

[debug]
compiler      = gnu
build_profile = debug
cflags        = -c
src           = ./src/
build_dir     = ./build/debug/

[release]
compiler      = gnu
build_profile = release
cflags        = -c
src           = ./src/
build_dir     = ./build/release/
```

```bash
fobis build --list-profiles                        # every compiler's flags for each profile
fobis build --mode debug
fobis build --mode debug --build-profile release   # the command line's profile wins over the mode's
```

<<< @/examples/output/2-growing/02/profiles.txt{console}

- **Four profiles:** `debug` (checks, backtrace, floating-point traps, warnings), `release`, `asan` (address and
  undefined-behaviour sanitizers), `coverage` (for [`fobis coverage`](./testing)).
- **Compilers:** `gnu`, `intel`, `intel_nextgen`, `nvfortran`, `nag`, `amd`, `lfortran` (`--list-profiles` shows
  which pairs exist). A pair missing for a compiler of another family gives a warning and no flags: gfortran's
  options are not theirs. Missing on purpose, because measured: ifort ignores `-fsanitize=address`, nvfortran rejects
  `-fsanitize=address` and `--coverage`, ifx does not support `-ip` or `-prof-gen=srcpos`. A `custom` compiler gets
  the `gnu` flags, with a warning; an unknown profile name, a warning and no flags.
- **The profile comes first:** its flags are put before the mode's `cflags`, so the mode's own flags win on a
  conflict (`-O0 -g -fcheck=all ... -c -DDEBUG`). The profile's link flags go before `lflags`.
- **C files too:** each profile has flags for the family's C compiler (`[C: ...]` above), before `c_cflags`.
- **Not `--profile`:** that one adds profiling instrumentation (`-pg`).

## Build one program out of many

```bash
fobis build --target src/solver.f90                 # this program and what it uses
fobis build --target src/solver.f90 --output solver
```

or `target` and `output` in the mode. Only the files the program reaches through `use` are compiled.

<<< @/examples/output/2-growing/02/release.txt{console}

- **A target outside the mode's `src` is an error** (exit 1), as above: add its directory to the mode's sources.
- **A path or a name:** `--target src/main.f90` names that file; `--target main.f90` names every file called so.
- **An explicit `--target`** keeps its own target and output over the mode's: this is how `fobis test` builds each
  test in a mode that names a program.
- **Without a target**, every program found is built; `--build-all` compiles every source, programs or not.

Several programs of one mode, each with its own flags, are `[target.NAME]` sections; `[example.NAME]` sections are
built with `--examples`:

```ini
[target.solver]
source = src/solver.f90
cflags = -c -O3 -DSOLVER

[example.demo]
source = examples/demo.f90
```

```bash
fobis build                          # every [target.NAME]
fobis build --target-filter solver   # only that one
fobis build --examples               # the targets and the examples
```

- **The mode must not set `target`** when `[target.NAME]` sections exist (an error).
- **A key of the section replaces the mode's** (`cflags` above is the whole set, not an addition).
- **The targets share the mode's object directory:** a target with other flags does not recompile objects another
  target already built. Use one mode per flag set when the flags must reach every object.
- **`output`, `mklib`, `track_build` and `log` apply to their own target:** one section can name its program, another
  build a library.
- **`--examples` needs `[target.NAME]` sections:** in a fobos with examples alone it builds the mode's program only.

## Flags that differ by compiler or system

A key qualified by a compiler family or an operating system applies only there, so one mode serves several:

```ini
[release]
compiler         = gnu
cflags           = -c -O2
cflags.gnu       = -march=native
cflags.intel     = -xHost
cflags.windows   = -static
ext_libs.windows = ws2_32
```

```bash
fobis introspect --buildoptions --mode release   # which qualified keys applied, and the result
```

- **Qualifiers:** a `compiler` value (`gnu`, `intel`, `intel_nextgen`, `nvfortran`, ...) or a system (`linux`,
  `macos`, `windows`, `freebsd`). The compiler is the mode's, after its templates (a mode's `compiler` replaces
  `--compiler`).
- **Flag keys are appended:** `cflags`, `lflags`, `preproc`, `c_cflags`, `c_preproc` get the base, then the
  compiler's, then the system's (gfortran on Linux above: `-c -O2 -march=native`). A command-line `--cflags` comes
  last.
- **Any other key is replaced**, so two qualified keys replacing the same key that both apply (`ext_libs.gnu` and
  `ext_libs.linux` with gfortran on Linux) are an error, as is an unknown qualifier (exit 2).
- **They work in templates**, and `$variables` are substituted in them.
- **`introspect --buildoptions`** lists every qualified key, whether it applied, how (`appended`, `replaced`) and the
  value it gave.

Which mechanism: a **qualified key** when the value follows the compiler or the system by itself; a
**[varset](#choose-machine-paths-at-build-time-varsets)** when it follows the machine (a cluster's library paths, a
GPU architecture) and you choose it with `--varset`; a **named mode** when the build itself differs (another target, a
library, other sources). A build profile when the flags are the usual debug or release ones.

## Share settings between modes: templates

A template is any section a mode names in `template`; the mode gets every key of the template it does not set itself:

<<< @/examples/tutorial/2-growing/01-templates/files/fobos{ini}

<<< @/examples/output/2-growing/01/lmodes.txt{console}

- **Several templates:** `template = template-gnu template-mpi`. The mode wins over all of them, an earlier template
  over a later one.
- **Templates of templates** are expanded depth first: `[template-library]` above gets `[template-gnu]`'s keys after
  its own.
- **A template is not a mode** unless `[modes]` lists it.
- **Errors:** a circular reference (A -> B -> A), or a template that is not defined, stop the build (exit 1).

## Reuse values: variables

A key starting with `$`, in any section, defines a variable; `$NAME` in the selected mode's values (and what its
templates gave it) is replaced by its value. The fobos above uses `$PROGRAM`, `$LIBRARY` and `$OPT`.

- **Variables are global:** the section holding them does not matter (`[common-variables]` is a convention), except
  `[varset:NAME]` sections (next recipe). A variable defined twice takes the later value.
- **Plain text replacement**, several per value, no expressions; names are matched whole, so `$HDF5` and
  `$HDF5_PREFIX` coexist.
- **Do not build a variable from another:** `$A = -c $B` is replaced only when `$B` is defined after `$A` in the
  file.
- **A variable nobody defines** stays in the value as written (`$NAME`).

## Choose machine paths at build time: varsets

When modes would differ only in a few values (library prefixes, a GPU architecture), keep one mode and put the values
in named varsets:

```ini
[varsets]
default = local

[varset:local]
$HDF5 = /usr/lib/x86_64-linux-gnu/hdf5/serial

[varset:cluster]
$HDF5 = /opt/spack/hdf5-1.14.3
$ARCH = cc80

[solver]
compiler = nvfortran
cflags   = -c -fast -gpu=$ARCH
include  = $HDF5/include
lib_dir  = $HDF5/lib
ext_libs = hdf5_fortran hdf5
target   = src/solver.F90
```

```bash
fobis build --mode solver                        # [varsets] default: local
fobis build --mode solver --varset cluster
fobis build --mode solver --varset cluster,a30   # several: the last one wins on a name both define
fobis introspect --varsets                       # every varset, its bindings and the default
```

- **A varset's variables apply only when it is selected**, by `--varset` or by `[varsets] default` (a list too).
  They override the global variables of the same name.
- **`--varset` replaces the default**, it does not add to it.
- **The mode key `varset` is not applied** (the variables are substituted before the mode's keys are read): select
  varsets with `--varset` or `[varsets] default`.
- **Errors and warnings:** an undefined varset (on the command line or as the default) stops the build (exit 1) and
  lists the defined ones; a key without `$` is ignored with a warning; a varset whose keys all lack the `$`, a
  warning.
- **With other options:** `check`, `introspect` and `test` take `--varset` too; varsets and features compose
  (`--varset cluster --features prod`).

## Split a fobos into files

```ini
[include]
paths = templates.fobos
        ../shared/compilers.fobos
        ?fobos.local
```

The sections of the listed files are merged into the fobos before anything else, key by key. Typical uses: one file
per kind of section, compiler templates shared by sibling projects, and a git-ignored `fobos.local` with a
developer's own paths (`$HDF5 = /home/me/hdf5`).

- **Paths** are relative to the including file, after `${VAR}` and `~` expansion. A `?` prefix makes a file optional:
  silently skipped when missing; without it, a missing file stops the build (exit 1) and suggests the `?`.
- **Who wins:** the including file over its includes; among the includes, the later one. A key the parent does not
  set flows through.
- **Lists are merged:** `[modes] modes`, `[features] default` and `[varsets] default` get the names of every file.
- **Includes may include**, depth first, up to 16 levels; a cycle (a file including itself, directly or not) stops
  the build (exit 1). Two paths reaching the same file are not a cycle.
- **Everything works across files:** variables, templates, features, varsets.
- **One path per line, no comment after it:** words on the `paths` line are file names, so `?fobos.local ; mine`
  includes a file named `;`.
- **`.fobos` is a convention** for included files, not a rule. Includes have no parameters and no conditions: for
  values chosen at build time use varsets or features.

## Switch options on and off: features

A feature is a named set of flags, activated per build:

<<< @/examples/tutorial/2-growing/02-profiles/files/fobos{ini}

```bash
fobis build --mode debug                        # [features] default + the mode's features (checks)
fobis build --features hdf5,mpi                 # more, comma or space separated
fobis build --mode debug --features -checks     # drop one, wherever it came from
fobis build --no-default-features               # ignore [features] default
```

<<< @/examples/output/2-growing/02/unchecked.txt{console}

- **Active set:** `[features] default`, then the mode's `features`, then `--features`; a `-NAME` drops NAME after
  everything is expanded. The build prints `Active features: ...`.
- **Routing:** `-l...`, `-L...`, `-Wl,...` go to the link flags; an OpenMP flag (`-fopenmp`, `-qopenmp`, `-fiopenmp`,
  `-mp`, `-qsmp=omp`, `-openmp`) to both; anything else (`-D`, `-I`, `-O3`) to the compile flags, after the mode's
  and the command line's.
- **Implicit features** need no definition: `openmp` (`omp`), `mpi`, `coarray`, `coverage`, `profile`,
  `openmp_offload` (`omp_offload`) switch the compiler's own option, as `--openmp` does, for any family. They add no
  `-D` macro: pair them with a feature of your own (`omp_defs = -DUSE_OMP`). A definition in `[features]` replaces
  the implicit one.
- **Composites:** `prod = @release @hdf5 -DEXTRA` activates both features and adds its own flag. Only `@NAME`
  refers to a feature; a cycle is ignored with a warning.
- **Unknown names** and a `-NAME` matching no active feature give a warning, not an error.
- **The mode's `no_default_features` is not read**: only the command-line `--no-default-features` drops the default.

Constraints between features, in sections of their own:

```ini
[feature:hdf5]
requires = mpi

[feature:static]
flags     = -static
conflicts = shared

[feature-group:precision]
members = single double quad
default = double
```

- **`requires`** activates the others too, transitively (`Activating 'mpi' required by 'hdf5'.`).
- **`conflicts`** stops the build (exit 1) when both are active, naming the feature that pulled each one in.
- **A group** allows at most one active member (two stop the build, exit 1); with a `default`, exactly one: the
  default fills the group when no member is active, unless the default was dropped with `-NAME`.
- **`flags`** in `[feature:NAME]` is an alternative to the `[features]` line: two different flag sets for one feature
  are an error.

Features and profiles compose: `fobis build --build-profile debug --features hdf5`.

## Preprocessor macros

```ini
[debug]
compiler = gnu
cflags   = -c -O0 -g
preproc  = -DDEBUG -DUSE_MPI
src      = ./src/
```

`preproc` reaches every Fortran compile command, after `cflags`; files the compiler preprocesses are the usual
`.F90`, `.F` (or any file with `-cpp`). Groups of macros switched by name are [features](#switch-options-on-and-off-features).
The analysis commands evaluate `#if` lines with the mode's `-D` macros.

## Compile in parallel

```bash
fobis build --jobs 8
```

or `jobs = 8` in the mode. The files of one level of the dependency graph compile at once:

<<< @/examples/output/2-growing/05/jobs.txt{console}

The speed-up is bounded by the width of the graph: a chain of modules each using the previous one compiles serially
whatever `-j`. Tutorial: [rules and parallel compiling](/tutorial/growing/05-rules).

## What is compiled again

| Change | Recompiled |
|---|---|
| A source file | the file, and every file using its modules, directly or not |
| An included file | the files including it |
| A `.mod` from outside the project (a `dependon` project, a library), newer than an object | the files using it |
| The compiler (another path, or another `--version`) | everything, once |
| The flags | nothing, unless `cflags_heritage = True` |
| `--force-compile`, or `force_compile = True` in the mode | everything |

<<< @/examples/output/1-first-steps/01/touch.txt{console}

![automatic recompilation](/gifs/05_clean.gif)

*A build from scratch, a touched file compiled again, then `fobis clean`.*

The cascade follows timestamps: touching a low-level module recompiles every file above it, even when its interface
did not change.

## Rebuild after changing the flags

```ini
[template-gnu]
compiler        = gnu
src             = ./src/
cflags_heritage = True
```

or `--cflags-heritage` (`--ch`). The mode's compile flags (with the macros, and the C command when the mode sets a C
key) are saved in `<build_dir>/.cflags.heritage`, or `<build_dir>/.<target>.cflags.heritage` with a target; when the
next build's differ, everything is recompiled:

<<< @/examples/output/2-growing/02/unchecked.txt{console}

- **The file is written when the build starts**, before compiling: a build that fails after a flag change leaves the
  objects it did not reach with the old flags, and the next build no longer sees a change. Rerun with
  `--force-compile`.
- **Link flags are not compared.**

## Rebuild after changing the compiler

Nothing to do. Every build records, in `<obj_dir>/.fobis-compiler.json`, the compiler behind the mode's command: its
resolved path and the first line of its `--version` (and the C compiler's, with C files). When the next build finds
another one, typically a `module load` of another release that keeps the name `gfortran`, it prints
`The compiler changed since the last build (path '...' -> '...'; version '...' -> '...'): rebuilding everything`
and recompiles everything, instead of linking objects and reading `.mod` files of two compilers.

- **The record is written only after a build without compile failure**: a failed build leaves the next one forced.
- **No record** (the first build, objects of an older FoBiS): nothing is forced.

## Keep build products out of the sources

```ini
[release]
compiler  = gnu
cflags    = -c -O2
build_dir = ./build/release/
obj_dir   = obj/
mod_dir   = mod/
```

`obj_dir` and `mod_dir` (default `./obj/` and `./mod/`) are inside `build_dir` (default `./`); the program goes to
`build_dir`, named after its file or `output`. One `build_dir` per mode keeps the modes' objects apart.

```bash
fobis build --mode release --build-dir /scratch/me/quad    # wins over the mode's build_dir
```

Shadow builds (`--shadow`, in [Testing](./testing)) and the variants of `fobis assess` keep their objects under
`.fobis/`, apart from yours.

## Clean

```bash
fobis clean --mode debug        # objects, module files and the mode's program
fobis clean --only-obj          # objects and module files, keep the program
fobis clean --only-target       # the program, keep the objects
```

<<< @/examples/output/1-first-steps/02/clean.txt{console}

- **It reads the same mode as `build`**, so the same directories are cleaned: give it the same `--mode` and `-f`.
- **The program is removed only when there is a target** (the mode's `target`, or `--target`): without one, as in a
  build with no fobos, the programs stay (see the tutorial's
  [cleaning](/tutorial/first-steps/01-first-build#cleaning)).
- **Also removed:** `<build_dir>/.cflags.heritage` and the compilation database with its root link. The compiler
  record and a `.<target>.cflags.heritage` stay.
- `--only-obj` and `--only-target` exclude each other.

## Choose the sources

```ini
[release]
compiler     = gnu
cflags       = -c -O2
src          = ./src/
               ./vendor/lib/src/
exclude_dirs = ./src/experimental/
exclude      = old_solver.f90
```

```bash
fobis build --src ./src --src ./vendor/lib/src     # repeat the option for several
fobis build --exclude old_solver.f90 --disable-recursive-search
```

- **`src`** lists directories, walked recursively unless `disable_recursive_search = True`.
- **`exclude`** matches file names: `exclude = src/old_solver.f90` excludes every `old_solver.f90`.
- **`exclude_dirs`** excludes a directory and those below it: a directory is skipped when its path contains the
  given one, so `./src/old` also skips `./src/older`.
- **`extensions`** sets which files are read (default: every Fortran extension, the include extensions and `.c`); a
  mode setting it must list everything it wants, `.c` included.
- **Fetched dependencies** used as sources join `src` by themselves: see [Dependencies](./dependencies).

## Modules from outside the project

```ini
[release]
compiler          = nvfortran
cflags            = -c -O3
include           = /opt/hdf5/include
intrinsic_modules = hdf5 h5lt mpi_f08
```

A `use` of a module no project file defines warns `the file 'X' depends on 'NAME' that is unreachable` and is left
to the compiler, which must find `NAME.mod` in an `include` directory. `intrinsic_modules` silences the warning for
modules that come from outside (case-insensitive, for that mode). The standard intrinsics and the compiler's own
modules (`cudafor` with nvfortran, `ifport` with Intel, the list in [compilers](/guide/compilers)) are skipped
already. Libraries found through pkg-config or a wrapper: [Libraries and integration](./libraries).

## Fortran include files

`include 'kernel.inc'` makes the file depend on `kernel.inc`: changing it recompiles the files including it. Include
files (extensions `inc`, default `.inc .INC .h .H`) are never compiled; FoBiS finds them in the source directories
and the `include` directories, and passes their directory to the compiler.

## Files named alike

Two files with the same name in different directories (`lib/one/util.f90`, `lib/two/util.f90`) are both compiled and
linked: their objects are named after their path (`lib_one_util.f90.o`, `lib_two_util.f90.o`); a file whose name is
unique keeps `util.o`. Two programs named alike would write one executable: FoBiS warns; build each with its own
`--target` and `--output`.

## C files with the Fortran ones

```ini
[release]
compiler  = gnu
cflags    = -c -O2
c_cflags  = -c -O2 -std=c11
c_preproc = -DNDEBUG
src       = ./src/
```

`.c` files among the sources are compiled with the family's C compiler and linked into every program and library,
with nothing in the fobos naming them (a timer through `clock_gettime`, a wrapper of a C library called through
`bind(c)`). Tutorial: [a timer in C](/tutorial/growing/03-parallel#a-timer-in-c).

| `compiler` | C compiler | with `mpi` | OpenMP |
|---|---|---|---|
| `gnu`, `opencoarrays-gnu`, `nag` | `gcc` | `mpicc` | `-fopenmp` |
| `intel` | `icx` | `mpiicc -cc=icx` | `-qopenmp` |
| `intel_nextgen` | `icx` | `mpiicx` | `-qopenmp` |
| `nvfortran` | `nvc` | `mpicc` | `-mp` |
| `pgi` | `pgcc` | `mpicc` | `-mp` |
| `amd` | `amdclang` | `mpicc` | `-fopenmp` |
| `ibm` | `xlc_r` | `mpicc` | `-qsmp=omp` |
| `g95`, `lfortran`, `custom` | `gcc` (g95), `cc` | `mpicc` | none |

Measured: gcc 16 with gfortran, nvc 26.5 with nvfortran, icx 2026.1 with ifx 2025.3, Open MPI 5.0 `mpicc`; the
others are the vendors' documented names.

- **The Fortran flags never reach C.** `c_cflags` (default `-c`, added when missing) and `c_preproc` do; `cc` names
  another C compiler. `openmp`, `coverage` and `profile` add the C compiler's own flag; a build profile adds its C
  flags before `c_cflags`. A shared library needs `-fPIC` in both `cflags` and `c_cflags`.
- **Dependencies:** a C file is read for its `#include "..."` lines only (every one, whatever `#if` holds it); a
  project header that changes recompiles it. `#include <...>` headers are the system's. `"sys/clock.h"` is found by
  the end of its path, and the directory it is relative to joins the include path.
- **Headers:** a `.h` file written in C (a `/* */` comment, `typedef`, `extern`, `#include <...>`) is a C header:
  never compiled, never read as a Fortran include file.
- **Objects:** `clock.c` compiles to `clock.c.o`, so a `clock.f90` beside it keeps `clock.o`.
- **Errors:** a C file that does not compile fails the build (a Fortran file defining no module that fails is
  dropped from the link with a warning). `build --json` reports its error with file and line, `tool: "c"`.
- **Elsewhere:** the compilation database and the Makefile export have the C files; the compiler record holds the C
  compiler; `introspect --compiler` shows `cc` and `c_cflags`.
- **Left out:** `lint`, `query`, `review` and the other analysis commands, `--explain` (it stops at a C error),
  shadow modes and `assess` variants (Fortran flags only), and PreForM.

## Preprocess with PreForM or another tool

```ini
[gnu-preform]
compiler          = gnu
cflags            = -c -O2
preprocessor      = PreForM.py
preprocessor_ext  = .pfm .F90
preprocessor_dir  = pfm/
preprocessor_args = -DDEBUG
extensions        = .f90 .F90 .pfm
src               = ./src/
```

```bash
fobis build --preprocessor                      # PreForM.py on every Fortran file
fobis build --preprocessor fypp --npp           # another tool; --npp drops the -o before its output
fobis build --preprocessor --epp .pfm --dpp pfm/
```

Each selected file is passed through `preprocessor ARGS FILE -o <name>.pp.f90` and the result compiled; the
preprocessed file is deleted after compiling unless `preprocessor_dir` (`--dpp`, inside `build_dir`) keeps it.

- **`preprocessor_ext`** (`--epp`, repeatable) restricts the preprocessor to those extensions; without it every
  Fortran file goes through. C files never do.
- **A file must be read to be preprocessed:** a non-Fortran extension such as `.pfm` must be in `extensions` too.
- **`preprocessor_args`** (`--app`) go to the preprocessor; `preproc` goes to the compiler.
- **A preprocessor not on the PATH** is reported (`... is not in your PATH!`) and the compiles fail. [PreForM.py](https://github.com/szaghi/PreForM) expands templates
  and `cpp`-like directives.

## The build cache

```bash
fobis cache list                 # entries, with key, compiler, size and date
fobis cache show penf            # the entries of one dependency
fobis cache clean --older-than 30
fobis cache clean                # the whole cache directory
```

The cache directory is `~/.fobis/cache/` (`FOBIS_CACHE_DIR`, or `--cache-dir` on each subcommand), keyed by
`SHA-256(source commit | compiler | sorted cflags | FoBiS version)` for `use=fobos` dependencies.

- **Nothing fills it in this version:** neither `build` nor `fetch` stores or restores entries, and `--no-cache`,
  `--cache-dir` on `build`, and the mode keys `no_cache` and `cache_dir` change nothing. Incremental builds rely on
  timestamps alone.
- **Pins decide the code**, not the cache: a dependency's `tag=`/`rev=` in the fobos, and the lock file
  ([Dependencies](./dependencies)).

## Build and run

```bash
fobis run --mode release                  # build the mode, then run its program
fobis run --mode release -- input.nml     # arguments after -- go to the program, untouched
fobis run --no-build                      # run what the last build left
fobis run --dry-run                       # print the build and run commands
fobis run ./build/release/other           # build the mode, run this binary
```

<<< @/examples/output/1-first-steps/02/run.txt{console}

- **The program** is the mode's `output` (or its target's name) in its `build_dir`; the mode needs one of the two. A
  name given after `run` is the binary to start, not a target to build: the build is the mode's, whole.
- **Exit status:** the program's; a program killed by a signal gives 128 + the signal (139 for a segmentation fault).
  A failed build stops before running.
- **Launchers:** `--launcher "gdb --args"`, `--launcher "valgrind --error-exitcode=1"`, `--ranks 4` for
  `mpirun -np 4`; a mode can keep `launcher = mpirun -np {ranks}`. More in [HPC and clusters](./hpc).
- **`--shadow checks`** runs the mode rebuilt with runtime checks; **`--explain`** explains a crash
  ([AI assistance](./ai)).
- Unknown options before `--` are an error, not passed to the program.

## Check the dependency graph

```bash
fobis check                 # no compile: unresolved modules and includes, cycles
fobis check --strict        # any other analysis warning fails too
fobis check --json
```

<<< @/examples/output/2-growing/06/check.txt{console}

It scans the sources as `build` would (fetched and test-only dependencies included) and exits 1 on a `use` nothing
provides, an `include` no source directory holds, or files depending on each other in a cycle. A module found as a
`.mod` in an include directory, or defined by a `dependon` project, is provided. `fobis build` stops on a cycle with
the same message (`error: circular dependency: a -> b -> a`). A fast first step in CI: see
[Continuous integration](./ci).

## Inspect the resolved settings

```bash
fobis introspect --compiler --buildoptions --mode shared   # the flags as FoBiS will pass them
fobis introspect --sources                                 # every file: modules, uses, program, language
fobis introspect --all --format toml
fobis introspect --all --write                             # one .fobis-info/intro-*.json per section
```

<<< @/examples/output/2-growing/01/options.txt{console}

Sections: `--sources`, `--compiler`, `--dependencies`, `--targets` (the mode's program or library), `--include-dirs`,
`--buildoptions` (with the qualified keys), `--projectinfo`, `--varsets`, `--all`; `--varset` and `--shadow` apply
before resolving. A call with no section prints `{}`. `--compile-commands` prints the compilation database of the
mode, alone ([Libraries and integration](./libraries)).

Two build options leave files to look at: `--log` writes `<build_dir>/build_<file>.log` (the dependencies of each
built program), `--graph` its dependency graph (graphviz). `--verbose` is the most detailed output.
