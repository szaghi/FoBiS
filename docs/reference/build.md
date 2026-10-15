# `build` command

Build all programs found in the source tree, or a specific target.

```bash
fobis build [options]
```

## Compiler options

| Option | Description |
|---|---|
| `--compiler {gnu,intel,intel_nextgen,g95,opencoarrays-gnu,pgi,ibm,nag,nvfortran,amd,lfortran,custom}` | Compiler (case-insensitive, default: `gnu`) — tab-completable |
| `--fc FC` | Compiler executable — required for `--compiler custom` |
| `--cflags CFLAGS` | Compilation flags |
| `--lflags LFLAGS` | Linking flags |
| `--modsw MODSW` | Module path switch — required for `--compiler custom` |
| `--mpi` | MPI compiler variant |
| `--openmp` | OpenMP |
| `--openmp-offload` | OpenMP offload |
| `--coarray` | Coarrays |
| `--coverage` | Coverage instrumentation |
| `--profile` | Profiling instrumentation |
| `--mklib {static,shared}` | Build a library instead of a program (use with `-t`) — tab-completable |
| `--ar AR` | Archiver executable for static libraries (default: `ar`) |
| `--arflags ARFLAGS` | Archiver flags (default: `-rcs`) |
| `--ranlib RANLIB` | Ranlib executable for indexing static libraries (default: `ranlib`); set to empty string to skip |
| `--ch`, `--cflags-heritage` | Track flag changes; force full rebuild when they differ |
| `--tb`, `--track-build` | Save build info for use by `install` |

## Compiler changes

Objects are recompiled when their sources changed (timestamps). Independently, every build records the compiler
behind the mode's command (its resolved path and the first line of its `--version`) in
`<obj_dir>/.fobis-compiler.json`; when the next build finds another compiler there — typically a `module load`
of another release that keeps the command name `gfortran` — it says so and recompiles everything, instead of
linking objects (and reading `.mod` files) of two compilers:

```text
The compiler changed since the last build (path '/usr/bin/gfortran' -> '/opt/gcc/bin/15.2.0/bin/gfortran';
version 'GNU Fortran ... 16.0.1 ...' -> 'GNU Fortran (GCC) 15.2.0'): rebuilding everything
```

The record is written only after a build that compiled without failure, so a failed build leaves the next one
forced. Without a record (the first build, or objects built by an older FoBiS) nothing is forced. Flag changes
are tracked separately with `--cflags-heritage`.

## Directory options

| Option | Default | Description |
|---|---|---|
| `-s`, `--src` | `./` | Root source directory (repeatable: `--src ./a --src ./b`) |
| `--dbld`, `--build-dir` | `./` | Build output directory; given on the command line it wins over the mode's `build_dir` (a build apart from the mode's tree) |
| `--dobj`, `--obj-dir` | `./obj/` | Compiled objects directory |
| `--dmod`, `--mod-dir` | `./mod/` | Module interface files directory |
| `--dlib`, `--lib-dir` | — | Library search directories (repeatable) |
| `-i`, `--include` | — | Include file search directories (repeatable) |
| `--ed`, `--exclude-dirs` | — | Directories to exclude from the build (repeatable) |
| `--drs`, `--disable-recursive-search` | `False` | Do not recurse into subdirectories |

## File options

| Option | Default | Description |
|---|---|---|
| `-t`, `--target` | All programs found | Specific target source file |
| `-o`, `--output` | Basename of target | Output executable name |
| `-e`, `--exclude` | — | Source files to exclude (repeatable) |
| `--libs` | — | External libraries (full paths, repeatable) |
| `--vlibs` | — | Volatile external libraries (full paths) — triggers rebuild on change |
| `--ext-libs` | — | External libraries (by name, in linker path) |
| `--ext-vlibs` | — | Volatile external libraries (by name) |
| `--dependon` | — | Interdependent fobos files (`path/fobos[:mode]`, repeatable) |
| `--inc` | `.inc .INC .h .H` | Include file extensions — tab-completable |
| `--extensions` | (all Fortran extensions) | Parsed file extensions — tab-completable |
| `--build-all` | `False` | Build all parsed sources, not just program files |

## fobos options

| Option | Description |
|---|---|
| `-f`, `--fobos` | Specify a fobos file with a different name or path |
| `--fci`, `--fobos-case-insensitive` | Case-insensitive fobos option parsing |
| `--mode` | Select a fobos mode — tab-completable from the active fobos file |
| `--shadow NAME` | Rebuild the mode as a [shadow](/advanced/matrix#shadow-modes): `checks`, `sanitize`, `strict` (or `none`), in `.fobis/shadow/<mode>-<shadow>/` |
| `--lmodes` | List available modes and exit |

## Preprocessor options

| Option | Description |
|---|---|
| `--preprocessor CMD` | Enable source preprocessing; specify preprocessor name (e.g. `PreForM.py`) |
| `--preproc` | Preprocessor flags for the main compiler |
| `--app`, `--preprocessor-args` | Flags passed to the preprocessor |
| `--npp`, `--preprocessor-no-o` | Omit `-o` from the preprocessor command line |
| `--dpp`, `--preprocessor-dir` | Directory for preprocessed sources (kept if set) |
| `--epp`, `--preprocessor-ext` | File extensions to preprocess (repeatable) |

## Build profile options

| Option | Description |
|---|---|
| `--build-profile {debug,release,asan,coverage}` | Apply a named compiler flag preset (see [Build Profiles](/advanced/build-profiles)) |
| `--list-profiles` | Print the full built-in flag table and exit |

## Feature flag options

| Option | Description |
|---|---|
| `--features NAMES` | Comma- or space-separated list of features to activate. Prefix a name with `-` to deactivate (e.g. `prod,-coverage`). See [Feature Flags](/advanced/features) for composites (`@`-references), `[feature:NAME]` constraints, and `[feature-group:NAME]` mutual exclusivity. |
| `--no-default-features` | Suppress the `default =` entry in `[features]`. Mode-level `features =` and CLI activations still apply. |

## Varset options

| Option | Description |
|---|---|
| `--varset NAMES` | Apply one or more `[varset:NAME]` sections' `$variable` bindings to the active mode. Comma- or space-separated; later varsets override earlier ones (last write wins). Overrides any `[varsets] default = ...` declared in the fobos. See [Varsets](/advanced/varsets). |

## Build cache options

| Option | Description |
|---|---|
| `--no-cache` | Disable the build cache for this invocation |
| `--cache-dir DIR` | Override the cache directory (default: `.fobis_cache`) |

## Multi-target options

| Option | Description |
|---|---|
| `--target-filter NAME` | Build only the named `[target.NAME]` or `[example.NAME]` section |
| `--examples` | Build all `[example.*]` sections defined in the fobos file |

## Hook options

| Option | Description |
|---|---|
| `--pre-build CMD` | Shell command to run before the build starts |
| `--post-build CMD` | Shell command to run after a successful build |

## Auto-discovery options

| Option | Description |
|---|---|
| `--no-auto-discover` | Disable convention-based source directory detection (`src/`, `source/`, `app/`) |

## External libraries

External libraries (MPI, HDF5, NetCDF, BLAS/LAPACK, FFTW, …) are configured in the
fobos file, not via CLI flags: declare them in an `[externals]` section and activate
them per mode with `externals = name1 name2`. FoBiS resolves their compile/link flags
automatically (via `pkg-config`, `nf-config`, `mpifort -show`, or an explicit prefix).
See [External Libraries](/advanced/externals) for the full mechanism and for generating
a `pkg-config` `.pc` file for your own project.

## Fancy options

| Option | Description |
|---|---|
| `--force-compile` | Force recompilation of all sources |
| `--colors` | Coloured terminal output |
| `-l`, `--log` | Write a build log file |
| `--graph` | Generate a graphviz dependency graph |
| `-q`, `--quiet` | Less verbose output |
| `--verbose` | Maximum verbosity (for debugging FoBiS.py itself) |
| `-j`, `--jobs` | Number of parallel compile jobs (default: 1) |
| `-m`, `--makefile` | Export a GNU Makefile instead of building |
| `--json` | Emit structured JSON to stdout (see [JSON output](/advanced/json-output)) |

## Compilation database

| Option | Description |
|---|---|
| `--compile-commands` | Write the compilation database `compile_commands.json` (opt-in; mode key `compile_commands = True`) |

The compilation database lists, for every source file of the build, the directory the command runs in, the file,
the exact compile command (as a list of words) and the object it writes:

```json
[
  {
    "directory": "/home/me/quad",
    "file": "/home/me/quad/src/quad_rules.F90",
    "arguments": ["gfortran", "-c", "-O2", "-J", "build/mod", "-Ibuild/mod", "src/quad_rules.F90",
                  "-o", "build/obj/quad_rules.o"],
    "output": "/home/me/quad/build/obj/quad_rules.o"
  }
]
```

Editors, language servers and static analysers read it to learn how each file is compiled: include directories,
module directory, `-D` macros, flags. With it on, FoBiS writes it:

- in the build directory, after the dependency analysis and **before** compiling, so it exists even when the build
  fails, and rewritten only when its content changes;
- with an entry for every compiled source, not only those compiled this time (an incremental build keeps it
  complete); included files have none;
- naming the original source when a separate preprocessor (`--preprocessor`) produces the file actually compiled;
- linked from the project root (`./compile_commands.json`, a relative link, or a copy where links are not
  available), where most tools look for it. A `compile_commands.json` in the root that FoBiS did not write is never
  replaced. Builds kept under `.fobis/` (shadow builds, `fobis assess` variants) write their own database and leave
  the root alone; the `[target.NAME]` sections of one run share one database.

`fobis clean` removes the database and the root link to it. The database is off by default because a new file in
the root makes clean-tree checks (release scripts, `fobis ecosystem release`) fail until the project's `.gitignore`
names it: add `compile_commands.json` to `.gitignore` when turning it on. `fobis introspect --compile-commands`
prints the same database for any mode without building or writing anything.

## Explain options

| Option | Description |
|---|---|
| `--explain` | When the build fails, explain why: from the project's facts (missing modules, unlinked objects, objects of another compiler, internal compiler errors), then with the LLM (cited cause and fix) for the first error they do not cover. See [Explaining build failures](/ai/explain) |
| `--explain-context` | Like `--explain`, but print what the model would receive instead of running it |

## Examples

```bash
# Build all programs with defaults
fobis build

# Build with GNU gfortran, parallel, debug flags
fobis build --compiler gnu --cflags "-c -O0 -g" -j 4

# Build a specific target
fobis build -t src/solver.f90 -o solver

# Build a static library
fobis build -t src/mylib.f90 --mklib static -o libmylib.a

![Static library build demo](/gifs/03_static_library.gif)

# Build a static library with LLVM tools
fobis build -t src/mylib.f90 --mklib static --ar llvm-ar --ranlib llvm-ranlib

# Build a static library skipping ranlib (llvm-ar updates the symbol table itself)
fobis build -t src/mylib.f90 --mklib static --ar llvm-ar --ranlib ""

# Use a fobos file and a specific mode
fobis build -f project.fobos --mode release

# Force full recompile
fobis build --force-compile

# Multiple source directories
fobis build --src ./src --src ./vendor/mylib/src
```

![dependon build demo](/gifs/04_dependent_build.gif)

::: tip Legacy single-dash options
All single-dash multi-character options from older versions (`-compiler`, `-mode`, `-force_compile`, etc.) are still accepted and normalised automatically. Both forms are equivalent:
```bash
fobis build -compiler intel -mode release   # legacy style
fobis build --compiler intel --mode release  # current style
```
:::

<!-- cli:begin -->
<!-- generated by docs/scripts/gen_cli_reference.py from the command line: do not edit -->

## All options

| Option | Value | Default | Description |
|---|---|---|---|
| `--fobos`, `-f` | TEXT |  | Specify a "fobos" file named differently from "fobos" |
| `--fci` |  |  | Assume fobos inputs as case insensitive |
| `--mode` | TEXT |  | Select a mode defined into a fobos file |
| `--lmodes` |  |  | List the modes defined into a fobos file |
| `--shadow` | TEXT |  | Rebuild the mode as a shadow (checks, sanitize or strict): the mode's settings with checking flags, in its own build directory (.fobis/shadow/&lt;mode&gt;-&lt;shadow&gt;/). |
| `--compiler` | TEXT | `gnu` | Compiler used (case insensitive, default gnu) |
| `--fc` | TEXT |  | Fortran compiler statement (for --compiler custom) |
| `--cflags` | TEXT |  | Compile flags |
| `--lflags` | TEXT |  | Link flags |
| `--cc` | TEXT |  | C compiler for the .c sources (default: the compiler family's, e.g. gcc) |
| `--c-cflags` | TEXT |  | Compile flags of the .c sources (default -c) |
| `--c-preproc` | TEXT |  | Preprocessor flags of the .c sources |
| `--modsw` | TEXT |  | Module search path switch (for --compiler custom) |
| `--mpi` |  |  | Use MPI enabled version of compiler |
| `--openmp` |  |  | Use OpenMP pragmas |
| `--openmp-offload` |  |  | Use OpenMP Offload pragmas |
| `--coarray` |  |  | Use coarrays |
| `--coverage` |  |  | Instrument for coverage analysis |
| `--profile` |  |  | Instrument for profiling analysis |
| `--mklib` | TEXT |  | Build library instead of program (static\|shared) |
| `--ar` | TEXT | `ar` | Archiver executable for static libraries [default: ar] |
| `--arflags` | TEXT | `-rcs` | Archiver flags for static libraries [default: -rcs] |
| `--ranlib` | TEXT | `ranlib` | Ranlib executable; empty string to skip [default: ranlib] |
| `--cflags-heritage`, `--ch` |  |  | Store cflags for heritage checking; re-compile all if they change |
| `--track-build`, `--tb` |  |  | Store build info for the install command |
| `--compile-commands`, `--no-compile-commands` |  |  | Write the compilation database compile_commands.json in the build directory, linked from the project root (opt-in) |
| `--src`, `-s` | TEXT |  | Root-directory of source files [default: ./] |
| `--build-dir`, `--dbld` | TEXT |  | Directory containing built objects [default: ./]; given here, it wins over the mode's build_dir |
| `--obj-dir`, `--dobj` | TEXT | `./obj/` | Directory containing compiled objects [default: ./obj/] |
| `--mod-dir`, `--dmod` | TEXT | `./mod/` | Directory containing .mod files [default: ./mod/] |
| `--lib-dir`, `--dlib` | TEXT |  | Directories searched for libraries |
| `--include`, `-i` | TEXT |  | Directories for searching included files |
| `--exclude-dirs`, `--ed` | TEXT |  | Exclude directories from the building process |
| `--disable-recursive-search`, `--drs` |  |  | Disable recursive search inside directories |
| `--target`, `-t` | TEXT |  | Specify a target file [default: all programs found] |
| `--output`, `-o` | TEXT |  | Output file name (used with --target) |
| `--exclude`, `-e` | TEXT |  | Exclude files from the building process |
| `--libs` | TEXT |  | External libraries with full paths |
| `--vlibs` | TEXT |  | Volatile external libraries with full paths |
| `--ext-libs` | TEXT |  | External libraries in compiler path |
| `--ext-vlibs` | TEXT |  | Volatile external libraries in compiler path |
| `--dependon` | TEXT |  | Interdependent external fobos files for interdependent building |
| `--inc` | TEXT |  | Extensions for include files |
| `--extensions` | TEXT |  | Extensions of parsed files |
| `--build-all` |  |  | Build all sources parsed |
| `--preprocessor` | TEXT |  | Preprocessor name for pre-processing sources (e.g. PreForM.py) |
| `--preproc` | TEXT |  | Preprocessor flags for the main compiler |
| `--preprocessor-args`, `--app` | TEXT |  | Preprocessor-specific flags |
| `--preprocessor-no-o`, `--npp` |  |  | Do not add -o in front of output in preprocessor command |
| `--preprocessor-dir`, `--dpp` | TEXT |  | Directory for preprocessed files |
| `--preprocessor-ext`, `--epp` | TEXT |  | File extensions to preprocess |
| `--force-compile` |  |  | Force to (re-)compile all |
| `--colors` |  |  | Activate colors in shell prints |
| `--log`, `-l` |  |  | Activate log file creation |
| `--graph` |  |  | Generate a dependencies graph via graphviz |
| `--quiet`, `-q` |  |  | Less verbose output |
| `--verbose` |  |  | Extremely verbose output for debugging |
| `--jobs`, `-j` | INTEGER | `1` | Number of concurrent compilation jobs [default: 1] |
| `--makefile`, `-m` | TEXT |  | Generate a GNU Makefile for building the project |
| `--json` |  |  | Emit structured JSON to stdout instead of human-readable output (useful for scripting / agents) |
| `--build-profile` | TEXT |  | Named build profile: debug, release, asan, coverage |
| `--features` | TEXT |  | Comma- or space-separated feature flags to activate (defined in [features] section). Prefix with '-' to deactivate (e.g. 'prod,-coverage'). A mode may declare 'features = a b c' to set its own default set. |
| `--no-default-features` |  |  | Disable the default feature set defined in [features] default |
| `--varset` | TEXT |  | Apply one or more [varset:NAME] sections' $variable bindings to the active mode. Comma- or space-separated; later varsets override earlier ones. Use to swap parameterized values (cluster paths, GPU arch, ...) without duplicating modes. |
| `--pre-build` | TEXT |  | Rule(s) to execute before compilation (defined in [rule-X] sections) |
| `--post-build` | TEXT |  | Rule(s) to execute after successful linking (defined in [rule-X] sections) |
| `--no-auto-discover` |  |  | Disable convention-based source directory auto-discovery |
| `--no-cache` |  |  | Disable the build artifact cache |
| `--cache-dir` | TEXT |  | Override the default cache directory |
| `--list-profiles` |  |  | Print all known build profile flag sets and exit |
| `--examples` |  |  | Also build [[example.*]] sections |
| `--explain` |  |  | When the build fails, explain why: from the project's facts first, then with the LLM (cited cause and fix) for the first error they do not cover. |
| `--explain-context` |  |  | Like --explain, but print what the model would receive instead of running it. |
| `--target-filter` | TEXT |  | Build only the named target(s) from [[target.*]] sections (comma-separated) |

<!-- cli:end -->
