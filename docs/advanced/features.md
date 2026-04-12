# Feature Flags

Feature flags let you define named compile-time options in the fobos file and
activate them selectively — without maintaining separate build modes for every
combination.

## Defining features

Add a `[features]` section to the fobos file. Each key is a feature name; the
value is the flags that feature contributes (cflags and lflags are separated
automatically):

```ini
[features]
default = mpi                     ; features active when none are explicitly requested

mpi    = -DUSE_MPI                ; pure define — goes to cflags
hdf5   = -DUSE_HDF5 -I/opt/hdf5/include
omp    = -DUSE_OMP -fopenmp       ; -fopenmp goes to lflags, -DUSE_OMP to cflags
netcdf = -DUSE_NETCDF

[default]
compiler = gnu
cflags   = -c -O2
```

## Activating features

```bash
# Default features only (from fobos [features] default =)
fobis build

# Explicitly request features (comma or space separated)
fobis build --features hdf5
fobis build --features "mpi,hdf5"

# Add features on top of defaults
fobis build --features netcdf        # defaults + netcdf

# Suppress defaults, use only what you specify
fobis build --no-default-features --features hdf5

# No features at all
fobis build --no-default-features
```

## Flag routing

Flags in a feature value are routed automatically:

| Flag pattern | Goes to | Reason |
|---|---|---|
| `-D...` | `cflags` | preprocessor define |
| `-I...` | `cflags` | include path |
| `-L...` | `lflags` | library search path |
| `-l...` | `lflags` | library name |
| `-Wl,...` | `lflags` | linker option |
| OpenMP flags (see below) | **both** `cflags` and `lflags` | needed at compile and link time |
| everything else | `cflags` | default |

### OpenMP flags are dual-destination

When a feature value contains an OpenMP flag written as a raw string, FoBiS
routes it to both cflags and lflags automatically. The recognized flags are:

| Compiler | OpenMP flag |
|---|---|
| `gnu`, `opencoarrays-gnu`, `amd` | `-fopenmp` |
| `intel`, `intel_nextgen` | `-qopenmp` |
| `intel_nextgen` (link-phase variant) | `-fiopenmp` |
| `nvfortran`, `pgi` | `-mp` |
| `ibm` | `-qsmp=omp` |
| `nag` | `-openmp` |

## Implicit (compiler-agnostic) features

FoBiS recognises a set of **implicit** feature names that map directly to
compiler capabilities already defined in the compiler table — the same
abstraction used by `--openmp`, `--mpi`, and `--coarray`. You can activate
these without a `[features]` section and without writing a single
compiler-specific flag:

| Feature name | Alias | Activates |
|---|---|---|
| `openmp` | `omp` | OpenMP for the active compiler |
| `mpi` | — | MPI compiler wrapper |
| `coarray` | — | Coarray support |
| `coverage` | — | Coverage instrumentation |
| `profile` | — | Profiling instrumentation |
| `openmp_offload` | `omp_offload` | OpenMP offload |

```bash
# Compiler-agnostic — works correctly with gnu, intel, nvfortran, ...
fobis build --compiler gnu   --features openmp
fobis build --compiler intel --features openmp
fobis build --compiler nvfortran --features omp
```

FoBiS resolves `openmp` to the flag appropriate for the active compiler,
passes it to both cflags and lflags, and selects the MPI wrapper or coarray
runtime accordingly — identical to passing `--openmp` / `--mpi` / `--coarray`
on the command line.

### No `[features]` section required

Implicit features work even when the fobos file has no `[features]` section:

```ini
[default]
compiler = intel
cflags   = -c -O2
```

```bash
fobis build --features openmp,mpi   # resolves -qopenmp and mpiifort correctly
```

### Explicit definition always wins

If you define an implicit feature name explicitly in `[features]`, the explicit
definition is used as-is and the implicit mechanism is bypassed:

```ini
[features]
; Add a preprocessor define alongside OpenMP — explicit wins over implicit
openmp = -DUSE_OMP -fopenmp
```

```bash
fobis build --compiler gnu --features openmp
# → routes -DUSE_OMP to cflags, -fopenmp to both cflags and lflags
# → does NOT set cliargs.openmp via the implicit mechanism
```

### Combining implicit and explicit features

Implicit and explicit features compose freely:

```ini
[features]
hdf5 = -DUSE_HDF5 -I/opt/hdf5/include -L/opt/hdf5/lib -lhdf5
```

```bash
# openmp resolved implicitly, hdf5 resolved explicitly
fobis build --features openmp,hdf5
```

### Preprocessor defines with implicit features

Implicit features activate the compiler capability but do not add a
preprocessor define. If `#ifdef USE_OMP` guards are needed, add a separate
explicit feature for the define and combine both:

```ini
[features]
omp_defs = -DUSE_OMP
```

```bash
fobis build --features openmp,omp_defs
```

## Unknown features

Requesting a feature name that is not defined in `[features]` emits a warning
and is otherwise ignored — the build continues:

```
Warning: unknown feature 'cuda'. Known features: hdf5, mpi, netcdf, omp. Ignored.
```

## Integration with modes

Features work across all modes. The `default` key in `[features]` applies to
every mode unless overridden by `--no-default-features`:

```ini
[features]
default = mpi hdf5

[debug]
compiler = gnu
cflags   = -c -O0 -g

[release]
compiler = gnu
cflags   = -c -O3
```

```bash
fobis build --mode debug             # builds with mpi + hdf5 defines
fobis build --mode release           # builds with mpi + hdf5 defines
fobis build --mode release --no-default-features --features omp
```

## Combining with build profiles

Features and profiles are independent and compose freely:

```bash
fobis build --build-profile debug --features hdf5
```
