# `clean` command

Remove compiled objects, module files, and built targets from a previous build.

```bash
FoBiS.py clean [options]
```

## Compiler options

| Option | Description |
|---|---|
| `-only_obj` | Clean only compiled objects (`.o`), leave built targets |
| `-only_target` | Clean only built targets (executables / libraries), leave objects |
| `-compiler {gnu,intel,…,custom}` | Compiler (used to locate object paths, default: `gnu`) |
| `-fc FC` | Compiler executable (for `-compiler custom`) |
| `-cflags CFLAGS` | Compilation flags (used to locate output paths) |
| `-lflags LFLAGS` | Linking flags |
| `-modsw MODSW` | Module path switch (for `-compiler custom`) |
| `-mpi` | MPI variant |
| `-openmp` | OpenMP |
| `-openmp_offload` | OpenMP offload |
| `-coarray` | Coarrays |
| `-coverage` | Coverage instrumentation |
| `-profile` | Profiling instrumentation |
| `-mklib {static,shared}` | Target was a library |
| `-ch`, `--cflags_heritage` | Also remove the cflags heritage file |
| `-tb`, `--track_build` | Also remove the track-build info file |

## Directory options

| Option | Default | Description |
|---|---|---|
| `-s`, `--src` | `./` | Root source directory |
| `-dbld`, `--build_dir` | `./` | Build output directory to clean |
| `-dobj`, `--obj_dir` | `./obj/` | Compiled objects directory |
| `-dmod`, `--mod_dir` | `./mod/` | Module interface files directory |
| `-dlib`, `--lib_dir` | — | Library search directories |
| `-i`, `--include` | — | Include file search directories |
| `-ed`, `--exclude_dirs` | — | Directories that were excluded from the build |
| `-drs`, `--disable_recursive_search` | `False` | Do not recurse into subdirectories |

## File options

| Option | Default | Description |
|---|---|---|
| `-t`, `--target` | All programs found | Specific target to clean |
| `-o`, `--output` | Basename of target | Output executable name |
| `-e`, `--exclude` | — | Source files that were excluded |
| `-libs` | — | External libraries (full paths) |
| `-vlibs` | — | Volatile external libraries (full paths) |
| `-ext_libs` | — | External libraries (by name) |
| `-ext_vlibs` | — | Volatile external libraries (by name) |
| `-dependon` | — | Interdependent fobos files |
| `-inc` | `.inc .INC .h .H` | Include file extensions |
| `-extensions` | (all Fortran extensions) | Parsed file extensions |
| `-build_all` | `False` | All parsed sources were built |

## fobos options

| Option | Description |
|---|---|
| `-f`, `--fobos` | Specify a fobos file with a different name or path |
| `-fci`, `--fobos_case_insensitive` | Case-insensitive fobos option parsing |
| `-mode` | Select a fobos mode |
| `-lmodes` | List available modes and exit |
| `--print_fobos_template` | Print a fobos template with all current option values |

## Fancy options

| Option | Description |
|---|---|
| `-colors` | Coloured terminal output |
| `-l`, `--log` | Write a log file |
| `-q`, `--quiet` | Less verbose output |
| `-verbose` | Maximum verbosity |

## Examples

```bash
# Clean everything (objects + targets)
FoBiS.py clean

# Clean only compiled objects, keep the executable
FoBiS.py clean -only_obj

# Clean only the built executable, keep objects
FoBiS.py clean -only_target

# Clean using settings from a fobos mode
FoBiS.py clean -f project.fobos -mode release

# Clean a specific build directory
FoBiS.py clean -dbld ./build/ -dobj ./build/obj/ -dmod ./build/mod/
```

::: tip fobos integration
When using a fobos file, `clean` reads the same directory and target settings as `build`, so the correct artefacts are removed without repeating paths on the command line.
:::
