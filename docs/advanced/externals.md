# External Library Detection

FoBiS can auto-detect compiler and linker flags for external libraries using
`pkg-config` and MPI wrapper inspection — so you never have to look up `-I`
and `-L` paths by hand.

## `pkg-config` integration

List package names in the fobos `[externals]` section or via `--pkg-config`:

```ini
[externals]
pkg-config = hdf5 netcdf zlib
```

```bash
# Equivalent via CLI
fobis build --pkg-config hdf5 --pkg-config netcdf
```

FoBiS runs `pkg-config --cflags --libs <name>` for each package and appends
the resulting flags to `cflags` and `lflags` respectively.

If a package is not found, a warning is emitted and the build continues:

```
Warning: external 'hdf5' could not be resolved. Flags skipped.
Check that the library is installed.
```

## MPI auto-detection

```ini
[externals]
mpi-auto = true
```

```bash
fobis build --with-mpi-auto
```

FoBiS probes for MPI compiler wrappers in order:
1. `mpifort` — Fortran-specific wrapper (preferred)
2. `mpif90`  — legacy Fortran wrapper
3. `mpif77`  — Fortran 77 wrapper (last resort)

It then calls `mpifort --showme:compile` and `--showme:link` (OpenMPI) or
`mpifort -show` (MPICH) to extract the underlying compiler flags.

The detected flags are merged with your existing `cflags` and `lflags`.
This is an alternative to `--mpi`, which just prefixes the compiler command
with `mpi*`.

## pkg-config spec in fobos

You can also generate a `.pc` file for your own project so downstream
consumers can link against it with `pkg-config`:

```ini
[pkgconfig]
name        = mylib
description = My Fortran library
version     = 1.2.0
url         = https://github.com/example/mylib
requires    = hdf5
cflags      = -I${includedir}
libs        = -L${libdir} -lmylib
```

```bash
# Write mylib.pc to the build directory
fobis build --write-pkgconfig
```

See [pkg-config generation](/reference/build) for the full option list.

## Flag routing

Flags returned by `pkg-config` are routed automatically:

| Flag pattern | Destination |
|---|---|
| `-I...` | `cflags` |
| `-D...` | `cflags` |
| `-L...` | `lflags` |
| `-l...` | `lflags` |
| `-Wl,...` | `lflags` |
| everything else | `cflags` |

## Combining with feature flags

External library detection and [feature flags](/advanced/features) are
independent and compose freely:

```ini
[features]
hdf5 = -DUSE_HDF5

[externals]
pkg-config = hdf5
```

When `--features hdf5` is active, the `-DUSE_HDF5` define is added to
`cflags` and `pkg-config hdf5` provides the include and link flags.
