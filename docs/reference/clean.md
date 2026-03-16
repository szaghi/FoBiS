# `clean` command

Remove compiled objects, module files, and built targets from a previous build.

```bash
FoBiS.py clean [options]
```

## Scope options

| Option | Description |
|---|---|
| `--only-obj` | Clean only compiled objects (`.o` / `.mod`), leave built targets |
| `--only-target` | Clean only built targets (executables / libraries), leave objects |

::: warning Mutually exclusive
`--only-obj` and `--only-target` cannot be used together — FoBiS.py will exit with an error if both are supplied.
:::

## Compiler options

| Option | Description |
|---|---|
| `--compiler {gnu,intel,…,custom}` | Compiler (used to locate object paths, default: `gnu`) |
| `--fc FC` | Compiler executable (for `--compiler custom`) |
| `--cflags CFLAGS` | Compilation flags (used to locate output paths) |
| `--lflags LFLAGS` | Linking flags |
| `--modsw MODSW` | Module path switch (for `--compiler custom`) |
| `--mpi` | MPI variant |
| `--openmp` | OpenMP |
| `--openmp-offload` | OpenMP offload |
| `--coarray` | Coarrays |
| `--coverage` | Coverage instrumentation |
| `--profile` | Profiling instrumentation |
| `--mklib {static,shared}` | Target was a library |
| `--ch`, `--cflags-heritage` | Also remove the cflags heritage file |
| `--tb`, `--track-build` | Also remove the track-build info file |

## Directory options

| Option | Default | Description |
|---|---|---|
| `-s`, `--src` | `./` | Root source directory |
| `--dbld`, `--build-dir` | `./` | Build output directory to clean |
| `--dobj`, `--obj-dir` | `./obj/` | Compiled objects directory |
| `--dmod`, `--mod-dir` | `./mod/` | Module interface files directory |
| `--dlib`, `--lib-dir` | — | Library search directories |
| `-i`, `--include` | — | Include file search directories |
| `--ed`, `--exclude-dirs` | — | Directories that were excluded from the build |
| `--drs`, `--disable-recursive-search` | `False` | Do not recurse into subdirectories |

## File options

| Option | Default | Description |
|---|---|---|
| `-t`, `--target` | All programs found | Specific target to clean |
| `-o`, `--output` | Basename of target | Output executable name |
| `-e`, `--exclude` | — | Source files that were excluded |
| `--libs` | — | External libraries (full paths) |
| `--vlibs` | — | Volatile external libraries (full paths) |
| `--ext-libs` | — | External libraries (by name) |
| `--ext-vlibs` | — | Volatile external libraries (by name) |
| `--dependon` | — | Interdependent fobos files |
| `--inc` | `.inc .INC .h .H` | Include file extensions |
| `--extensions` | (all Fortran extensions) | Parsed file extensions |
| `--build-all` | `False` | All parsed sources were built |

## fobos options

| Option | Description |
|---|---|
| `-f`, `--fobos` | Specify a fobos file with a different name or path |
| `--fci`, `--fobos-case-insensitive` | Case-insensitive fobos option parsing |
| `--mode` | Select a fobos mode — tab-completable from the active fobos file |
| `--lmodes` | List available modes and exit |
| `--print-fobos-template` | Print a fobos template with all current option values |

## Fancy options

| Option | Description |
|---|---|
| `--colors` | Coloured terminal output |
| `-l`, `--log` | Write a log file |
| `-q`, `--quiet` | Less verbose output |
| `--verbose` | Maximum verbosity |
| `--json` | Emit structured JSON to stdout (see [JSON output](/advanced/json-output)) |

## Examples

```bash
# Clean everything (objects + targets)
FoBiS.py clean

# Clean only compiled objects, keep the executable
FoBiS.py clean --only-obj

# Clean only the built executable, keep objects
FoBiS.py clean --only-target

# Clean using settings from a fobos mode
FoBiS.py clean -f project.fobos --mode release

# Clean a specific build directory
FoBiS.py clean --build-dir ./build/ --obj-dir ./build/obj/ --mod-dir ./build/mod/
```

::: tip fobos integration
When using a fobos file, `clean` reads the same directory and target settings as `build`, so the correct artefacts are removed without repeating paths on the command line.
:::
