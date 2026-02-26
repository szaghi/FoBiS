# `build` command

Build all programs found in the source tree, or a specific target.

```bash
FoBiS.py build [options]
```

## Compiler options

| Option | Description |
|---|---|
| `-compiler {gnu,intel,intel_nextgen,g95,opencoarrays-gnu,pgi,ibm,nag,nvfortran,amd,custom}` | Compiler (case-insensitive, default: `gnu`) |
| `-fc FC` | Compiler executable — required for `-compiler custom` |
| `-cflags CFLAGS` | Compilation flags |
| `-lflags LFLAGS` | Linking flags |
| `-modsw MODSW` | Module path switch — required for `-compiler custom` |
| `-mpi` | MPI compiler variant |
| `-openmp` | OpenMP |
| `-openmp_offload` | OpenMP offload |
| `-coarray` | Coarrays |
| `-coverage` | Coverage instrumentation |
| `-profile` | Profiling instrumentation |
| `-mklib {static,shared}` | Build a library instead of a program (use with `-t`) |
| `-ch`, `--cflags_heritage` | Track flag changes; force full rebuild when they differ |
| `-tb`, `--track_build` | Save build info for use by `install` |

## Directory options

| Option | Default | Description |
|---|---|---|
| `-s`, `--src` | `./` | Root source directory (repeatable) |
| `-dbld`, `--build_dir` | `./` | Build output directory |
| `-dobj`, `--obj_dir` | `./obj/` | Compiled objects directory |
| `-dmod`, `--mod_dir` | `./mod/` | Module interface files directory |
| `-dlib`, `--lib_dir` | — | Library search directories |
| `-i`, `--include` | — | Include file search directories |
| `-ed`, `--exclude_dirs` | — | Directories to exclude from the build |
| `-drs`, `--disable_recursive_search` | `False` | Do not recurse into subdirectories |

## File options

| Option | Default | Description |
|---|---|---|
| `-t`, `--target` | All programs found | Specific target source file |
| `-o`, `--output` | Basename of target | Output executable name |
| `-e`, `--exclude` | — | Source files to exclude |
| `-libs` | — | External libraries (full paths) |
| `-vlibs` | — | Volatile external libraries (full paths) — triggers rebuild on change |
| `-ext_libs` | — | External libraries (by name, in linker path) |
| `-ext_vlibs` | — | Volatile external libraries (by name) |
| `-dependon` | — | Interdependent fobos files (`path/fobos[:mode]`) |
| `-inc` | `.inc .INC .h .H` | Include file extensions |
| `-extensions` | (all Fortran extensions) | Parsed file extensions |
| `-build_all` | `False` | Build all parsed sources, not just program files |

## fobos options

| Option | Description |
|---|---|
| `-f`, `--fobos` | Specify a fobos file with a different name or path |
| `-fci`, `--fobos_case_insensitive` | Case-insensitive fobos option parsing |
| `-mode` | Select a fobos mode |
| `-lmodes` | List available modes and exit |
| `--print_fobos_template` | Print a fobos template with all current option values |

## Preprocessor options

| Option | Description |
|---|---|
| `-preprocessor [CMD]` | Enable source preprocessing (default: `PreForM.py`) |
| `-p`, `--preproc` | Preprocessor flags for the main compiler |
| `-app`, `--preprocessor_args` | Flags passed to the preprocessor |
| `-npp`, `--preprocessor_no_o` | Omit `-o` from the preprocessor command line |
| `-dpp`, `--preprocessor_dir` | Directory for preprocessed sources (kept if set) |
| `-epp`, `--preprocessor_ext` | File extensions to preprocess |

## Fancy options

| Option | Description |
|---|---|
| `-force_compile` | Force recompilation of all sources |
| `-colors` | Coloured terminal output |
| `-l`, `--log` | Write a build log file |
| `-graph` | Generate a graphviz dependency graph |
| `-q`, `--quiet` | Less verbose output |
| `-verbose` | Maximum verbosity (for debugging FoBiS.py itself) |
| `-j`, `--jobs` | Number of parallel compile jobs (default: 1) |
| `-m`, `--makefile` | Export a GNU Makefile instead of building |

## Examples

```bash
# Build all programs with defaults
FoBiS.py build

# Build with GNU gfortran, parallel, debug flags
FoBiS.py build -compiler gnu -cflags " -c -O0 -g" -j 4

# Build a specific target
FoBiS.py build -t src/solver.f90 -o solver

# Build a static library
FoBiS.py build -t src/mylib.f90 -mklib static -o libmylib.a

# Use a fobos file and a specific mode
FoBiS.py build -f project.fobos -mode release

# Force full recompile
FoBiS.py build -force_compile
```
