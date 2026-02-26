# Supported Compilers

## Selecting a compiler

Use the `-compiler` flag (case-insensitive):

```bash
FoBiS.py build -compiler gnu
FoBiS.py build -compiler intel
FoBiS.py build -compiler custom -fc g95 -modsw "-fmod="
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
| `custom` | User-defined — requires `-fc` and optionally `-modsw` |

## Custom compiler

For any compiler not listed, use `custom` and specify the executable and module path switch:

```bash
FoBiS.py build -compiler custom -fc /opt/myfc/bin/myfc -modsw "-module "
```

In a fobos file:

```ini
[default]
compiler = custom
fc       = /opt/myfc/bin/myfc
modsw    = -module
cflags   = -c -O2
```

## Compiler variants

### MPI

Enable the MPI-wrapped compiler variant:

```bash
FoBiS.py build -mpi
```

This switches to the MPI wrapper (e.g. `mpif90` for GNU, `mpiifort` for Intel).

### OpenMP

```bash
FoBiS.py build -openmp
```

Adds the appropriate OpenMP flag for the selected compiler.

### OpenMP offloading

```bash
FoBiS.py build -openmp_offload
```

### Coarrays

```bash
FoBiS.py build -coarray
```

### Coverage instrumentation

Instrument the build for gcov-compatible coverage analysis:

```bash
FoBiS.py build -coverage
```

After running the program, analyze `.gcov` files with the intrinsic rule:

```bash
FoBiS.py rule -gcov_analyzer reports/ summary
```

### Profiling

```bash
FoBiS.py build -profile
```

## Compilation and linking flags

Override the default flags for the selected compiler:

```bash
FoBiS.py build -cflags " -c -O3 -march=native" -lflags " -O3"
```

Or in fobos:

```ini
[default]
cflags = -c -O3 -march=native
lflags = -O3
```

::: tip Flag prefixing
Prepend a space to flag strings to avoid `argparse` misinterpreting flags that start with `-`. See the [Quick Start](/guide/quickstart#quoted-string-arguments) note.
:::

## Preprocessor flags

Pass flags to the compiler's built-in preprocessor (e.g. `-D` macros):

```bash
FoBiS.py build -p " -DDEBUG -DUSE_MPI"
```

In fobos:

```ini
[default]
preproc = -DDEBUG -DUSE_MPI
```
