---
title: Libraries and other build systems
---

# Libraries and other build systems

A mode can build a library instead of a program, install it with its module files, link libraries built elsewhere,
rebuild another FoBiS project before linking it, and run project commands as named rules. For the people and tools
that do not use FoBiS, the same fobos exports a GNU Makefile, an `fpm.toml` and a compilation database.

How it works:

1. **A library is a target and what it reaches.** `target` names the file of one module and `mklib` the kind,
   `static` or `shared`. The library holds that module, every module it reaches through `use`, and the files
   without modules (C files included); a module the target never reaches is left out.
2. **Archive or shared object.** A static library is `ar -rcs` then `ranlib`; a shared one is the link command with
   `-shared` added (the sources need `-fPIC` in `cflags`). Without `output` the file is
   `<build_dir>/<target stem>.a` (or `.so`), with no `lib` prefix.
3. **Module files travel with it.** A program using the library compiles against its `.mod` files
   (`<build_dir>/<mod_dir>`, `mod/` by default) and links the archive: `include` gives the first, `libs`, or
   `ext_libs` with `lib_dir`, the second.
4. **Linking runs at every build.** A program is linked again each time, so a changed library is always picked up.
   Recompiling follows the sources, and the `.mod` files of modules used from the include directories: a newer one
   recompiles the files using it.

Tutorial: [a library](/tutorial/first-steps/03-library),
[a library from another project](/tutorial/growing/04-dependon), [rules](/tutorial/growing/05-rules),
[other build systems](/tutorial/growing/07-export). Reference:
[`build`](/reference/build), [`install`](/reference/install), [`rule`](/reference/rule), [`fpm`](/reference/fpm),
[`introspect`](/reference/introspect).

## Build a static or shared library

One mode per kind, each with its own `build_dir`:

<<< @/examples/tutorial/1-first-steps/03-library/files/fobos{ini}

```bash
fobis build --mode static
fobis build --target src/mylib.f90 --mklib static --output libmylib.a    # the same from the command line
fobis new kit --lib                                                     # a new project laid out as a library
```

<<< @/examples/output/1-first-steps/03/static.txt{console}

<<< @/examples/output/1-first-steps/03/shared.txt{console}

<<< @/examples/output/1-first-steps/03/tree.txt{console}

![fobis build --mode static writes a static library](/gifs/03_static_library.gif)

*Recorded on a small demo project, not the tutorial's quad.*

- **Several modules, one library.** Only what the target reaches is archived. When the library has modules that do
  not use each other, make the target a module that uses them all (and re-exports them, if the users should need a
  single `use`).
- **Name the output.** `output = libquad.a` gives the `lib` prefix that `-lquad` looks for; `fobis rule
  --get-output-name` prints the path a mode writes.
- **One `build_dir` per library mode.** The `track_build` record is named after the target: two modes building the
  same target into one directory overwrite each other's.
- **A static library does not carry other libraries.** It holds the mode's objects only: `libs`, `vlibs` and
  `ext_libs` of a static mode stay out of it, and FoBiS warns that a program using it links them too. A shared
  library links them into the `.so`.
- **Programs linking a shared library** find it at run time through `LD_LIBRARY_PATH`, or through an rpath:
  `lflags = -Wl,-rpath,/opt/quad/lib`.

## Use another archiver

```ini
[llvm-static]
compiler  = gnu
cflags    = -c -O2
src       = ./src/
build_dir = ./build/llvm/
target    = src/mylib.f90
mklib     = static
output    = libmylib.a
ar        = llvm-ar
arflags   = -rcs
; empty: no ranlib step (llvm-ar writes the symbol table itself)
ranlib    =
```

```bash
fobis build --mode static --ar llvm-ar --ranlib ""
```

`ar`, `arflags` and `ranlib` default to `ar`, `-rcs` and `ranlib`, for cross toolchains and vendor archivers alike.
The archiver in use is printed in the builder settings (`Archiver: ar -rcs`).

## Install what a mode built

`track_build = True` (or `--track-build`) records what the build produced in `<build_dir>/.<target>.track_build`;
`fobis install` copies it to a prefix: programs to `bin/`, libraries to `lib/`, module files to `include/`.

```bash
fobis build --mode static
fobis install --mode static --prefix ~/opt/quad
```

<<< @/examples/output/1-first-steps/03/install.txt{console}

![a tracked build installed to a prefix](/gifs/06_install.gif)

*Recorded on a small demo project, not the tutorial's quad.*

- **Every module of the library is installed:** the target's and those of the files it uses (`.mod` files, named in
  lower case as compilers write them).
- **The sub-directories:** `--bin`, `--lib`, `--include` given on the command line, else the mode's `bin` and `lib`
  keys, else `bin/`, `lib/`, `include/`. A mode's `include` is its build's search path, never the install's.
- **Build first.** Without the build directory `fobis install` stops: `Error: build directory not found!` (exit 1).

Cloning, building and installing a project from GitHub in one command: [Dependencies](./dependencies).

## Publish a pkg-config file

`pkgconfig = True` in a library mode makes FoBiS write a pkg-config file for it: one for using the library where it
was built, one for its installed copy.

```ini
[project]
name    = quad
version = v0.1.0
summary = Quadrature rules

[static]
compiler    = gnu
cflags      = -c -O2
src         = ./src/
build_dir   = ./build/static/
target      = src/quad_rules.F90
mklib       = static
output      = libquad.a
track_build = True
pkgconfig   = True
; Requires: and Requires.private: of the file
pkgconfig_req_priv = zlib
```

```bash
fobis build --mode static                        # writes build/static/quad.pc: the build tree
fobis install --mode static --prefix ~/opt/quad  # writes ~/opt/quad/lib/pkgconfig/quad.pc
PKG_CONFIG_PATH=~/opt/quad/lib/pkgconfig pkg-config --cflags --libs quad
```

The second prints `-I/home/me/opt/quad/include -L/home/me/opt/quad/lib -lquad`: a program using the library compiles
and links with these flags alone.

- **The fields:** `Name` is `pkgconfig_name`, else `[project] name`, else the library's name; `Description` is
  `pkgconfig_desc`, else `[project] summary`; `URL` is `pkgconfig_url`, else `[project] repository`; `Version` is the
  project's version without a leading `v`. `pkgconfig_req` and `pkgconfig_req_priv` fill `Requires` and
  `Requires.private`.
- **The paths are absolute:** `prefix` is the build directory or the install prefix; `Cflags` names the module
  directory (`include/` once installed, `--include` renames it).
- **A library named `libNAME`** is linked with `-L... -lNAME`; any other name (a mode without `output` builds
  `NAME.a`) is linked by its path, which `-l` could not find.
- **Libraries only:** a mode without `mklib` writes no file.

## Link an installed or system library

<<< @/examples/tutorial/1-first-steps/03-library/consumer/fobos{ini}

<<< @/examples/output/1-first-steps/03/consumer.txt{console}

```bash
fobis build --libs /opt/foo/libfoo.a --include /opt/foo/mod              # a library by its full path
fobis build --ext-libs foo --ext-libs bar --lib-dir /opt/lib             # by name: -L/opt/lib -lfoo -lbar
```

- **`libs`** are full paths, linked as given; **`ext_libs`** are names, linked as `-l<name>` and searched in the
  `lib_dir` directories (`lib<name>.a` or `lib<name>.so`).
- **`include`** is searched for `.mod` files and included files. A module found there is not compiled: FoBiS does
  not look for it among the sources.

## Find MPI, HDF5, NetCDF, BLAS, FFTW

Declare the libraries once in `[externals]`, then list in each mode the ones it uses:

```ini
[externals]
mpi    = auto
hdf5   = auto
netcdf = auto
fftw   = auto
; an explicit prefix: -I/opt/openblas/include -L/opt/openblas/lib -lblas
blas   = /opt/openblas

[release]
compiler  = gnu
cflags    = -c -O2
src       = ./src/
externals = hdf5 blas
```

`auto` probes the environment at every build:

- `mpi`: `mpifort`, `mpif90`, `mpiifort`, `mpiifx` with `--showme:compile`/`--showme:link` (Open MPI), else `-show`
  (MPICH, Intel MPI), else `pkg-config ompi-fort`;
- `hdf5`: `pkg-config hdf5_fortran`, else `h5pfc -show` or `h5fc -show`;
- `netcdf`: `nf-config` or `nc-config` (`--fflags`, `--flibs`), else `pkg-config netcdf`;
- `blas` (`pkg-config blas`, else `openblas`), `openblas`, `lapack`, `fftw` and `fftw3` (`pkg-config fftw3`).

An explicit prefix adds `<prefix>/include` and `<prefix>/lib` (when they exist) and the package's usual library
names: `-lhdf5_fortran -lhdf5`, `-lnetcdff -lnetcdf`, `-lfftw3`, `-lmpi_usempif08 -lmpi_mpifh -lmpi`; any other
name links `-l<name>`. The compile flags found are appended to `cflags`, the link flags to `lflags`, and the include
and library directories to `include` and `lib_dir`. From a wrapper's `-show` only `-I`/`-D` and `-L`/`-l` words are
kept.

- **A library not found is a warning, not an error:** `Warning: could not auto-detect external 'hdf5'`, and the build
  goes on without its flags, to fail later at compile or link time.
- **Only the names above can be probed.** Another name with `auto` (or listed in the mode but absent from
  `[externals]`) gives `Warning: no probe strategy for external 'NAME'`: give it a prefix.
- **`mpi = True` is another thing:** it compiles with the MPI wrapper as the compiler. `externals = mpi` keeps the
  plain compiler and adds the MPI flags.
- **Composes with feature flags.** A feature supplies the macro (`hdf5 = -DUSE_HDF5` in `[features]`), the external
  the include and link flags of the same library ([building](./build)).

## Recompile everything when a library changes

A library rebuilt elsewhere (a nightly CI artefact, a colleague's checkout) changes under objects compiled against
it. A volatile library is hashed at every build; when its MD5 differs from the last build's, everything is
recompiled:

```ini
[default]
compiler  = gnu
cflags    = -c -O2
; by full path
vlibs     = /shared/ci/libfoo.a
; by name: lib<name>.a, else lib<name>.so, in each lib_dir
lib_dir   = /shared/ci/
ext_vlibs = bar
include   = /shared/ci/mod/
```

```bash
fobis build --vlibs /shared/ci/libfoo.a --include /shared/ci/mod/
```

```text
The volatile library /shared/ci/libfoo.a is changed with respect the last building: forcing to (re-)compile all
```

- **The hash lives in the build directory**, as `.<library file name>.md5`. The first build only records it.
- **A missing volatile library** is reported (`The volatile library ... is not found!`) and the link then fails, as
  for any library.
- **When you need it.** The link step already runs at every build, and a newer `.mod` from an include directory
  already recompiles its users. A volatile library adds a full recompile on any change of the library's bytes: for
  libraries whose module files you do not have, or whose changes the `.mod` times do not show.

## Build another FoBiS project first

`dependon` names the fobos of a library project: FoBiS builds it (in its own directory, with its own fobos and mode)
before building this one, then adds its module directory to `include` and links its library.

<<< @/examples/tutorial/2-growing/04-dependon/area/fobos{ini}

<<< @/examples/output/2-growing/04/touch.txt{console}

```bash
fobis build --dependon "../quad/fobos:static((direct))"     # quoted: the shell reads the parentheses
```

The form is `PATH/fobos[:MODE][((direct|indirect))]`, the two suffixes in either order, several entries separated by
spaces:

- **`:MODE`** selects the dependency's mode, else its default mode. It must be a mode that builds a library: its
  output is what gets linked.
- **`((direct))`** (the default) links the library by its full path (`libs`); **`((indirect))`** links it by name,
  its build directory added to `lib_dir` (`ext_libs`).
- **The path is relative to the fobos that writes it**, as a `path=` dependency's; given with `--dependon`, to the
  directory you run `fobis` in. The mode's other paths (`src`, `build_dir`, ...) are relative to that directory.
- **The dependency is built every time** (an up-to-date one compiles nothing); its build failing stops this one with
  its exit status. `--quiet` is passed on.
- **Only `fobis build` builds it.** `fobis check` treats the modules of `dependon` projects as provided. A Makefile
  export builds the dependency too, then writes the Makefile.

![dependon builds the library project first, then links it](/gifs/04_dependent_build.gif)

*Recorded on a small demo project, not the tutorial's quad.*

The same without the link syntax, from a directory or a git repository: `[dependencies]` with `use=fobos`, in
[Dependencies](./dependencies).

## Run project commands as rules

A `[rule-NAME]` section holds shell commands, run by `fobis rule --execute NAME`:

```ini
[rule-smoke]
help = The last line of the program's output
rule = ./build/release/integrate | tail -n 1

[rule-dist]
help     = A source archive
rule_rm  = rm -f quad-0.1.0.tar.gz
rule_tar = tar czf quad-0.1.0.tar.gz fobos src test
```

```bash
fobis rule --list                   # the rules, their help and commands
fobis rule --execute dist           # --ex for short
```

<<< @/examples/output/2-growing/05/list.txt{console}

<<< @/examples/output/2-growing/05/dist.txt{console}

- **Every key starting with `rule` is a command**, run in the order written, each in a shell. Keys of one section
  must differ (`rule_rm`, `rule_tar`): an INI file keeps one value per key.
- **All commands run, even after one fails;** the rule then reports the failed output and exits 1. Successful
  output is printed when all are done. Chain with `&&` in one command when a step depends on the previous one.
- **`$variables`** of the fobos are substituted in the commands at execution (`fobis rule --list` shows them
  unsubstituted).
- **`quiet = True`** hides the rule's commands from the execution and the listing; **`log = True`** appends failed
  output to `rules_errors.log`.
- **An unknown rule** prints `Error: the rule "NAME" is not defined into the fobos file` and the list of rules, and
  exits 1.

## Run rules before and after a build

```ini
[release]
help          = Optimised
template      = template-gnu
build_profile = release
cflags        = -c
post_build    = smoke
build_dir     = ./build/release/
target        = $PROGRAM
```

```bash
fobis build --mode release --post-build smoke      # the option form; --pre-build likewise
```

<<< @/examples/output/2-growing/05/release.txt{console}

`pre_build` and `post_build` (keys or options) name rules, several separated by spaces; `post_build` runs only after
a successful build. A name with no `[rule-NAME]` section stops the build before it starts (exit 1). A Makefile
export runs neither.

## Ask the fobos from a script

```bash
fobis rule --mode release --get build_dir           # any key of the mode, templates and $variables applied
fobis rule --mode static --get-output-name          # build_dir + output, or the target's stem + .a/.so
EXE=$(fobis rule --mode release --get-output-name)
fobis rule --is-float128-kind-supported             # also --is-ascii-kind-supported, --is-ucs4-kind-supported
```

<<< @/examples/output/2-growing/05/float128.txt{console}

- **`--get`** prints an empty line for a key the mode does not set; without `--mode` it reads the default mode (the
  first of `[modes]`).
- **The kind checks** compile and run a small program with the mode's compiler, in its build directory.
- **`--ford PROJECT.md`** runs FORD on a project file, and exits 1 when FORD fails or is not installed.
- **`--gcov-analyzer DIR [--gcov-analyzer SUMMARY]`** reads every `.gcov` file under the current directory and
  writes `DIR/<file>.gcov.md` for each, plus `DIR/SUMMARY.md` with tables and Mermaid pie charts. `fobis coverage`
  is the complete report: [Testing](./testing).

## Export a GNU Makefile

```bash
fobis build --mode release --makefile Makefile      # writes the Makefile, compiles nothing
```

<<< @/examples/output/2-growing/07/makefile.txt{console}

<<< @/examples/output/2-growing/07/make.txt{console}

![fobis build -m Makefile exports a GNU Makefile that make builds](/gifs/08_makefile_export.gif)

*Recorded on a small demo project, not the tutorial's quad.*

The Makefile holds the mode's compiler, flags, directories and libraries, and one compile rule per scanned source
with its dependencies written out, so `make` orders nothing itself. Its default goal is the mode's target (named as
`fobis build` names it); without a target, a rule per program. `make cleanobj`, `cleanmod`, `cleanexe`, `clean`
(objects and modules) and `cleanall` remove what it built.

- **Libraries too:** a static library mode exports an archive rule with the mode's `ar`, `arflags` and `ranlib`, a
  shared one a link with its `-shared` flags; the library is named as `fobis build` names it.
- **Without a target, every program gets a rule,** named after its file as `fobis build` names it.
- **The link takes every object of the object directory** (`$(DOBJ)*.o`) after deleting the other programs'.
- **A snapshot.** Generate it again when the fobos or the sources change, with a rule for instance.

## Translate to and from fpm

`fobis fpm` translates between an `fpm.toml` and a fobos, keeps what the other side can express, and prints the
rest as notes:

```bash
fobis fpm import                                    # fpm.toml -> fobos, fpm's flags for gfortran
fobis fpm import --compiler intel_nextgen --output fobos.ifx --force
fobis fpm export --mode release                     # fobos + the sources -> fpm.toml
fobis fpm import --print                            # print the translation, write nothing
```

Neither overwrites an existing file without `--force` (exit 2 then, as for a missing or unreadable input); `--json`
prints the text, the notes and the file written.

### Import: build an fpm package with FoBiS

The import translates the whole build configuration for one compiler (`--compiler`, default `gnu`) on the operating
system it runs on: each file compiles with the flags `fpm build` gives it.

| fpm.toml | fobos |
|----------|-------|
| `name`, `version`, `author`, `description`, `homepage` | `[project]` name, version, authors, summary, repository |
| `[library] source-dir` (default `src`), executables, tests, examples (declared or `app/`, `test/`, `example/`) | `src` of every mode |
| `[library] include-dir` | `include` |
| each profile, plus `debug` and `release` | a mode `<compiler>-<profile>` listing its `features` |
| each feature | a `[feature:NAME]` with its flags for that compiler and OS |
| the `[fortran]` table (defaults included), cpp in use | the template's `cflags` (`-fPIC` too for ifort/ifx) |
| `[library] type` | modes `lib-static`, `lib-shared` (`-fPIC`), target = the module named after the package |
| test directory | `[test] test_dir` |
| git dependencies (`tag`, `branch`, `rev`) | `[dependencies]`, for `fobis fetch` |
| path dependencies, and theirs | `name = path=DIR/<its source-dir>` |
| `[dev-dependencies]` | the same, with `:: dev` |
| `mpi = "*"`, `openmp = "*"` | `mpi = True`, `openmp = True`; inside a feature `@mpi`, `@openmp` |
| `[build] link` | `ext_libs` |
| `[preprocess.cpp] macros` (`NAME={version}` expanded) | `preproc = -D...`, `c_preproc` for C files |
| C files, `c-flags` | built by FoBiS, `c_cflags` |
| `link-time-flags` of a profile's features | the mode's `lflags` |

```bash
fobis build --mode gnu-debug                        # one mode per profile: gnu-debug, gnu-release, gnu-<profile>
fobis test --mode gnu-debug
fobis build --mode lib-static
fobis build --mode gnu-release --features checks    # any imported feature, as any FoBiS feature
```

A feature is merged as fpm merges it: the part for all platforms, then each matching variant (per compiler
`name.gfortran.flags`, per OS `name.linux.flags`, or both) in the manifest's order:

```toml
[features]
checks.flags = "-g"
checks.gfortran.flags = "-fcheck=all"
checks.ifx.flags = "-check all"
checks.linux.preprocess.cpp.macros = "ON_LINUX"
[profiles]
careful = ["checks"]
```

```ini
[gnu-careful]
template  = template-common
features  = checks
build_dir = ./build/careful/

[feature:checks]
flags = -g -fcheck=all -DON_LINUX
```

- **`debug` and `release` always exist**, as in fpm: the manifest's `debug`/`release` features when it defines them,
  fpm's built-in flags otherwise (for gfortran `-Wall -Wextra -Wimplicit-interface ... -g -fcheck=bounds ...`, fpm
  `5fa4649`, February 2026). The `default` profile's features come first in those two only.
- **The `[fortran]` defaults reach every Fortran compile:** for gfortran `-fimplicit-none
  -Werror=implicit-interface -ffree-form`, plus `-cpp` when the manifest uses cpp anywhere.
- **Features named like FoBiS's own** (`openmp`, `omp`, `mpi`, `coarray`, `coverage`, `profile`, `openmp_offload`,
  `omp_offload`, `default`) are renamed `fpm-NAME`.
- **No library mode** when no module is named after the package: a note says so (FoBiS builds a library from one
  target module).
- **One compiler per import.** The notes name the features with flags for other compilers and the `--compiler` value
  that imports them (`intel_nextgen` for ifx).
- **One flag set per build.** A dependency compiled with the project (a path dependency, or a git one with
  `use=sources`) gets the project's macros; fpm gives each package its own.
- **Notes list what is not translated:** registry versions and other metapackages, `external-modules`, an unknown
  `source-form`, a feature's parts that are not flags (executables, dependencies other than `mpi`/`openmp`,
  `build`, `install`), a profile naming a missing feature, `[profiles]` in the old table syntax, flags for another
  OS.

Checked against fpm 0.13.0 built from its sources (`5fa4649`): ten of fpm's example packages and a mixed C/Fortran
fixture compiled in every profile with the same flags per file (as sets: fpm repeats some), with gfortran and gcc,
ifx 2025.3 and nvfortran 26.5. FLAP's manifest (70 tests, two git dependencies) imported: `fobis fetch`,
`fobis build --mode lib-static`, and `fobis test --mode gnu-debug` passed the 70 tests with fpm's flags. Without
Python's `tomllib` (before 3.11) FoBiS reads the manifest with its own TOML reader, equal to `tomllib` on 14 real
manifests.

### Export: give fpm users a manifest

<<< @/examples/output/2-growing/07/fpm.txt{console}

The manifest comes from the fobos and the analysis of the mode's sources (default: the first mode), the fetched
dependencies left out:

- `[library] source-dir` is the common directory of the files holding modules, with a note when it also holds
  programs: fpm compiles every file there into the library;
- programs under the `[test]` directory (else under a `test`/`tests` directory) are `[[test]]`, the others
  `[[executable]]`, each named after its program (after its file when names repeat); `auto-*` discovery is off;
- `[dependencies]` are the fobos's, as git dependencies with their pin, a path dependency as `{ path = "..." }`;
  `mpi`/`openmp` `"*"` when the mode uses them; the mode's `-D` macros go to `[preprocess.cpp] macros`;
- the version is `[project] version` (a version file is read), without a leading `v`.

Modes, templates, flags and rules are not exported: fpm uses its own profiles. StringiFor's export (151 tests, three
git dependencies) built with fpm 0.12.0.

## Give editors the compile commands

```ini
[release]
compiler         = gnu
cflags           = -c -O2
src              = ./src/
build_dir        = ./build/release/
compile_commands = True
```

```bash
echo compile_commands.json >> .gitignore
fobis build --mode release --compile-commands            # the same as the key
fobis introspect --compile-commands --mode debug         # another mode's database, printed: nothing built or written
```

`compile_commands.json` lists, for every source of the build, the directory the command runs in, the file, the
exact compile command as a list of words and the object it writes: language servers, editors and analysers
read the include and module directories, macros and flags from it.

- **Written before compiling**, after the dependency analysis, so it exists when the build fails; rewritten only
  when its content changes; complete in an incremental build; included files have no entry; with a separate
  preprocessor the entry names the original source.
- **In the build directory, linked from the root** (`./compile_commands.json`, a relative link, a copy where links
  are not available). A root file FoBiS did not write is never replaced (a warning says so); builds under `.fobis/`
  (shadow builds, assess variants) leave the root alone; `[target.NAME]` sections of one run share one database.
- **Off by default:** a new file in the root breaks clean-tree checks (release scripts, `fobis ecosystem release`)
  until `.gitignore` names it. `fobis clean` removes the database and the link.
