# Assessing numerical error and uncertainty

`fobis verify` tells you whether a result changed. `fobis assess` tells you how much of it you can trust: it runs an
**ensemble** of variants of a [case](/advanced/cases) — the same program with its arithmetic, compiler, thread count,
inputs or resolution changed — and reports what the spread of each quantity says about its accuracy.

```bash
fobis assess sod                          # the families declared in [assess:sod] (default: rounding)
fobis assess sod --families precision,rounding
fobis assess sod --json                   # for scripts, CI and agents
fobis assess sod --jobs 4                 # four runs at a time
```

Nothing here is specific to a field: the case says what the program computes, the families say how to perturb it.

## Families

| Family | Variants | What the spread estimates |
|--------|----------|---------------------------|
| `precision` | the program rebuilt with its reals promoted (defaults below, or declared flag sets such as a project kind switch `-DRKIND=16`) | digits of the base run that agree with the most precise run |
| `rounding` | compiler-level perturbations: optimisation level, FMA contraction, value-unsafe math, vectorisation | significant digits the members share: round-off and its amplification |
| `compiler` | the case built by other fobos modes (`modes = ...`), each in the environment of its `[verification] setup` | implementation-defined variability, and which compiler is the outlier |
| `parallel` | thread (and rank) counts, each run `repeats` times | digits shared across counts; repeated runs that differ (non-determinism) |
| `inputs` | declared inputs varied one at a time (`rel EPS`) or sampled (`uniform A B`, `normal MU SIGMA`, seeded) | elasticities, or the output's mean, standard deviation and correlation with each input |
| `refinement` | a control parameter on a ladder of values (resolution, step, tolerance) | observed order, Richardson extrapolation, error estimate, GCI, convergence type, asymptotic range |

Default variants, checked on gfortran 16, ifx 2025.3 and nvfortran 26.1:

| | gfortran | ifx / ifort | nvfortran |
|-|----------|-------------|-----------|
| `precision` | `-freal-4-real-8 -freal-8-real-16` (explicit `real64` promoted too) | `-real-size 64 -double-size 128` (default REAL and DOUBLE PRECISION only: `real(real64)` stays 8 bytes) | `-r8` (default REAL only) |
| `rounding` | `-O0`, `-O3`, `-O2 -mfma -ffp-contract=fast`, `-ffp-contract=off`, `-O3 -ffast-math`, `-O3 -fno-tree-vectorize` | `-O0`, `-O3`, `-fp-model precise`, `-fp-model fast=2`, `-no-fma` | `-O0`, `-O2`, `-fast`, `-Kieee`, `-Mnofma` |

The flags are appended to the mode's (the last `-O` wins with all three compilers); each variant is built once, in
its own directory under `.fobis/variant/`. Every run gets a fresh run directory: inputs are edited there, never in
the project.

## Declaring an assessment

```ini
[case:model]
target = src/model.f90
inputs = input/model.nml
quantities = stdout

[assess:model]
families = inputs refinement parallel
inputs =
    k:  namelist input/model.nml k rel 1e-3
    dt: namelist input/model.nml dt rel 1e-3
refine = dt: namelist input/model.nml dt values 0.1 0.05 0.025 0.0125
threads = 1 2 4
repeats = 3
budget = q: digits >= 10; q: order >= 1.9
```

| Key | Meaning |
|-----|---------|
| `families` | the families to run when `--families` is not given (default `rounding`) |
| `precision`, `rounding` | variants, one per line: `NAME: flags` (or the flags alone) |
| `modes` | the other modes of the `compiler` family |
| `threads`, `ranks`, `repeats` | the `parallel` family (default threads 1 2 4 up to the cores, 2 repeats) |
| `inputs` | `NAME: TARGET VARIATION` lines |
| `refine` | `NAME: TARGET values V1 V2 V3 ... [inverse]` (at least 3, coarse to fine; `inverse`: h = 1/value) |
| `samples`, `seed` | Monte Carlo sampling of `inputs` (default 16, seed 0) |
| `budget` | `quantity: digits\|order\|error >=\|<=\|>\|< value`, separated by `;` or new lines |

A target is where the value lives: `namelist FILE VAR`, `keyvalue FILE KEY` (`key = value` or `key: value` lines),
`regex FILE 'PATTERN(with one group)'`, `arg N` (the case's N-th argument), `env VAR`. Files must be among the case's
`inputs`. FoBiS reads the current value first: a target that does not hold a number is an error before anything
runs.

**Budgets** turn the assessment into a check: `digits` is the fewest digits any family found, `order` and `error`
those of the finest refinement triple. A budget that no family that ran can measure is reported as skipped. Exit
code 1 when a budget fails.

## Real assessments

Every number below is real output, on programs whose answer is known.

**A single-precision sum, and the Kahan sum that fixes it.** A million additions of `0.1` in single precision,
assessed with `precision`, `rounding` and `compiler` (another mode with nvfortran 26.1, loaded by a setup line):

```text
assess naive (mode gnu): 9 build(s), 9 run(s)
precision (1 member(s))
  note: default promotion for gnu: -freal-4-real-8 -freal-8-real-16
  total: 2.0 digit(s) agree with precision-promoted: 100958.344 vs 100000
rounding (6 member(s))
  note: compiler-level perturbations (Verificarlo's Monte Carlo arithmetic is not used)
  total: 2.3 significant digit(s) (>= 2.1 at 95%); range 99759.8516 .. 100958.344; outlier rounding-fast-math
compiler (1 member(s))
  total: 2.2 significant digit(s) (>= 1.0 at 95%); range 100022.352 .. 100958.344; outlier compiler-nvf
budgets
  total: digits >= 6: 2.0 FAILED
```

```text
assess kahan (mode gnu): 9 build(s), 9 run(s)
precision (1 member(s))
  total: every digit agrees with precision-promoted: 100000 vs 100000
rounding (6 member(s))
  total: 3.0 significant digit(s) (>= 2.8 at 95%); range 99759.8516 .. 100000; outlier rounding-fast-math
compiler (1 member(s))
  total: every member gives the same value; range 100000 .. 100000
```

Kahan summation keeps every printed digit — except under `-ffast-math`, the outlier: value-unsafe reassociation
simplifies the compensation `(t - s) - y` away and the sum falls back to the naive vectorised result (99759.85). A
compensated algorithm needs its compiler flags too, and the rounding family is what shows it.

**A non-deterministic OpenMP reduction** (an `atomic` update of a single-precision sum), `threads = 1 4`, 3 repeats:

```text
parallel (6 member(s))
  harmonic: 4.5 significant digit(s) (>= 3.2 at 95%); range 15.3102655 .. 15.3110323; outlier threads=4
    NON-DETERMINISTIC at threads=4: 3 repeated runs differ (max rel 3.28e-05)
```

**Refinement.** The trapezoid rule for the integral of `exp` on [0, 1], `n = 8 16 32 64`:

```text
integral: observed order 2.000 (triples: 2.000, 2.000), monotonic, asymptotic
  extrapolated 1.718281826, error estimate 3.5e-05, GCI 2.54e-05
```

The extrapolated value matches e − 1 = 1.718281828 to nine digits, and the error estimate is the fine level's true
error. On a real library, FOODIE's ODE integrators (its `foodie_tester` on the linear constant-coefficient problem,
`Dt = 0.05 ... 0.00625`) recover their design orders: explicit Euler 1.012, SSP Runge-Kutta 2.016, 3.016 and (five
stages) 4.012, all monotonic and in the asymptotic range. There the quantity is the error itself: its extrapolated
value tends to zero, so the GCI, relative to that value, is not meaningful — the order is.

**Inputs.** A model `q = k² exp(-dt)` with `k = 3`, `dt = 0.5`:

```text
q: elasticity (relative change of the output per relative change of the input): k 2, dt -0.5
```

and with `k: normal 3.0 0.03`, `dt: uniform 0.4 0.6`, 64 samples:

```text
q: mean 5.485798829, std 0.3373651749 (1.2 digit(s)); correlation with k +0.21, dt -0.95
```

The relative standard deviation, 6.1 %, is what first-order propagation predicts (√(0.02² + 0.058²)).

**What the families found in FOODIE.** The `rounding` member with FMA contraction did not run: the tester refused
the time step ("the final integration time must be an exact multiple of the time step used"). Its check is
`final_time - int(final_time/Dt)*Dt == 0`: without FMA, `160*0.00625` rounds to exactly 1; fused into one operation,
the representation error of 0.00625 survives and the exact equality fails. The `precision` member failed to build:
promoted to 128-bit reals, a PENF dependency stores `storage_size` of its real kinds in an `integer(1)` parameter,
which overflows. For code that derives facts from its own kinds, a declared kind switch
(`precision = kind16: -DRKIND=16`) is the right variant.

## Notes

- The confidence bound of the significant digits (`>= ... at 95%`) assumes independent random samples (Monte Carlo
  inputs); for deterministic variants (flags, compilers) it is indicative. With two members it is wide by nature.
- Verificarlo (Monte Carlo arithmetic) is not used: the `rounding` family perturbs the arithmetic through the
  compiler.
- Refinement is assessed on scalar quantities (arrays change size with the resolution): probe a norm or a value at a
  point.
- Cost: one build per variant and one run per member, printed on the first line. `--jobs` runs members in
  parallel; builds are sequential.
- `fobis assess --json` (see [JSON output](/advanced/json-output#fobis-assess-json)); the MCP server exposes it as
  the `assess` tool.
