---
title: 3. OpenMP and MPI
---

# 3. OpenMP and MPI

FoBiS knows each compiler's switch for OpenMP and its MPI wrapper: a mode says `openmp = True` or `mpi = True`, and
the right flags or command follow.

## OpenMP

A new program, `sweep`, computes the errors of both rules for 12 grids. The cases are independent, so OpenMP threads
compute them in parallel:

<<< @/examples/tutorial/2-growing/03-parallel/files/src/sweep.F90{fortran}

The rules are `pure`: they can be called from parallel threads safely (and a parallel construct cannot appear inside
a pure procedure, so the parallelism belongs to the caller). A mode for it:

```ini
[openmp]
help          = The sweep, multi-threaded with OpenMP
template      = template-gnu
build_profile = release
cflags        = -c
openmp        = True
build_dir     = ./build/openmp/
target        = src/sweep.F90
```

<<< @/examples/output/2-growing/03/openmp.txt{console}

`-fopenmp` was added to both the compiling and the linking flags.

<<< @/examples/output/2-growing/03/sweep.txt{console}

## MPI

Another program splits `[0, pi]` among the MPI processes; each integrates its piece, and `mpi_reduce` adds them up:

<<< @/examples/tutorial/2-growing/03-parallel/files/src/integrate_mpi.F90{fortran}

```ini
[mpi]
help          = Simpson's rule split among MPI processes
template      = template-gnu
build_profile = release
cflags        = -c
mpi           = True
build_dir     = ./build/mpi/
target        = src/integrate_mpi.F90
```

With `mpi = True` FoBiS compiles with the MPI wrapper of the compiler (`mpif90` for gfortran):

<<< @/examples/output/2-growing/03/mpi.txt{console}

<<< @/examples/output/2-growing/03/mpirun.txt{console}

Two processes with 64 intervals each make 128 intervals over the whole range: the error is the one `sweep` printed for
128 intervals.

`fobis run` starts the mode's program through a launcher: `{ranks}` is replaced by `--ranks`. A mode can keep its
launcher in the fobos (`launcher = mpirun -np {ranks}`), and `fobis test` takes the same options, so MPI tests run
with one command:

<<< @/examples/output/2-growing/03/launcher.txt{console}

::: info MPI outputs
The MPI outputs were recorded with Open MPI 5.0 and gfortran 15 (the documentation's CI has no MPI); the rest of the
page, with gfortran 13.
:::

::: tip What you learned
`openmp = True`, `mpi = True`. For libraries found through `pkg-config` or a wrapper (HDF5, NetCDF, FFTW, MPI
too) see [external libraries](/advanced/externals).
:::

Next: [4. A project that depends on quad](./04-dependon).
