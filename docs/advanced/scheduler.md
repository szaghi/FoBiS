# Running on a cluster

On a cluster the programs are built on the login node and must run on compute nodes. With `--runner slurm`, the
commands that run programs — `case run`, `verify`, `test`, `assess`, `bench`, `diff-run` — submit every run as a
Slurm job and read its results exactly as they read a local run: same probes, same JSON, same verdicts.

```bash
fobis verify --runner slurm              # each case a job; quantities compared with the references
fobis test --runner slurm                # each test program a job
fobis bench sod --runner slurm --record  # the job's own run time, measured inside the job
```

## Declaring the scheduler

`[scheduler]` is read from the user config (`~/.config/fobis/config.ini`: the machine — partition, account, login
nodes) and then from the fobos (the project), key by key:

```ini
[scheduler]
kind        = slurm                 ; the only kind so far
partition   = gpu
account     = myproject
qos         = normal
launcher    = srun                  ; how a case with ranks is launched inside the job ({ranks} replaced)
options     = --exclusive           ; more #SBATCH options, one per line
              --mem=32G
setup       = module load nvhpc/26  ; shell lines run in the job before the program
poll        = 10                    ; seconds between squeue polls
login_nodes = login* frontend       ; host-name patterns of the login nodes
```

The case gives the rest: `ranks` -> `--ntasks`, `threads` -> `--cpus-per-task` and `OMP_NUM_THREADS`, `gpus` ->
`--gpus`, `timeout` -> `--time` (minutes, rounded up), `env` -> exported.

## How a run becomes a job

1. The program is built on the submitting host, as for a local run (same rebuild guard, same flags).
2. The run directory is prepared as usual (inputs copied) and the job script `fobis-job.sh` is written into it:
   `#SBATCH` resources, the setup lines, then the command — with the case's launcher for ranked cases — whose
   output, exit status, start and end time are written to files in the run directory.
3. `sbatch --parsable`; the submitting environment (the modules loaded) is exported to the job.
4. `squeue` is polled until the job leaves the queue (pending, running are reported on stderr); Ctrl-C cancels
   the job (`scancel`) before stopping.
5. `sacct` gives the final state (`COMPLETED`, `FAILED`, `TIMEOUT`, `OUT_OF_MEMORY`, ...). The exit status and the
   wall time are the command's own, from the files the script wrote: they do not depend on the accounting database,
   and the time excludes queueing. A job killed by the scheduler (time limit, memory) is reported with its state and
   the last line of its Slurm log.
6. The probes read the run directory: the result is the same `RunResult`, its provenance extended with
   `scheduler` (kind, partition, account, job id, final state, compute node). The job also records the facts of
   the node it ran on (host, OS, CPU model, processors available to the job, the GPUs it was given, from
   `nvidia-smi -L`), and these replace the submitting host's in the provenance's `machine`: a reference or a
   benchmark history written from a login node describes the compute node, not the login node. Job ids and node
   names are not reported as provenance changes, and GPUs are compared by model, not by serial number.

The run directories must be on a file system the compute nodes share: by default they are inside the project
(`.fobis/runs`), and with a scheduler the scratch copies of `diff-run` and `bench --compare` are also made inside
the project (`.fobis/scratch`) instead of `/tmp`.

## The login-node guard

On a host matching `login_nodes`, a case with `ranks` or `gpus` is refused when it would run locally:

```text
refusing to run an MPI or GPU case on the login node login02 ([scheduler] login_nodes): run it through the
scheduler with --runner slurm
```

Serial cases still run locally (a small check on the login node is usually allowed); MPI and GPU runs there are what
cluster policies forbid.

## Notes

- `fobis bench --runner slurm` measures the job's own run time (inside the job). CPU time and load average cannot
  be measured from the submitting host: they are left out.
- `fobis matrix` and `fobis gate` drive nested commands and run locally.
- PBS and other schedulers are not supported yet (`kind = slurm` only).
- **Memory.** Slurm gives a job its partition's default memory, often per CPU (`scontrol show config | grep
  DefMemPer`): a case with one CPU per rank may get little. On the cluster used to test FoBiS (`DefMemPerCPU =
  1024` MB), two ranks with a GPU each under Nsight Systems ended with `srun: error: ...: Out Of Memory`; set it
  with `options = --mem=32G` (any `#SBATCH` option goes there).
- Tested on a real cluster (Slurm 23.11, NVIDIA A30 nodes, nvfortran 25.5 with HPC-X Open MPI and
  `launcher = srun --mpi=pmix -n {ranks}`): an MPI case (4 ranks), an OpenACC case (1 GPU) and an MPI+OpenACC case
  (2 ranks, 2 GPUs), `case run`, `verify --update` then `verify` (PASS), `test`, `profile --tool nsys`, and the
  guard refusing the same cases on the login node. The test suite uses a stand-in Slurm (stub
  `sbatch`/`squeue`/`sacct`/`scancel`/`srun` that run the job script locally) for the job script, polling,
  states, time limit and missing accounting.
