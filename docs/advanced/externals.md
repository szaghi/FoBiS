# External Libraries

Linking against system libraries — MPI, HDF5, NetCDF, BLAS/LAPACK, FFTW — usually means
hunting down the right `-I`, `-L`, and `-l` flags for whichever machine you happen to be
on. FoBiS resolves them for you: declare the libraries in an `[externals]` section, list
which ones a mode needs, and FoBiS probes the environment and appends the discovered flags
to your build. There is **no CLI flag** for this — it is entirely fobos-driven.

## The `[externals]` section

Each entry maps a library *name* to a *spec* — either `auto` (probe the environment) or an
explicit installation prefix:

```ini
[externals]
mpi    = auto            ; probe mpifort/mpif90/mpiifx wrappers
hdf5   = auto            ; pkg-config hdf5_fortran, or h5pfc/h5fc -show
netcdf = auto            ; nf-config / nc-config, or pkg-config netcdf
fftw   = auto            ; pkg-config fftw3
blas   = /opt/openblas   ; explicit prefix → /opt/openblas/{include,lib}
```

Declaring a library in `[externals]` does not activate it. A mode opts in with the
`externals` key:

```ini
[default]
compiler  = gnu
cflags    = -c -O2
src       = ./src/
externals = mpi hdf5     ; only these two are resolved and linked for this mode
```

FoBiS resolves `mpi` and `hdf5`, then appends the resulting include dirs and compile flags
to `cflags`, and the library dirs and `-l` flags to `lflags`, before the build runs.

## `auto` probing

For `name = auto`, FoBiS dispatches to a built-in prober. The recognised names and their
strategies:

| Name | Probe strategy |
|---|---|
| `mpi` | `mpifort` / `mpif90` / `mpiifort` / `mpiifx` with `--showme` (Open MPI) or `-show` (MPICH); falls back to `pkg-config ompi-fort` |
| `hdf5` | `pkg-config hdf5_fortran`, else `h5pfc -show` / `h5fc -show` |
| `netcdf` | `nf-config` / `nc-config`, else `pkg-config netcdf` |
| `blas` | `pkg-config blas`, falling back to `openblas` |
| `openblas` | `pkg-config openblas` |
| `lapack` | `pkg-config lapack` |
| `fftw` / `fftw3` | `pkg-config fftw3` |

`pkg-config` is the primary mechanism; the wrapper scripts (`mpifort -show`, `h5fc -show`,
`nf-config`) are fallbacks for libraries that ship one.

If an `auto` library cannot be resolved, FoBiS emits a warning and continues — the build is
not aborted:

```
Warning: external 'hdf5' could not be resolved. Flags skipped. Check that the library is installed.
```

## Explicit prefix

When a library is not on the `pkg-config` path, or you want to pin a specific build, give a
prefix instead of `auto`:

```ini
[externals]
hdf5 = /opt/hdf5-1.14
```

FoBiS probes `<prefix>/include` for module/include files and `<prefix>/lib` for the library,
using the conventional library names for that package (e.g. `hdf5_fortran`, `hdf5` for HDF5).
For names with no built-in library mapping, the external name itself is used as the `-l`
target.

## Generating a `pkg-config` file for your project

The flip side of consuming externals is *publishing* one: FoBiS can emit a relocatable `.pc`
file so downstream projects can link against your library with `pkg-config`. This is driven
by `pkgconfig*` keys in the build mode (not a separate section, and not a CLI flag):

```ini
[default]
compiler           = gnu
cflags             = -c -O2
src                = ./src/
mklib              = static
output             = libmylib.a

pkgconfig          = true                     ; enable .pc generation
pkgconfig_name     = mylib                    ; defaults to [project] name
pkgconfig_desc     = My Fortran library       ; defaults to [project] summary
pkgconfig_url      = https://github.com/example/mylib
pkgconfig_req      = hdf5                      ; → Requires:
pkgconfig_req_priv = zlib                      ; → Requires.private:
```

Only `pkgconfig = true` is required; every other field falls back to the corresponding
`[project]` value when omitted. FoBiS writes a `.pc` with relocatable `prefix`/`libdir`/
`includedir` variables, stripping a leading `v` from the version and the leading `lib`/
suffix from the library name.

## Flag routing

However the flags are obtained (pkg-config output, wrapper `-show`, or prefix probing), FoBiS
routes each one to the right place:

| Flag pattern | Destination |
|---|---|
| `-I…`, `-D…`, include dirs | `cflags` |
| `-L…`, `-l…`, `-Wl,…`, library dirs | `lflags` |
| everything else | `cflags` |

## Composing with feature flags

External resolution and [feature flags](/advanced/features) are independent and compose
cleanly. A feature can supply the *conditional-compilation define* while the external
supplies the *include and link flags* for the same library:

```ini
[features]
hdf5 = -DUSE_HDF5

[externals]
hdf5 = auto

[default]
compiler  = gnu
cflags    = -c
features  = hdf5         ; adds -DUSE_HDF5
externals = hdf5         ; adds the HDF5 include + link flags
```
