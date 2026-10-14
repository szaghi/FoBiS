---
title: HPC and clusters
---

# HPC and clusters

## OpenMP and MPI

```ini
[omp]
compiler  = gnu
cflags    = -c -O2
openmp    = True
src       = ./src/
build_dir = ./build/omp/

[mpi]
compiler  = gnu
cflags    = -c -O2
mpi       = True
src       = ./src/
build_dir = ./build/mpi/
```

`mpi = True` compiles with the compiler's MPI wrapper: `mpif90`, or `mpiifort` for Intel (`mpiifort -fc=ifx` for ifx). Tutorial: [OpenMP and MPI](/tutorial/growing/03-parallel).

## Run under MPI, a debugger or a checker

```ini
[mpi]
compiler = gnu
mpi      = True
launcher = mpirun -np {ranks}
```

```bash
fobis run  --mode mpi --ranks 4                     # mpirun -np 4 ./program
fobis test --mode mpi --ranks 2                     # every test on 2 ranks
fobis run  --launcher "gdb --args" -- input.nml     # under the debugger
fobis test --launcher "valgrind --error-exitcode=1" # every test under valgrind
```

Tutorial: [OpenMP and MPI](/tutorial/growing/03-parallel). Reference: [launchers](/reference/run#launchers).

## A GPU build

```ini
[gpu]
compiler  = nvfortran
cflags    = -c -O2 -acc -gpu=cc80
lflags    = -acc -gpu=cc80
src       = ./src/
build_dir = ./build/gpu/
```

`-gpu=cc80` is an A100/A30; `-gpu=ccnative` uses the GPUs of the build machine. Tutorial: [on a cluster](/tutorial/numerics/09-cluster).

## Several compilers loaded by modules

```ini
[verification]
setup =
    nvfortran: module load nvhpc
    intel_nextgen: source /opt/intel/oneapi/compiler/latest/env/vars.sh
```

```bash
fobis matrix                    # every mode x shadow, each in its own environment
fobis matrix --compilers gnu,nvfortran --verify
```

A setup line applies to a mode by its name, else by its compiler (`gnu`, `intel_nextgen`, `nvfortran` ...), else by the
compiler family. Guide: [the matrix](/advanced/matrix).

## Run on compute nodes with Slurm

```ini
[scheduler]
kind        = slurm
partition   = gpu
account     = myproject
login_nodes = login*
```

```bash
fobis case run --runner slurm
fobis verify --runner slurm
fobis test --runner slurm
```

Builds stay on the login node; each run is a job. Tutorial: [on a cluster](/tutorial/numerics/09-cluster).
Guide: [running on a cluster](/advanced/scheduler).

## Where the time goes

```bash
fobis profile mycase                      # gprof
fobis profile mycase --tool callgrind     # instructions, per source line
fobis profile mycase --tool nsys --runner slurm
```

Tutorial: [where the time goes](/tutorial/numerics/08-profile).

## FoBiS without pip

```bash
make standalone                  # dist/fobis.pyz, from a FoBiS checkout
python3 fobis.pyz build
```

The release assets include `fobis.pyz`.
