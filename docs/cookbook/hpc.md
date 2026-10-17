---
title: HPC and clusters
---

# HPC and clusters

A mode says which parallel model a build uses (`openmp`, `mpi`, `coarray`, GPU flags), and FoBiS adds each compiler's
switches or picks its MPI wrapper. `fobis run` and `fobis test` start the programs through a launcher. On a cluster the
programs are built on the login node and run on compute nodes: with `--runner slurm` the commands that run programs
submit each run as a Slurm job and read its results exactly as they read a local run, with the same probes, JSON and
verdicts.

How it works:

1. **Build where you are.** Every build runs on the submitting host (the login node), with the compilers of its
   environment: load the modules first.
2. **Run where the resources are.** With `--runner slurm`, each case or test run becomes a job: a script written into
   its run directory, `sbatch`, `squeue` until the job leaves the queue, `sacct` for its final state. The resources
   come from the case (`ranks`, `threads`, `gpus`, `timeout`) and from `[scheduler]`.
3. **Read the same files.** The job writes the program's output, exit status, start and end time and the node's facts
   into the run directory; the probes read them there. The run directories must be on a file system the compute nodes
   share: they are inside the project by default (`.fobis/runs`).
4. **Refuse what the login node must not run.** On a host matching `[scheduler] login_nodes`, an MPI or GPU run is
   refused unless it goes through the scheduler.

Tutorial: [OpenMP and MPI](/tutorial/growing/03-parallel), [on a cluster](/tutorial/numerics/09-cluster).
Reference: [`run`](/reference/run), [`test`](/reference/test), [`case`](/reference/case),
[`profile`](/reference/profile), [configuration](/reference/configuration).

## OpenMP and MPI modes

```ini
[openmp]
help          = The sweep, multi-threaded with OpenMP
template      = template-gnu
build_profile = release
cflags        = -c
openmp        = True
build_dir     = ./build/openmp/
target        = src/sweep.F90

[mpi]
help          = Simpson's rule split among MPI processes
template      = template-gnu
build_profile = release
cflags        = -c
mpi           = True
build_dir     = ./build/mpi/
target        = src/integrate_mpi.F90
```

`openmp = True` adds the compiler's OpenMP switch to the compiling and the linking flags: `-fopenmp` (gnu, amd),
`-qopenmp` (intel; intel_nextgen links with `-fiopenmp`), `-mp` (nvfortran, pgi), `-qsmp=omp` (ibm), `-openmp` (nag),
`--openmp` (lfortran). `mpi = True` replaces the compiler command with its MPI wrapper: `mpif90`, `mpiifort` for
intel, `mpiifort -fc=ifx` for intel_nextgen.

<<< @/examples/output/2-growing/03/mpi.txt{console}

- **Another wrapper (`mpiifx`, Cray `ftn`, `mpifort`):** set `fc = mpiifx` and leave `mpi` off. With `mpi = True` the
  family's wrapper replaces `fc`.
- **Coarrays:** `coarray = True` adds `-fcoarray=lib` (and `-lcaf_mpi` at link time) for gnu, `-coarray` for Intel;
  or `compiler = opencoarrays-gnu`, which compiles with the `caf` wrapper.
- **C files** in an MPI mode compile with the family's MPI C wrapper (`mpicc`, `mpiicx` for intel_nextgen); OpenMP
  adds the C switch too.
- **Check what a mode does** with `fobis introspect --compiler --mode NAME`: the command the build runs (the MPI
  wrapper included) and the flags with the OpenMP and coarray switches, without building anything.
- **Libraries found through `pkg-config` or a wrapper** (HDF5, NetCDF, FFTW): [Dependencies](./dependencies).

Thread count and stack: `OMP_NUM_THREADS` for a run of your own; a case's `threads` sets it for its runs.

## Run a program or the tests through a launcher

```ini
[mpi]
compiler = gnu
mpi      = True
launcher = mpirun -np {ranks}
```

```bash
fobis run  --mode mpi --ranks 4                       # mpirun -np 4 ./integrate_mpi
fobis test --mode mpi --ranks 2                       # every test on 2 ranks
fobis run  --launcher "gdb --args" -- input.nml       # under the debugger, arguments after --
fobis test --launcher "valgrind --error-exitcode=1"   # every test under valgrind
fobis run  --mode mpi --ranks 4 --dry-run             # the build and the run commands, launcher included
```

<<< @/examples/output/2-growing/03/launcher.txt{console}

- **Where the launcher comes from:** `--launcher`, else the mode's `launcher` key, else (tests) the `[test] launcher`
  key, else `mpirun -np {ranks}` when only `--ranks` is given. `{ranks}` is replaced by `--ranks`, 1 when not given.
- **Checked before building:** a launcher that is not on the PATH stops `run` and `test` with exit 2.
- **The exit status is the launcher's:** an MPI launcher returns its processes' failure.
- **Parallel MPI tests:** `fobis test -j 8 --ranks 4` runs two tests at a time, each taking 4 of the 8 slots.
- **Cases** have their own launcher: the case's `ranks` with `[verification] launcher` (default
  `mpirun -np {ranks}`); see [Verifying results](./verification).

## GPU builds: OpenACC and OpenMP offload

A mode for nvfortran and an NVIDIA A30 (compute capability 8.0); the offload flags go to the link too:

<<< @/examples/output/5-numerics/09/mode.txt{ini}

- **nvfortran:** `-acc` OpenACC, `-mp=gpu` OpenMP target offload, `-cuda` CUDA Fortran; `-gpu=cc80` the compute
  capability (`ccnative`: the GPUs of the build machine). `-gpu=mem:managed` puts allocatable data in managed memory,
  which hides missing data clauses: a code correct only with it can fail with `-gpu=mem:separate`. Device code uses
  FMA unless `-gpu=nofma`.
- **`openmp_offload = True`** adds the offload flag to the compile and link flags: `-fopenmp-targets=spir64` for ifx
  (Intel GPUs), `-mp=gpu` for nvfortran. Any other compiler gets a warning and no flag: write its offload flags in
  `cflags` and `lflags`.
- **gfortran:** `-fopenacc` offloads only with a gfortran built with an offload target; otherwise the regions run on
  the host.
- **One mode for several compilers:** qualified keys (`cflags.nvfortran = -acc -gpu=cc80`): [Building](./build).

The compilers' GPU and runtime-check flags, as measured, are in the shipped knowledge pack:

```bash
fobis kb search "GPU options" --pack compilers
fobis kb show compilers:nvfortran#gpu-options
```

A GPU case declares `gpus = 1`: locally it runs on the build machine's GPU, under `--runner slurm` the job asks for it
(`--gpus=1`), and on a login node it is refused (below).

## Several compilers loaded by environment modules

```ini
[verification]
setup =
    nvfortran: module load nvhpc
    intel_nextgen: source /opt/intel/oneapi/compiler/latest/env/vars.sh
```

```bash
fobis matrix                                      # every mode x shadow, each in its own environment
fobis matrix --compilers gnu,nvfortran --verify   # two families, the cases checked in every cell
```

- **Which line applies:** a setup line applies to a mode by its name, else by its compiler (`gnu`, `intel_nextgen`,
  `nvfortran` ...), else by the compiler's family (`gnu`, `intel`, `nvfortran`). The environment it leaves is
  captured once (`bash -c`), and a compiler that is not on its PATH makes the cell `skipped`.
- **Who reads it:** `matrix`, `assess`, `diff-run`, `bench` and `profile`. `build`, `case run`, `verify` and `test`
  use the environment they are started in: load the modules first.
- **In a non-interactive shell** (a job, a CI step) the module command may need its init script and `MODULEPATH`
  first: put them in the setup line.
- **A module swap that keeps the command name** (`gfortran` of gcc 15 instead of 16) is caught: `fobis build`
  records the compiler's path and version in the object directory and rebuilds everything once when they change.

The matrix of compilers and shadows: [Verifying results](./verification).

## Declare the scheduler

Where to submit is a property of the machine: it goes in the user configuration (`~/.config/fobis/config.ini`, or
`$XDG_CONFIG_HOME/fobis/config.ini`). A fobos `[scheduler]` section adds to it, key by key, and its keys win.

```ini
[scheduler]
; the only kind so far, and the default
kind        = slurm
partition   = gpu
account     = myproject
qos         = normal
; how a case with ranks is launched inside the job, {ranks} replaced (default srun)
launcher    = srun --mpi=pmix -n {ranks}
; more #SBATCH options, one per line
options     = --exclusive
              --mem=32G
; shell lines run in the job before the program
setup       = module load nvhpc
; seconds between squeue polls (default 10)
poll        = 10
; host-name patterns of the login nodes, space- or comma-separated
login_nodes = login*
```

The case gives the rest of the job: `ranks` -> `--ntasks`, `threads` -> `--cpus-per-task` and `OMP_NUM_THREADS`,
`gpus` -> `--gpus`, `timeout` -> `--time` (minutes, rounded up, plus 2 for the job's setup lines: a case's default
timeout of 600 s gives 12 minutes),
`env` -> exported in the script.

<<< @/examples/output/5-numerics/09/case.txt{ini}

- **An unknown key or kind stops every command that reads the section** with exit 2, local runs included: the guard
  reads `login_nodes` from it.
- **`kind = slurm` only:** PBS and other schedulers are not supported.
- **`login_nodes`** patterns are shell globs matched against the full host name and its short form
  (`login01.cluster` and `login01`).
- **`options`** lines may start with `#SBATCH` or not.
- **The launcher under `--runner slurm` is the scheduler's:** it replaces `[verification] launcher` for ranked cases,
  and is the default of `fobis test --ranks`.
- **Values are literal,** in the user configuration as in a fobos: `--output=slurm-%j.out` and `--comment=50%` are
  passed as written.
- **`setup` lines may carry `;`:** they are shell, so a comment after `;` is part of the command, not a comment.

## Run cases, tests and benchmarks on compute nodes

```bash
fobis case run --runner slurm                 # each case a job
fobis verify --runner slurm                   # each case a job, compared with its reference
fobis test --runner slurm                     # each test program a job
fobis bench sod --runner slurm --record       # the job's own run time, measured inside the job
fobis assess area --runner slurm              # every member of the ensemble a job
fobis diff-run main --runner slurm            # both sides' runs as jobs
fobis profile gpu --tool nsys --runner slurm  # the case under Nsight Systems, in a job
```

<<< @/examples/output/5-numerics/09/run.measured.txt{console}

<<< @/examples/output/5-numerics/09/update.measured.txt{console}

A reference written on a workstation, checked on a compute node with another compiler: the result is within the
tolerance, and the provenance lists what differs. The machine facts are the node's, recorded by the job itself:

<<< @/examples/output/5-numerics/09/verify.measured.txt{console}

What a run becomes:

1. **Built on the submitting host**, as a local run (same flags, same rebuild guard).
2. **A job script**, `fobis-job.sh` in the run directory: the `#SBATCH` resources, the `setup` lines, the exports,
   then the command (with the launcher for a ranked case) writing `fobis-stdout.txt`, `fobis-stderr.txt`,
   `fobis-exit.txt` (exit status, start, end) and `fobis-host.txt` (the node's host, OS, CPU, processors available to
   the job, the GPUs from `nvidia-smi -L`). Slurm's own log is `slurm-<job>.out` there too.
3. **`sbatch --parsable`**, the submitting environment (the modules loaded) exported to the job. `squeue` is polled
   every `poll` seconds; `slurm: job N submitted`, `pending`, `running` go to stderr. Ctrl-C cancels the job
   (`scancel`) before stopping.
4. **The result:** the exit status and the wall time are the command's own, from the files the script wrote, so they
   exclude queueing and do not depend on the accounting database; `sacct` gives the final state (`COMPLETED`,
   `FAILED`, `TIMEOUT`, `OUT_OF_MEMORY`, ...). A job killed by the scheduler is reported with its state and the last
   line of its Slurm log: status `timeout` for a time limit, `failed` otherwise.
5. **The provenance** gains `scheduler` (kind, partition, account, job, state, node), and the node's facts replace
   the submitting host's in `machine`: a reference or a benchmark history written from a login node describes the
   compute node. Job ids, node names and job states are not reported as provenance changes, and GPUs are compared by
   model, not by serial number.

Pitfalls and limits:

- **Tests** run in `.fobis/runs/test-jobs/<name>/`. A test job asks for `--ntasks` from `--ranks` and `--time` from
  the test's timeout (60 s by default, so 3 minutes with the setup's 2), never for GPUs: a GPU test needs `--gpus=1` in the fobos's
  `[scheduler] options`. With `-j N`, N jobs are in the queue at once.
- **`bench`** measures the job's own run time; CPU time and load average are not measured (they would be the login
  node's).
- **Scratch copies** of `diff-run` and `bench --compare` are made in `.fobis/scratch` instead of `/tmp`, which the
  nodes do not see.
- **Memory.** Slurm gives a job its partition's default memory, often per CPU (`scontrol show config | grep
  DefMemPer`). On the cluster FoBiS was tested on (`DefMemPerCPU = 1024` MB), two ranks with a GPU each under Nsight
  Systems ended with `srun: error: ...: Out Of Memory`; `options = --mem=32G` fixed it. Any `#SBATCH` option goes in
  `options`.
- **`fobis run` has no `--runner`:** submit a program of your own as a case (a `[case:NAME]` with its `target`, or a
  `command`).
- **Tested on a real cluster:** Slurm 23.11, NVIDIA A30 nodes, nvfortran 25.5 with HPC-X Open MPI and
  `launcher = srun --mpi=pmix -n {ranks}`: an MPI case (4 ranks), an OpenACC case (1 GPU), an MPI+OpenACC case
  (2 ranks, 2 GPUs), `case run`, `verify --update` then `verify`, `test`, `profile --tool nsys`, and the guard.

## The login-node guard

On a host matching `login_nodes`, a case with `ranks` or `gpus` is not run locally:

<<< @/examples/output/5-numerics/09/guard.measured.txt{console}

- **Cases** (`case run`, `verify`, `assess`, `bench`, `diff-run`, `profile`) get the status `error` with this message,
  and the command exits 1.
- **`fobis run --ranks` and `fobis test --ranks`** stop before building, with exit 2 and the same message for "an MPI
  program". `fobis test --runner slurm` is accepted; `fobis run` cannot be submitted (the message names
  `--runner slurm` all the same).
- **Serial runs still run locally:** a small check on the login node is usually allowed; MPI and GPU runs are what
  cluster policies forbid. A launcher without `--ranks` (valgrind, gdb) is not refused.

## What stays local

`fobis matrix` and `fobis gate` drive nested `fobis` commands and run them on the host they are started on; neither
takes `--runner`. On a login node, their nested case runs meet the guard: an MPI or GPU case fails the matrix cell or
the gate's verify stage. Run them on a workstation or inside an interactive allocation (`salloc`, `srun --pty`), or
gate the GPU cases with `fobis verify --runner slurm` as a separate step.

## Where the GPU time goes: Nsight Systems in a job

```bash
fobis profile gpu --tool nsys --runner slurm
```

<<< @/examples/output/5-numerics/09/nsys.measured.txt{console}

The kernels take under 3 ms; copying all the samples back to the host at line 25 takes 0.19 s, 70 times as long. The
host needs only two samples:

<<< @/examples/output/5-numerics/09/fix.txt{console}

<<< @/examples/output/5-numerics/09/nsys-fixed.measured.txt{console}

- **One report per process,** named after its MPI rank (`SLURM_PROCID`, `OMPI_COMM_WORLD_RANK` or `PMI_RANK`); with
  several ranks the profile gives each process's kernel time and the imbalance.
- **Kernels map to their directive:** nvfortran names a kernel after its procedure's scopes and the directive's line
  (`area_acc_21_gpu`, `..._gpu__red` for a reduction's last step; OpenMP `nvkernel_...F1L<line>_...`).
- **`nsys stats` runs on the submitting host** after the job: nsys must be on the PATH there too.
- **nsys runs with `TMPDIR=/tmp`.** With `TMPDIR` on a network file system, Nsight Systems 2025.3 recorded no CUDA or
  OpenACC event, without an error. When no kernel is recorded, FoBiS says so and suggests `NVCOMPILER_ACC_NOTIFY=1`
  (every launch printed) and the case's `gpus`.
- **Times, not hardware counters:** Nsight Compute (`ncu`) is not supported; on the test cluster it stopped with
  `ERR_NVGPUCTRPERM` (counters reserved to administrators).
- **gprof and callgrind** run under `--runner slurm` too: [Verifying results](./verification) covers the CPU
  profiles.

Tutorial: [where the time goes](/tutorial/numerics/08-profile), [on a cluster](/tutorial/numerics/09-cluster).

## A cluster without internet

The standalone archive is FoBiS and its whole Python dependency closure in one file, for a cluster where `pip` and
PyPI are out of reach. Build it with `make standalone` from a FoBiS checkout, or download `fobis.pyz` from a release
([installation](/guide/installation)), copy it over, and run it with the cluster's Python 3.10 or later:

```bash
python3 fobis.pyz build --mode gpu
python3 fobis.pyz verify --runner slurm
```

- **Nested commands use the same archive:** `gate`, `matrix`, the case runner's builds and `fetch`'s dependency
  builds run `python3 fobis.pyz ...`, not a `fobis` from the PATH.
- **The compilers come from the cluster:** the archive holds no compiler.
- **Dependencies** fetched elsewhere and copied over: [Dependencies](./dependencies).
- **A local model** for the AI commands, copied with its runtime: [AI setup](./ai-setup).
