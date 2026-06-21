# Supported Compilers

## Selecting a compiler

Use the `--compiler` flag (case-insensitive, tab-completable):

```bash
fobis build --compiler gnu
fobis build --compiler intel
fobis build --compiler custom --fc g95 --modsw "-fmod="
```

Or set it in the fobos file:

```ini
[default]
compiler = gnu
```

## Built-in compilers

| Identifier | Compiler |
|---|---|
| `gnu` | GNU gfortran |
| `intel` | Intel Fortran Compiler Classic (ifort) |
| `intel_nextgen` | Intel Fortran Compiler (ifx) |
| `g95` | g95 |
| `opencoarrays-gnu` | OpenCoarrays + gfortran |
| `pgi` | PGI Fortran Compiler |
| `ibm` | IBM XL Fortran |
| `nag` | NAG Fortran Compiler |
| `nvfortran` | NVIDIA HPC Fortran (nvfortran) |
| `amd` | AMD Flang (amdflang) |
| `lfortran` | LFortran (LLVM-based) — see [notes](#lfortran-notes) |
| `custom` | User-defined — requires `--fc` and optionally `--modsw` |

## Custom compiler

For any compiler not listed, use `custom` and specify the executable and module path switch:

```bash
fobis build --compiler custom --fc /opt/myfc/bin/myfc --modsw "-module "
```

In a fobos file:

```ini
[default]
compiler = custom
fc       = /opt/myfc/bin/myfc
modsw    = -module
cflags   = -c -O2
```

## LFortran notes {#lfortran-notes}

[LFortran](https://docs.lfortran.org/) is an LLVM-based Fortran compiler. As of
the 0.63 alpha it builds many real projects, with a few differences from the
established compilers that affect FoBiS usage:

- **Preprocessing is not automatic.** Unlike gfortran, LFortran does not
  preprocess uppercase `.F90` sources implicitly. FoBiS leaves `cflags` as a
  bare `-c`; if your sources use `#define`/`#ifdef`, add `--cpp` yourself:

  ```ini
  [default]
  compiler = lfortran
  cflags   = -c --cpp
  preproc  = -DDEBUG
  ```

  (FoBiS still preprocesses uppercase-extension files internally for its own
  dependency scan, so module resolution works regardless.)

- **Linking goes through `clang` by default.** LFortran invokes `clang` as its
  link driver, so `clang` must be on `PATH`. To use a different driver, pass it
  through `lflags` (e.g. `lflags = --linker=gcc`).

- **No quad precision.** `selected_real_kind(33,4931)` returns `-1`; build PENF
  and similar libraries without the `_R16P`/float128 path.

- **OpenMP** is supported (`fobis build --openmp` adds `--openmp`). **MPI** uses
  an LFortran-built `mpif90` wrapper (`fobis build --mpi`), mirroring gfortran.
  **Coarrays** are not yet available in the alpha.

## Compiler variants

### MPI

Enable the MPI-wrapped compiler variant:

```bash
fobis build --mpi
```

This switches to the MPI wrapper (e.g. `mpif90` for GNU, `mpiifort` for Intel).

### OpenMP

```bash
fobis build --openmp
```

Adds the appropriate OpenMP flag for the selected compiler.

### OpenMP offloading

```bash
fobis build --openmp-offload
```

### Coarrays

```bash
fobis build --coarray
```

### Coverage instrumentation

Instrument the build for gcov-compatible coverage analysis:

```bash
fobis build --coverage
```

After running the program, analyze `.gcov` files with the intrinsic rule:

```bash
fobis rule --gcov-analyzer reports/ summary
```

### Profiling

```bash
fobis build --profile
```

## Compiler-supplied intrinsic modules

The dependency scanner skips well-known intrinsic modules so they don't
surface as "unreachable" warnings. Three tiers of filtering apply, in
order:

**1. Universal Fortran intrinsics** — recognised by every compiler:

| Module |
|---|
| `iso_fortran_env`, `iso_c_binding` |
| `ieee_exceptions`, `ieee_arithmetic`, `ieee_features` |
| `openacc`, `omp_lib`, `mpi` |

A `use, intrinsic :: NAME` declaration (any `NAME`) is also filtered, since
the user has explicitly asked the compiler to take the intrinsic version.

**2. Compiler-supplied modules** — filtered only when the matching compiler
is active. Switching to a compiler that doesn't ship these modules makes
them resurface as unresolved dependencies, which is the right behaviour:

| Compiler | Recognised intrinsic modules |
|---|---|
| `nvfortran`, `pgi` | `cudafor`, `cudadeviceprop`, `cublas`, `cublas_v2`, `cusparse`, `cusolverdn`, `curand`, `curand_device`, `cufft`, `nccl`, `nvtx`, `thrust` |
| `intel`, `intel_nextgen` | `ifport`, `ifcore`, `ifqwin`, `iflogm`, `dfport`, `mkl_service` |
| `gnu`, `nag`, `ibm`, `amd`, `lfortran`, `g95`, `opencoarrays-gnu` | (universal set only) |

**3. User-extensible per-mode list** — for modules from external libraries
(e.g. `hdf5`, `hdf5_hl`, `mpi_f08`, vendor HPC modules) declare them in the
mode block:

```ini
[release]
compiler          = nvfortran
intrinsic_modules = hdf5 hdf5_hl
target            = src/main.F90
```

Names are case-insensitive and apply only to the mode they are declared in.
See the [`intrinsic_modules` mode key](/fobos/#intrinsic-modules-mode-key)
documentation for details.

## Compilation and linking flags

Override the default flags for the selected compiler:

```bash
fobis build --cflags " -c -O3 -march=native" --lflags " -O3"
```

Or in fobos:

```ini
[default]
cflags = -c -O3 -march=native
lflags = -O3
```

::: tip Flag prefixing
Prepend a space to flag strings to avoid the parser misinterpreting flags that start with `-`. See the [Quick Start](/guide/quickstart#quoted-string-arguments) note.
:::

## Preprocessor flags

Pass flags to the compiler's built-in preprocessor (e.g. `-D` macros):

```bash
fobis build --preproc " -DDEBUG -DUSE_MPI"
```

In fobos:

```ini
[default]
preproc = -DDEBUG -DUSE_MPI
```
