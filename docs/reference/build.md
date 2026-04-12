# `build` command

Build all programs found in the source tree, or a specific target.

```bash
fobis build [options]
```

## Compiler options

| Option | Description |
|---|---|
| `--compiler {gnu,intel,intel_nextgen,g95,opencoarrays-gnu,pgi,ibm,nag,nvfortran,amd,custom}` | Compiler (case-insensitive, default: `gnu`) — tab-completable |
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

## Directory options

| Option | Default | Description |
|---|---|---|
| `-s`, `--src` | `./` | Root source directory (repeatable: `--src ./a --src ./b`) |
| `--dbld`, `--build-dir` | `./` | Build output directory |
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
| `--features NAMES` | Comma- or space-separated list of features to activate (see [Feature Flags](/advanced/features)) |
| `--no-default-features` | Suppress the `default =` entry in `[features]`; activate only explicitly listed features |

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

## External library options

| Option | Description |
|---|---|
| `--pkg-config NAMES` | `pkg-config` package names to query for flags (repeatable) |
| `--with-mpi-auto` | Auto-detect MPI compiler wrapper and flags |

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

## Examples

```bash
# Build all programs with defaults
fobis build

# Build with GNU gfortran, parallel, debug flags
fobis build --compiler gnu --cflags " -c -O0 -g" -j 4

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
