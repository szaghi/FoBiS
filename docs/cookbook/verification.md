---
title: Verifying results
---

# Verifying results

A test asks whether a check passes. The verification commands ask whether the **numbers** changed, by how much,
where, and what else changed with them. You declare what a program computes as a case; FoBiS builds it, runs it,
reads its quantities, and compares them with whatever answers your question: results you accepted, other builds,
perturbed variants, another revision, the time the program took.

How it works:

1. **A case.** A `[case:NAME]` section names a program FoBiS builds (`target`) or a command, the mode, the
   arguments, the input files and, optionally, threads, MPI ranks, GPUs and a time limit. Every run happens in a
   fresh directory under `.fobis/runs/`, so runs never see each other's files.
2. **Quantities.** After the run, probes read numbers and arrays from what the program printed or wrote: lines of
   the output, regular expressions, columns, JSON keys, HDF5 datasets, Fortran unformatted records, the exit status.
3. **Provenance.** Every run records what produced it: commit and uncommitted change, dependency pins, compiler,
   version and flags, loaded modules, machine. When two runs disagree, the provenance says what else changed.
4. **One comparison per question.** `verify` compares with a reference you accepted; `matrix` with other modes and
   checked rebuilds of them; `assess` with variants perturbed on purpose; `diff-run` with another revision; `bench`
   compares run times; `profile` maps the time to the code. `gate` runs those that apply and gives one verdict.
5. **Equality is declared.** Two values are equal when the case's tolerance says so: exact by default. A tolerance
   is a claim about the program: it lives in the fobos, next to the case, and is reviewed like code.
6. **Nothing is written unasked.** References are written only by `verify --update`, benchmark history only by
   `bench --record`. Checked and perturbed builds go to `.fobis/`; revisions are built in scratch copies. Your tree,
   build directories and repository are never touched. FoBiS does not know the right answer: a reference is the
   answer you accepted, and `assess` measures how much answers spread, not how far they are from the truth (except
   grid refinement, which estimates the discretisation error).

Tutorial: [verified numerics](/tutorial/numerics/01-cases). Reference: [`case`](/reference/case),
[`provenance`](/reference/provenance), [`verify`](/reference/verify), [`matrix`](/reference/matrix),
[`assess`](/reference/assess), [`diff-run`](/reference/diff-run), [`bench`](/reference/bench),
[`gate`](/reference/gate), [`profile`](/reference/profile).

## Declare a case and run it

The smallest case: a program of the project, the mode it is built in, its argument, and every `name = number` line
of its output as a quantity.

<<< @/examples/output/5-numerics/01/case.txt{ini}

<<< @/examples/output/5-numerics/01/list.txt{console}

<<< @/examples/output/5-numerics/01/run.txt{console}

<<< @/examples/output/5-numerics/01/files.txt{console}

```bash
fobis case list                 # the declared cases
fobis case run                  # build and run them all, print their quantities
fobis case run area --mode fast # one case, built in another mode
fobis case run --json           # one JSON document: status, exit code, quantities, provenance per run
```

Every key of a case:

```ini
[case:model]
description = the model on the coarse mesh
; a program of the project, built with the mode (or: command = ./scripts/run.sh, run as it is)
target      = src/model.f90
; default: the fobos default mode; --mode overrides it
mode        = release
args        = input/model.nml
; files and directories copied into the run directory, at the same relative paths
inputs      = input/model.nml input/mesh/
; OMP_NUM_THREADS
threads     = 2
; MPI ranks, through the [verification] launcher
ranks       = 4
; GPUs the case needs: requested from a scheduler, refused on a declared login node
gpus        = 1
; seconds (default 600); the whole process group is killed after it
timeout     = 600
; more environment variables, KEY=VALUE
env         = MODEL_DEBUG=0 MODEL_LOG=quiet
; how equal a rerun must be: see the tolerances below
tolerance   = *: ulp 4
quantities  =
    stdout
    l2 : column norms.dat 3 last

[verification]
; {ranks} is replaced (default mpirun -np {ranks}); srun, mpiexec ... work too
launcher       = mpirun -np {ranks}
; run directories and the cases' programs (default .fobis/runs)
runs_dir       = .fobis/runs
; where verify keeps the references (default verification/references)
references_dir = verification/references
; where bench keeps the history (default verification/bench)
bench_dir      = verification/bench
```

A run's status is `ok` (exit 0, every quantity read), `probe-error` (exit 0, a quantity missing), `failed` (non-zero
exit), `timeout`, `build-failed` (with the build's diagnoses) or `error` (the program could not start, an input is
missing, or the run was refused). `fobis case run` exits 1 when a run is not `ok`, 2 when a case is declared
incorrectly or an unknown case is named.

- **Exactly one of `target` and `command`.** A `command` whose first word holds a `/` is relative to the project
  root. Unknown keys are an error, not ignored. The fobos `$variables` are substituted as in the modes.
- **The target must be among the mode's sources.** It is built with `fobis build --target`, into
  `.fobis/runs/bin/<case>-<mode>`; the mode's own executable is not used.
- **The run directory is recreated for every run:** `<runs_dir>/<case>/<variant>/` (`default` for a plain run)
  holds the inputs, everything the program writes, `stdout.txt` and `stderr.txt`. An input outside the project is
  copied by its name. Add `.fobis/` to `.gitignore`: `fobis case run` reminds you when git does not ignore it.
- **`timeout = 0`** means no time limit.

## Read the quantities

```ini
[case:harmonic]
target     = src/sim.f90
quantities =
    stdout
    total_re : regex  stdout "total =\s*(\S+)" last
    l2       : column norms.dat 3 all
    residual : json   run.json $.solver.residual
    rho      : hdf5   sol.h5 /fields/rho
    x        : binary state.bin real64 [4] record 2
    status   : exit
```

One quantity per line, `name : kind arguments`; lines starting with `#` or `;` are skipped.

- **`stdout` alone** collects every line holding exactly `name = number` (or `name: number`): one number per line.
  A name printed several times becomes an array. A run printing no such line is a probe error, never a vacuous pass.
- **`regex SOURCE PATTERN [first|last|all]`**: the numbers in the first group of a Python regular expression, in
  `stdout`, `stderr` or a file of the run directory; `all` by default.
- **`column PATH N [first|last|all|ROW]`**: column N (from 1) of a text file; lines starting with `#`, `!` or `%`,
  and lines with no number there, are skipped. ROW counts from 1; a negative ROW counts from the end.
- **`json PATH KEYPATH`**: a value or a nested array, `$.solver.res[1]` or `solver.res.1`.
- **`hdf5 PATH DATASET`**: through h5py when it is importable, else the `h5dump` tool (the standalone `fobis.pyz`
  has no h5py). The shape is HDF5's, row-major: a Fortran `rho(3,2)` reads as `[2, 3]`.
- **`binary PATH KIND [SHAPE] [record N|stream]`**: `real32`, `real64`, `int32` or `int64` values, from record N
  (default 1) of a Fortran unformatted sequential file (little-endian 4-byte record markers, the default of
  gfortran, ifx and nvfortran) or from a stream file. `[nx,ny]` records the shape, in Fortran order.
- **`exit`**: the exit status.

Numbers are read the Fortran way: `1.5D+03`, `NaN`, `-Infinity`, and two fields glued by a missing space
(`1.0E+00-2.5E-01`) are two numbers. A quantity that cannot be read is reported with its reason; the others are
still read.

## Record what produced a result

```bash
fobis provenance --mode release        # what a result produced now would depend on
fobis provenance --json
```

<<< @/examples/output/5-numerics/01/provenance.measured.txt{console}

- **`git`**: commit, branch, `dirty`, and a hash of the uncommitted change. Dirty means a tracked file changed or an
  untracked **source** exists (FoBiS compiles untracked sources, listed as `untracked_sources`); untracked outputs do
  not count.
- **`dependencies`**: the commit of each fetched dependency, from `<deps_dir>/fobos.lock`.
- **`mode`, `compiler`**: the effective mode; the compiler, its path, the first line of its `--version`, the
  compile, link and preprocessor flags. With `compiler = mpif90` it is the wrapped compiler's version.
- **`environment`**: `$LOADEDMODULES`, `OMP_NUM_THREADS`, and for a case with ranks the first line of
  `mpirun --version`.
- **`machine`**: host, OS, CPU model, cores, GPUs (`nvidia-smi -L`), Python; under a scheduler, the compute node's.

Two provenances are compared without the date, the host name, the branch, FoBiS's version and scheduler job ids;
GPUs are compared by model, not serial number. Run FoBiS in the environment of your builds: toolchains loaded with
`module load` are part of the record.

## Accept results, then catch a change

```bash
fobis verify --update          # once, when the results are right: write the references
fobis verify                   # every time after
fobis verify area --mode fast  # one case, in another mode
```

<<< @/examples/output/5-numerics/02/update.txt{console}

<<< @/examples/output/5-numerics/02/pass.txt{console}

A one-character change in Simpson's rule:

<<< @/examples/output/5-numerics/02/diff.txt{console}

<<< @/examples/output/5-numerics/02/fail.txt{console}

A reference is `verification/references/<case>.json` (`[verification] references_dir`): the quantities and the
provenance of the run you accepted. Commit it: it is the result you vouch for. `--update` refuses a run that missed a
quantity or whose repetitions differ, and says when the reference comes from uncommitted code:

<<< @/examples/output/5-numerics/07/update.txt{console}

For each quantity the report gives the values out of tolerance, the largest absolute and relative errors, the L2
norm of the difference, and the worst point with its index: `(i,j)`, Fortran order and 1-based, for arrays read
from Fortran binary files; `[i][j]`, row-major and 0-based, for HDF5 and JSON. A NaN or an infinity that appeared or
vanished is listed with its position. A quantity in the reference that the run did not produce fails (`missing`); a
quantity the reference lacks is `new`, not a failure, and the next `--update` records it.

What changed in the provenance since the reference follows: the first suspect next to a failure; next to a pass,
`(results unaffected)`, proof the results did not depend on it. The text report lists 20 changes; `--json` all.
Switching compilers with `module load` and moving to a cluster node, the case still passed:

<<< @/examples/output/5-numerics/09/verify.measured.txt{console}

Statuses: `pass`, `fail`, `no-reference`, `nondeterministic`, `run-failed` (build failure, crash, timeout: with the
build's diagnoses or the end of the error output), `updated`. `fobis verify` exits 0 when every case passes or was
updated, 1 otherwise (no reference included), 2 for a bad declaration or an unknown case.

- **The cases' builds are stricter than `fobis build`.** The case's program is recompiled from scratch when there is
  no record of how its objects were built, when the compiler (path or `--version`) or the flags changed, or when
  another build touched the mode's object directory since. The reason is in the provenance, `rebuilt_because`.
  FoBiS's timestamps alone would keep objects compiled by another GCC loaded under the same command name.

## Allow round-off differences

By default a quantity must be reproduced exactly. Declare a tolerance per quantity in the case:

```ini
[case:sod]
target     = src/sod.f90
quantities = stdout
tolerance  = mass: rel 1e-12; rho: abs 1e-10 rel 1e-8; iters: exact
             *: ulp 4
```

- **`exact`** (the default): identical values. NaN equals NaN; an infinity equals only the same infinity.
- **`abs A rel R`**: equal when `|value - reference| <= A + R * |reference|`; either part alone works.
- **`ulp N`**: within N units in the last place of the reference. It combines with `abs` and `rel`: either test
  passing is enough.
- **`*`** applies to every quantity without its own entry. Entries are separated by `;` or new lines, and a bad
  spec fails when the fobos is read (exit 2), not when a comparison needs it.

The report gives the errors observed also within tolerance, so a tolerance is chosen knowing what it allows:

<<< @/examples/output/5-numerics/05/verified.txt{console}

The same tolerance decides `diff-run` and the disagreements of `matrix`.

## Results that change from run to run

```bash
fobis verify --repeat 3
```

Each case runs three times (run directories `repeat-2`, `repeat-3`), and the runs are compared with the first,
exactly, whatever the tolerance. A difference is non-determinism: an unseeded random number, a reduction whose order
changes with threads or ranks, uninitialised memory, a race. The case is `NONDETERMINISTIC`, with the quantities
that changed, and `--update` refuses to record it. The `parallel` family of `fobis assess` measures the spread across
thread and rank counts.

## Defects only some builds see

A release build tells little about correctness: optimised and unchecked, it lets an index run past an array,
reads an uninitialised variable as whatever was in memory, and turns 0/0 into a silent NaN. A **shadow** rebuilds
any mode with checking flags, in `.fobis/shadow/<mode>-<shadow>/`, without touching the mode's build:

```bash
fobis build --mode fast --shadow checks       # the mode with runtime checks and floating-point traps
fobis run --mode fast --shadow sanitize       # its program under AddressSanitizer
fobis test --mode fast --shadow checks        # its tests built that way (see Testing)
fobis case run --shadow checks                # the cases' programs
fobis verify --shadow checks                  # ... against the references
fobis introspect --compiler --mode fast --shadow strict       # the flags a shadow would use
```

A shadow keeps everything of the mode (sources, include paths, libraries, preprocessor flags, MPI and OpenMP) and
changes only the flags: it removes those that would defeat it (optimisation, fast math, link-time optimisation,
conflicting checks or standards) and adds its own.

| Shadow | gfortran | ifx, ifort | nvfortran |
|--------|----------|------------|-----------|
| `checks` | `-O0 -g -fcheck=all -ffpe-trap=invalid,zero,overflow -finit-real=snan -finit-integer=-9999 -finit-derived -fbacktrace` | `-O0 -g -check all -fpe0 -init=snan,arrays -traceback` | `-O0 -g -Mbounds -Mchkptr -Ktrap=fp -Minit-real=snan -traceback` |
| `sanitize` | `-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined` | ifx: `-O1 -g -fsanitize=address`; ifort: none | none |
| `strict` | `-std=f2018 -pedantic -Werror` | `-stand f18 -warn stderrors -warn errors` | `-Mstandard -Werror` |
| `none` | the mode's own flags, in the shadow's directory | | |

What each catches, measured on programs holding one defect each (gfortran 16, ifx 2025.3, ifort 2024.2,
nvfortran 26.1):

- **`checks`**: out-of-bounds indices with all three (located); an uninitialised real and a division by zero trap
  with gfortran and the Intel compilers. With nvfortran an uninitialised real becomes a quiet NaN
  (`-Minit-real=snan` writes `7FC00000`), not a trap.
- **`sanitize`**: gfortran finds stack and heap overflows, also through an assumed-size dummy; ifx finds stack and
  global overflows and misses that heap overflow. AddressSanitizer misses an overflow that stays inside one object
  (past `a(4)` into the next component of a derived type): `checks` finds it.
- **`strict`**: extensions rejected (`real*8`) with all three.

Two shadows do not exist, and FoBiS says so instead of building something that checks nothing: nvfortran has no
sanitizer (`Unknown switch: -fsanitize=address`), and ifort accepts `-fsanitize=address` with a warning and ignores
it, so a sanitize build with ifort would pass every test unchecked: use ifx (`compiler = intel_nextgen`). Compilers
outside these families (LFortran, NAG, AMD flang, ...) have no shadows; add the flags to a mode of your own.

When a program crashes in an optimised build, `run --explain` and `test --explain` advise rerunning with
`--shadow checks`.

## Every mode, every shadow, every compiler: the matrix

```bash
fobis matrix                                    # every mode x {none, checks}: build, then the tests
fobis matrix --modes fast --shadows none,checks,sanitize,strict
fobis matrix --verify --recheck                 # also the cases; failures rerun under checks
fobis matrix --compilers gnu,nvfortran --no-tests
```

A `fast` mode (release flags, the tests among the sources) passes its tests, and is wrong: a test divides by zero,
and `NaN > tolerance` is false.

<<< @/examples/output/5-numerics/03/fast.txt{ini}

<<< @/examples/output/5-numerics/03/matrix.txt{console}

After the fix:

<<< @/examples/output/5-numerics/03/fixed.txt{console}

For each cell (a mode rebuilt as a shadow), FoBiS:

1. builds the mode **from scratch** in the shadow's directory (a compiler swapped by `module load` under the same
   command name would otherwise leave the old compiler's objects);
2. runs the tests, when the project has test programs (not with `--no-tests`);
3. with `--verify`, runs every case **built in the cell's mode**, compares each with its reference when there is one,
   and compares every quantity with the first cell that produced it, with the case's tolerance: a difference is a
   **disagreement**.

A mode whose compiler is not found is `skipped`, a shadow its compiler lacks is `n/a`: the matrix runs what the
machine has and says what it could not run. With `--recheck`, a failed or timed-out test or case of a cell is run
again under `checks` (once per mode), whose runtime checks often turn a crash or a wrong number into a located
message; leaks are not rechecked. A sanitizer failure is reported in one line: the AddressSanitizer error kind,
LeakSanitizer's leaked bytes and allocation site, or UBSan's message, at the first frame in your code.

Compilers often live in environment modules. A `setup` line loads each one: bash commands run before the mode's
cells, and the environment they leave is the cells'.

```ini
[verification]
setup =
    gnu15-release: source /usr/share/lmod/lmod/init/bash; module load gcc/15.2.0
    nvfortran: source /usr/share/lmod/lmod/init/bash; module load nvhpc/26
    intel_nextgen: source /opt/intel/oneapi/compiler/2025.3/env/vars.sh
```

A line is looked up by mode name, then compiler name, then family (`gnu`, `intel`, `nvfortran`). A failing setup
skips the mode, with the end of its output as the reason. Every cell records the first line of its compiler's
`--version` in that environment, so the report shows what really compiled it. The same lines set the environment of
`assess`, `diff-run`, `bench` and `profile`; `case run` and `verify` run in FoBiS's own environment.

What a matrix found, measured:

- **Far from the cause.** A test writing one element past an array, onto a guard value in the same derived type:
  the release builds fail at the program's own `error stop`, or (nvfortran `-fast`) not at all; `--recheck` under
  `checks` locates the write; AddressSanitizer does not see it. An uninitialised variable passes every release build
  silently.
- **Reordered sums.** A series summed at `-O3 -ffast-math`, `-fast` or ifx `-O3` differs from the `-O0` builds by
  about 2e-14 relative: reported with an exact tolerance; whether it matters is what the case's tolerance declares.
- **In real libraries** (FLAP, FiNeR, StringiFor, PENF, BeFoR64, json-fortran): a source that gfortran 16 rejects
  in every mode while ifort builds it (the compiler, not the configuration); constructs beyond the standard under
  `strict` (an integer literal outside the symmetric range, finalized structure constructors, `$` in an
  identifier); LeakSanitizer reports with size and allocation site; and a `checks` trap on an overflow a test
  provokes on purpose (a string converted to an infinite `real(4)`): a trap reports every overflow, intended or not.

`fobis matrix` exits 0 when every cell that ran is ok and nothing disagrees, 1 otherwise, 2 for an unknown mode or
shadow, a bad declaration, `--verify` without cases, or no fobos. Every cell is a full build: 5 modes x 4 shadows is
20 builds; `--modes`, `--shadows`, `--compilers` and `--no-tests` keep it to what you need.

## How many digits can you trust?

`fobis assess` runs an ensemble of variants of a case (its arithmetic, compiler, thread count, inputs or resolution
changed) and reports what the spread of each quantity says about its accuracy.

<<< @/examples/output/5-numerics/04/section.txt{ini}

<<< @/examples/output/5-numerics/04/assess.txt{console}

```bash
fobis assess area                             # the families of [assess:area] (default: rounding)
fobis assess area --families precision,rounding
fobis assess area --jobs 4                    # four runs at a time; builds stay sequential
```

| Family | Variants | What the spread estimates |
|--------|----------|---------------------------|
| `precision` | the program rebuilt with its reals promoted (defaults below, or declared flag sets) | digits of the base run that agree with the last, most precise variant |
| `rounding` | optimisation level, FMA contraction, value-unsafe math, vectorisation | significant digits the members share: round-off and its amplification |
| `compiler` | the case built by other modes (`modes = ...`), each in its `setup` environment | implementation-defined variability, and which compiler is the outlier |
| `parallel` | thread (and rank) counts, each run `repeats` times | digits shared across counts; repeated runs that differ |
| `inputs` | declared inputs varied one at a time (`rel EPS`) or sampled (`uniform A B`, `normal MU SIGMA`) | elasticities; or mean, standard deviation, correlation with each input |
| `refinement` | a control parameter on a ladder of values (resolution, step, tolerance) | observed order, Richardson extrapolation, error estimate, GCI, convergence type, asymptotic range |

The default variants, checked on gfortran 16, ifx 2025.3 and nvfortran 26.1:

| | gfortran | ifx, ifort | nvfortran |
|-|----------|------------|-----------|
| `precision` | `-freal-4-real-8 -freal-8-real-16` (explicit `real64` promoted too) | `-real-size 64 -double-size 128` (default REAL and DOUBLE PRECISION only: `real(real64)` stays 8 bytes) | `-r8` (default REAL only) |
| `rounding` | `-O0`, `-O3`, `-O2 -mfma -ffp-contract=fast`, `-ffp-contract=off`, `-O3 -ffast-math`, `-O3 -fno-tree-vectorize` | `-O0`, `-O3`, `-fp-model precise`, `-fp-model fast=2`, `-no-fma` | `-O0`, `-O2`, `-fast`, `-Kieee`, `-Mnofma` |

The flags are appended to the mode's (the last `-O` wins with all three); each variant is built once, in
`.fobis/variant/<mode>-<variant>/`, and the base run is shared by every family. Every member runs in its own run
directory: inputs are edited there, never in the project. Other compilers need declared variants.

```ini
[case:model]
target     = src/model.f90
inputs     = input/model.nml
quantities = stdout

[assess:model]
families = inputs refinement parallel
; precision and rounding: NAME: flags, one per line (a line of flags alone is named after them)
precision =
    kind16: -DRKIND=16
; the other modes of the compiler family
modes    = gnu-release nvf-release
; parallel: default threads 1 2 4 (up to the cores), the case's ranks, 2 repeats
threads  = 1 2 4
repeats  = 3
; one at a time (rel), or sampled (uniform A B, normal MU SIGMA: Monte Carlo)
inputs =
    k:  namelist input/model.nml k rel 1e-3
    dt: namelist input/model.nml dt rel 1e-3
; at least 3 values, coarse to fine; inverse: h = 1/value (a number of points)
refine   = n: arg 1 values 100 200 400 800 inverse
; Monte Carlo samples (default 16) and seed (default 0)
samples  = 64
seed     = 0
budget   = q: digits >= 10; err: order >= 1.9
```

- **Where an input lives:** `namelist FILE VAR`, `keyvalue FILE KEY` (`key = value` or `key: value` lines),
  `regex FILE 'PATTERN(with one group)'`, `arg N` (the case's N-th argument), `env VAR` (a variable the case's `env`
  sets). Files must be among the case's `inputs`. The current value is read first: a target that does not hold a
  number fails before anything runs. Values are written with 15 significant digits; refinement values as declared.
- **Monte Carlo:** as soon as one input is sampled, every `rel EPS` input is sampled uniformly within ±EPS.
- **Budgets** turn the assessment into a check: `quantity: digits|order|error >=|<=|>|< value`, separated by `;` or
  new lines. `digits` is the fewest any family found; `order` and `error` come from the finest refinement triple. A
  budget no family that ran can measure is `skipped`. `fobis assess` exits 1 when a budget fails or the base run is
  not ok, 2 for an unknown case or family, a bad section, or a family without what it needs (`compiler` without
  `modes`, `inputs` without inputs, `refinement` without `refine`).
- **The method** of each family, its assumptions and references, is in the `numerics` knowledge pack; the report
  names the section:

<<< @/examples/output/5-numerics/04/method.txt{console}

What assessments measured on programs whose answer is known:

- **A single-precision sum and its Kahan fix.** A million additions of `0.1` in single precision: 2 digits agree
  with the promoted build, and the `compiler` family names nvfortran the outlier; a `digits >= 6` budget fails. The
  Kahan sum keeps every digit, except under `-ffast-math`: value-unsafe reassociation simplifies the compensation
  `(t - s) - y` away and the sum falls back to the naive vectorised result. A compensated algorithm needs its
  compiler flags too, and the `rounding` family shows it.
- **Non-determinism.** An OpenMP `atomic` update of a single-precision sum, threads 1 and 4, 3 repeats: 4.5
  significant digits, and the 4-thread runs differ from each other (max rel 3.3e-05).
- **Refinement.** The trapezoid rule for the integral of `exp` on [0, 1], n = 8 ... 64: order 2.000, extrapolated
  value equal to e - 1 to nine digits. FOODIE's ODE integrators recover their design orders (explicit Euler 1.012,
  SSP Runge-Kutta 2.016, 3.016, 4.012). When the quantity is an error, its extrapolated value tends to zero and the
  GCI, relative to it, is meaningless: read the order.
- **Inputs.** `q = k² exp(-dt)`: elasticities 2 and -0.5, exactly; sampled, the relative standard deviation is the
  one first-order propagation predicts.
- **Flags that break code.** FOODIE's FMA member did not run: an exact equality `final_time - int(final_time/Dt)*Dt
  == 0` holds without FMA and fails with it. Its precision member did not build: promoted to 128-bit reals, PENF
  stores `storage_size` of its kinds in an `integer(1)`. For code that derives facts from its own kinds, a declared
  kind switch (`kind16: -DRKIND=16`) is the right variant.

Limits:

- **The 95% bound of the significant digits** assumes independent random samples (Monte Carlo inputs); for
  deterministic variants (flags, compilers) it is indicative, and with two members it is wide by nature.
- **Rounding is perturbed through the compiler;** Monte Carlo arithmetic (Verificarlo) is not used.
- **Refinement and inputs are assessed on scalars** (arrays change size with the resolution): probe a norm or a
  point value. A quantity that echoes the refined parameter is reported as such, not assessed. An outlier is named
  only beyond 8 double-precision ulps from the median.
- **Cost:** one build per variant and one run per member, printed on the first line of the report.

## Is a change harmless?

`fobis diff-run` builds and runs the cases on a revision and on the working tree, and compares every quantity: a
refactoring, a modernisation or an agent's edit checked by running the program, not by reading the code.

```bash
fobis diff-run                  # HEAD vs the working tree, every case
fobis diff-run v2.0.0 sod       # a tag, one case
fobis diff-run main --assess    # judge a difference against the code's own spread
fobis diff-run HEAD --keep      # keep the scratch copies, and print where they are
```

Simpson's rule rewritten to sum the odd and even nodes apart; the last bit of the result moves:

<<< @/examples/output/5-numerics/05/diffrun.txt{console}

`--assess` judges the difference against the digits the working tree's own variants share; here they share every
digit, so the difference is real:

<<< @/examples/output/5-numerics/05/assess.txt{console}

Four ulps declared as the case's tolerance, the change is equivalent:

<<< @/examples/output/5-numerics/05/case.txt{ini}

<<< @/examples/output/5-numerics/05/equivalent.txt{console}

- **Scratch copies.** The revision is extracted with `git archive`, its submodules at the commits it records; the
  working tree is copied (tracked and untracked files, ignored ones excluded); the fetched dependencies of the
  working copy are copied into both. Both are built and run there, then removed: your tree, build directories and
  repository metadata are never written.
- **The cases are the working tree's;** each side builds them with its own fobos. A mode the revision lacks makes
  the revision's run fail (`old-failed`).
- **Each quantity** is compared as `verify` compares, with the case's tolerance. The report lists the files that
  changed and, for Fortran sources, the procedures whose code changed: the first place to look.
- **`--assess`** runs, for a case that differs, the case's `[assess:]` families on the working tree (without
  `inputs` and `refinement`; `rounding` when none is left). A relative difference below 10^-digits is what the code
  produces anyway under a change of flags: the case is `within-uncertainty` instead of `differs`.
- **Statuses:** `equivalent`, `within-uncertainty`, `differs`, `new-failed` (the working tree's run), `old-failed`.
  Exit 0 when every case is equivalent or within uncertainty, 1 otherwise, 2 for an unknown revision or case, or a
  bad declaration.

What it showed on real libraries: StringiFor's commit making `split`, `replace`, `unique`, `escape`, `join` linear
is equivalent on a probe program turning their results into numbers; PENF's "make real str exact" differs exactly
where its message says (`pi` and `1/3` gained their 17th digit, `0.1` did not change, `str(huge)` no longer reads
back as infinity), and the renamed preprocessor macro shows in the provenance changes.

- **The case's program must exist on both sides:** commit a probe program written for the comparison (on a branch)
  first, or compare cases both revisions have.
- **Both sides use the current fetched dependencies:** a revision that pins other versions is built against them,
  and the report says so.
- **Cost:** two builds per case, plus the assessment's with `--assess`.

## Is it faster?

`fobis bench` runs a case until its median run time is known to a stated precision, and calls a change faster or
slower only when the measurements say so.

<<< @/examples/output/5-numerics/06/bench.txt{ini}

<<< @/examples/output/5-numerics/06/compare.measured.txt{console}

<<< @/examples/output/5-numerics/06/record.measured.txt{console}

<<< @/examples/output/5-numerics/06/history.txt{console}

```bash
fobis bench                           # the cases with a [bench:] section (all, when none has one), vs history
fobis bench fine --record             # measure and append to verification/bench/fine.jsonl
fobis bench --compare v2.0            # the working tree against a revision, runs interleaved
fobis bench --compare HEAD --feedback # ... and what the compiler did differently
fobis bench fine --runs 20            # at most 20 runs per side
```

Every key is optional:

```ini
[bench:sod]
; runs discarded first (caches, page faults, device initialisation)
warmup   = 1
min_runs = 10
max_runs = 50
; stop when the median's 95% interval is within +-2% of it
target   = 0.02
; seconds of measuring per side, at most
max_time = 600
; wall, or a quantity of the case: a time in seconds the program measures itself
time     = wall
; work per run: a throughput is reported
work     = 1.6e7 cells
```

- **The median and its 95% interval.** Timings are skewed (a run can be slowed, never sped up, by the rest of the
  machine), so no normal distribution is assumed: the interval comes from the order statistics, `[x(k), x(n+1-k)]`
  with the largest k such that `P(Binomial(n, 1/2) < k) <= 2.5%`. It exists from 6 runs (then it spans the smallest
  and the largest). The MAD, the fastest run, CPU/wall (the cores the program kept busy; a serial program reads 1.04
  on WSL2: accounting granularity) and the throughput are reported too.
- **Stopping.** After the warm-up, runs continue until the half-width is below `target` with `min_runs` done, or
  `max_runs`, or `max_time`.
- **The verdict** comes from the intervals, not the medians: faster when the working tree's interval lies entirely
  below the other, slower when entirely above, otherwise no measurable difference. The speedup (old median / new
  median) carries a conservative interval `[old low / new high, old high / new low]`.
- **`--compare REF`** builds the revision and the working tree in scratch copies (as `diff-run` does) and measures
  them **interleaved**, one run of each in turn, so a drift of the machine (another job, thermal throttling) hits
  both alike.
- **History.** `--record` appends to `<bench_dir>/<case>.jsonl` (default `verification/bench`): date, commit, dirty
  flag, mode, flags, statistics and the machine key (CPU model, cores, GPU models without serials, compiler and
  version). A plain `fobis bench` compares with the newest record of the same key and mode. Nothing is recorded
  without `--record`, which does not combine with `--compare`.
- **`--feedback`** (with `--compare`) builds both sides once more with the compiler's reports (gfortran
  `-fopt-info-vec-optimized -fopt-info-vec-missed`, nvfortran `-Minfo=accel,mp,vect`) and compares, per procedure,
  the counts of vectorised loops, loops not vectorised, implicit host-device copies (per variable) and sequential
  device loops. Counts, not lines, so moved code does not matter. A lost vectorisation, a new implicit copy or a new
  sequential device loop is a `REGRESSION` at the new side's lines; a procedure on one side only is reported as
  added or removed, never as a regression. Intel compilers are not covered (their reports go to files).

The report warns when a measurement deserves less trust: the interval did not reach the target, or too few runs for
one; a median run below 10 ms (mostly process start-up: enlarge the case or use `time = NAME`); a load average above
half the cores; a device build timed by wall time (start-up, device initialisation and transfers included: print a
wait-bracketed `system_clock` time and declare it); a GeForce GPU (FP64 at 1/64 of FP32).

What it measured: a loop given a loop-carried recurrence ran at 0.464 [0.431, 0.482] of the old speed, and
`--feedback` named the loop that lost its vectorisation (gfortran 16 and nvfortran 26.1 alike). A second statement in
the same memory-bound loop moved the medians by 7%, with intervals overlapping (speedup 0.931 [0.827, 1.121]): no
measurable difference, where a comparison of medians would have reported a slowdown. StringiFor's linear `split`
was 33.7 times faster, known only to within [15.4, 50.6] because the new runs lasted a millisecond on a busy machine,
and the notes said so.

`fobis bench` exits 1 when a case fails or is measurably slower, 2 for a bad declaration, an unknown case or
revision, `--feedback` without `--compare`, or `--record` with `--compare`. Comparisons across machines are
refused by the history key, not adjusted.

## One command for all of it

```bash
fobis gate                        # the working tree against HEAD
fobis gate --base origin/master   # everything since the merge base, uncommitted edits included
fobis gate --stage build,test     # only some stages, in this order
fobis gate --skip bench --advisory verify --fail-fast
```

<<< @/examples/output/5-numerics/07/section.txt{ini}

<<< @/examples/output/5-numerics/07/gate.txt{console}

<<< @/examples/output/5-numerics/07/pass.txt{console}

| Stage | Runs | Fails when | Skipped when |
|-------|------|------------|--------------|
| `build` | `fobis build` | the build fails (first diagnosis) | never |
| `review` | `fobis review` of the changed lines | an error or warning finding on a changed line | nothing changed; no git repository |
| `test` | `fobis test` | a test fails (crash located) | no test program in the test directory |
| `verify` | `fobis verify` | a case differs from its reference, or has none | no case |
| `diff-run` | `fobis diff-run BASE` | a case's results changed (worst point, changed procedures) | no case; nothing changed; no git repository |
| `bench` | `fobis bench --compare BASE` | a `[bench:]` case is measurably slower | no `[bench:]`; nothing changed; no git repository |
| `assess` | `fobis assess CASE` for each case with a budget | a budget fails | no `[assess:]` budget |
| `matrix` | `fobis matrix` on the declared modes and shadows (`--verify` when there are cases) | a cell fails or two disagree | no `matrix_modes` |

Each stage is a nested `fobis ... --json` command reduced to `pass`, `fail`, `error` (the command gave no result) or
`skip` with its reason, so "no tests" is never mistaken for "tests pass", and to the first failing fact. When the
build fails, the stages that need it are skipped; the review still runs.

```ini
[gate]
; order and selection (default: all eight)
stages         = build review test verify diff-run bench assess matrix
; still listed in the report, as "skip: by [gate] skip"
skip           = assess
; reported, never failing
advisory       = bench
base           = origin/master
; the mode of build, review and test (the cases keep their own)
mode           = gnu-debug
matrix_modes   = gnu-debug nvf-debug
; default none checks
matrix_shadows = none checks
```

- **The base.** Without one, the change is the working tree against `HEAD`: review, diff-run and bench are skipped
  when there are no uncommitted edits. With `--base REF` (or `base`), the change is everything since the merge base
  of `HEAD` and REF, uncommitted edits included.
- **The command line wins:** `--stage`, `--base`, `--mode` replace the section's values; `--skip` and `--advisory`
  add to them.
- **Exit codes:** 0 pass, 1 when a non-advisory stage fails or errs, 2 for an unknown key or stage, or a base with no
  merge base.

Measured: an uncommitted loop change starting at 2 and carrying a recurrence failed three stages at once: verify
(no reference yet), diff-run (the total moved by 0.1, the procedure named) and bench (slower, speedup 0.465). Gating
StringiFor's linear-`split` commit against its parent: same results, not slower, and one review finding on a line
the commit added.

## Where does the time go?

`fobis profile` runs a case under a profiler and maps the result to the project's procedures (qualified, with file
and line) and source lines.

```bash
fobis profile fine                     # gprof: sampled time and exact call counts
fobis profile fine --tool callgrind    # instructions per function and per source line
fobis profile fine --top 20 --json     # more rows; for scripts and agents
fobis profile gpu --tool nsys --runner slurm   # GPU kernels and transfers, on a compute node
```

<<< @/examples/output/5-numerics/08/gprof.measured.txt{console}

<<< @/examples/output/5-numerics/08/callgrind.measured.txt{console}

| Tool | Build | Measures | Limit |
|------|-------|----------|-------|
| `gprof` (default) | the mode rebuilt with `-pg -g` (`-p` for Intel) | self time sampled every 0.01 s; exact call counts; one file per MPI rank | inlined procedures count in their caller; a run shorter than a sample measures no time |
| `callgrind` | the mode rebuilt with `-g` added, optimisation kept | instructions executed, per function and source line; inlined code keeps its own lines | instructions, not time: memory stalls and vector width are not weighed; many times slower |
| `nsys` | the mode's own build | GPU kernel time and launches, host-device copies per direction, OpenACC transfers per source line, kernel time per rank | times, not hardware counters; nvfortran kernel names only |

- **The builds are variants** in `.fobis/variant/`: the mode's build directory is not touched. The program runs in
  the case's run directory, with its arguments, inputs, ranks and threads; valgrind wraps the program after the MPI
  launcher. gprof needs a program FoBiS builds, not a `command`, and a program that ends normally (it writes
  `gmon.out` at exit).
- **Mapping.** Symbols are demangled (gfortran `__mod_MOD_proc`, ifx `mod_mp_proc_`, nvfortran `mod_proc_`) and
  matched to the procedures of the mode's sources. Callgrind's lines go to their innermost procedure, so a procedure
  the compiler inlined is still found (listed in a note); a line in module scope is reported as such. Costs outside
  the sources (runtime, libc, libraries) are labelled so, with the project procedures that call them directly, their
  call counts and inclusive cost: in FOODIE's tester, `malloc` called 5,765 times by FLAP's argument-group setup
  (11% of the instructions), more than the integration itself.
- **MPI.** gprof writes one `gmon.out.<pid>` per rank; the profile sums them and reports each process's total and
  the imbalance max/mean (1 = balanced).
- **GPU.** Each process runs under `nsys profile`, its report named after its MPI rank; `nsys stats` then reads the
  reports on the submitting host, so nsys must be on the PATH there too. nvfortran names each kernel after its
  scopes and the line of its directive (OpenACC `prog_17_gpu`, `module_proc_17_gpu`, `..._gpu__red` for a
  reduction's last step; OpenMP `nvkernel_<symbol>F1L9_2_`), so kernel time is reported at the directive. nsys runs
  with `TMPDIR=/tmp`: with `TMPDIR` on a network file system, Nsight Systems 2025.3 records no CUDA or OpenACC event
  and reports no error.

An OpenACC program copying all its samples back to the host at line 25, then only the first and the last, the two
it needs:

<<< @/examples/output/5-numerics/09/nsys.measured.txt{console}

<<< @/examples/output/5-numerics/09/nsys-fixed.measured.txt{console}

Not supported: Nsight Compute (`ncu`: occupancy, memory throughput; on the cluster FoBiS was tested on it stopped
with `ERR_NVGPUCTRPERM`, the counters being reserved to administrators) and `perf`. `fobis profile` exits 1 when the
build or the run fails or the profiler wrote nothing, 2 for an unknown case or tool, a tool not on the PATH, or gprof
on a `command` case.

## On a cluster

`case run`, `verify`, `assess`, `diff-run`, `bench`, `profile` and `test` take `--runner slurm`: FoBiS builds
locally, submits each run as a batch job, and records the compute node's facts in the provenance. On a login node
declared in the `[scheduler]` configuration, a case asking for ranks or GPUs is refused instead of run there:

<<< @/examples/output/5-numerics/09/guard.measured.txt{console}

`matrix` and `gate` run locally. Scheduler settings, launchers and the whole workflow: [HPC and clusters](./hpc);
tutorial: [on a cluster](/tutorial/numerics/09-cluster).

## For CI and agents

Every command here takes `--json`: one document on standard output, progress on standard error. `fobis gate --json`
gives the verdict and, per stage, the status, the first failing fact and the commands run. The MCP server exposes
`case_list`, `case_run`, `provenance`, `verify`, `matrix`, `assess`, `diff_run`, `bench`, `gate` and `profile` as
tools; none of them writes references or benchmark history. More in [Continuous integration](./ci) and
[AI assistance](./ai).
