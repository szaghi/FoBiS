# Cases, quantities and provenance

A **case** tells FoBiS how to run something your project produces and which **quantities** to read from what it
writes. It is the base of FoBiS's verification features: a case's quantities are what [`fobis verify`](/advanced/verify) compares,
what error assessments perturb and what benchmarks time. Every result also records its **provenance**: what
produced it.

```bash
fobis case list              # the declared cases
fobis case run               # build and run them all, print their quantities
fobis case run harmonic --json
fobis provenance             # what a result produced now would depend on
```

## Declaring a case

Cases are fobos sections `[case:NAME]`:

```ini
[case:harmonic]
description = harmonic sums of 1/i
; built with the mode, then run
target      = src/sim.f90
; default: the fobos default mode
mode        = gnu
args        = input/sim.nml
; copied into the run directory (files or directories)
inputs      = input/sim.nml input/mesh/
; OMP_NUM_THREADS
threads     = 2
; MPI ranks, through the launcher below
ranks       = 4
; seconds (default 600)
timeout     = 600
env         = SIM_DEBUG=0
quantities  =
    stdout
    total_re : regex  stdout "total =\s*(\S+)" last
    l2       : column norms.dat 3 all
    residual : json   run.json $.solver.residual
    x        : binary state.bin real64 [4] record 2
    status   : exit

[verification]
; default; srun, mpiexec ... also work
launcher = mpirun -np {ranks}
; default
runs_dir = .fobis/runs
```

| Key | Meaning |
|-----|---------|
| `target` | A program of the project, built with `fobis build --target` and the case's mode, then run. |
| `command` | Instead of `target`: a command run as it is (a path with `/` is relative to the project root). |
| `mode` | The fobos mode to build with; `fobis case run --mode M` overrides it. |
| `args` | Arguments of the program. |
| `inputs` | Files and directories copied into the run directory, at the same relative paths. |
| `threads`, `ranks` | `OMP_NUM_THREADS`, and the number of MPI ranks given to the launcher. |
| `gpus` | GPUs the case needs: requested from the scheduler (`--runner slurm`); with `ranks`, refused on a declared login node. |
| `timeout` | Seconds; the whole process group is killed after it. |
| `env` | More environment variables, `KEY=VALUE`. |
| `quantities` | One per line, `name : kind arguments` (below), or `stdout` alone. |

The fobos `$variables` are substituted as in the modes.

Each run happens in a fresh directory, `<runs_dir>/<case>/<variant>/`, holding the inputs, everything the
program writes, and its `stdout.txt` and `stderr.txt`. Add `.fobis/runs/` to `.gitignore`: `fobis case run`
reminds you when git does not ignore it.

## Quantities

| Kind | Arguments | Reads |
|------|-----------|-------|
| `stdout` (alone) | | Every `name = number` (or `name: number`) line of the standard output |
| `regex` | `SOURCE PATTERN [first\|last\|all]` | The first group of a Python regular expression in `stdout`, `stderr` or a file; `all` by default |
| `column` | `PATH N [first\|last\|all\|ROW]` | Column N (from 1) of a text file; lines without a number there are skipped |
| `json` | `PATH KEYPATH` | A value or an array of a JSON file: `$.solver.res[1]` |
| `hdf5` | `PATH DATASET` | An HDF5 dataset, through h5py when importable, else the `h5dump` tool; the shape is HDF5's (C order: a Fortran `rho(3,2)` is `[2, 3]`), the values in memory order |
| `binary` | `PATH KIND [SHAPE] [record N\|stream]` | `real32`, `real64`, `int32`, `int64` values of a Fortran unformatted sequential file (record N, default 1) or a stream file; `[nx,ny]` records the shape |
| `exit` | | The exit status |

Numbers are read the Fortran way: `1.5D+03`, `NaN`, `-Infinity`, and two fields glued by a missing space
(`1.0E+00-2.5E-01`) are two numbers. A quantity that cannot be read (missing file, no match) is reported with
the reason; it does not stop the others.

## Running

A real run of the case above (a program summing `1/i` that writes text, JSON and unformatted files):

```text
$ fobis case run harmonic
Running case harmonic...
  ok (exit 0, 0.00 s) in .fobis/runs/harmonic/default
    total = 2.083333333333333
    n = 4
    total_re = 2.083333333333333
    glued = 1, -0.25
    l2 = 1.4433756729740643, 0.72168783648703216, 0.48112522432468813
    l1_last = 0.69444444444444431
    residual = 2.083333333333333e-12
    x = 1, 0.5, 0.33333333333333331, 0.25 shape [4]
    n_bin = 4
    status = 0
```

A run's status is `ok` (exit 0, every quantity read), `probe-error` (exit 0, a quantity missing), `failed`
(non-zero exit), `timeout`, `build-failed` (with the build's [diagnoses](/advanced/json-output#diagnosed-build-failures))
or `error` (the program could not be started, an input is missing). `fobis case run` exits with 1 when a run is not
`ok`, and 2 when a case is declared incorrectly.

## Provenance

Every result carries what produced it:

| Field | Content |
|-------|---------|
| `git` | Commit, branch, `dirty`, and a hash of the uncommitted change. Dirty means a tracked file changed or an **untracked source** exists (FoBiS compiles untracked sources); untracked outputs do not count. |
| `dependencies` | The commit of each fetched dependency (`fobos.lock`). |
| `mode`, `compiler` | The effective mode; the compiler, its `--version`, compile, link and preprocessor flags. |
| `environment` | Loaded environment modules (`$LOADEDMODULES`), `OMP_NUM_THREADS`, the MPI launcher's version for cases with ranks. |
| `machine` | Host, OS, CPU model and cores, GPUs (`nvidia-smi -L`), Python. |

`fobis provenance [--mode M] [--json]` prints it for the current state. Toolchains loaded with environment modules
(`module load openmpi/...`) are recorded, and the compiler is the mode's (`fc = mpif90` gives the wrapped
compiler's version): run FoBiS in the same environment as your builds. Comparing two provenances explains a
changed result: a different compiler version accounts for a last-digit drift, a dirty tree for anything.

## For agents

`fobis case list --json`, `fobis case run --json` and `fobis provenance --json` print one JSON document (see
[JSON output](/advanced/json-output#fobis-case-run-json)); the [MCP server](/ai/mcp) exposes them as the tools
`case_list`, `case_run` and `provenance`.
