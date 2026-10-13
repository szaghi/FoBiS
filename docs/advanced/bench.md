# Benchmarks

"It is faster now" is a claim about a noisy measurement. `fobis bench` measures a declared
[case](/advanced/cases) repeatedly until the median run time is known to a stated precision, and calls a change
faster or slower only when the measurements say so.

```bash
fobis bench                          # the declared benchmarks, against their recorded history
fobis bench sod --record             # measure and append to verification/bench/sod.jsonl
fobis bench --compare v2.0           # the working tree against a revision, runs interleaved
fobis bench --compare HEAD --feedback  # ... plus what the compiler did differently (vectorisation, data movement)
fobis bench --json                   # for scripts, CI and agents
```

## Declaring a benchmark

Any case can be benchmarked; a `[bench:NAME]` section (every key optional) says how:

```ini
[case:sod]
target     = src/app/sod.f90
mode       = gnu-release
quantities = stdout

[bench:sod]
warmup   = 1          ; runs discarded first (caches, page faults, device initialisation)
min_runs = 10
max_runs = 50
target   = 0.02       ; stop when the median's 95% interval is within +-2% of it
max_time = 600        ; seconds of measuring per side, at most
time     = wall       ; or a quantity of the case: a time the program measures itself, in seconds
work     = 1.6e7 cells  ; work per run: a throughput (cells/s) is reported
```

Without names, `fobis bench` runs the cases with a `[bench:]` section (all cases when none has one).

## What is measured

- **The median and its 95% interval.** Timings are skewed (a run can be slowed, never sped up, by the rest of the
  machine), so no normal distribution is assumed: the interval is the distribution-free one from the order
  statistics of the sample, `[x(k), x(n+1-k)]` with the largest `k` such that `P(Binomial(n, 1/2) < k) <= 2.5%`.
  It exists from 6 runs (then it is the smallest and largest run). The MAD (median absolute deviation) and the
  fastest run are reported too.
- **Stopping.** After the warm-up, runs continue until the interval's half-width is below `target` (and
  `min_runs` are done), or `max_runs`, or `max_time`.
- **CPU/wall**: CPU time of the run (user + system, from the operating system's accounting of child processes)
  over its wall time: about the number of cores the program kept busy. A serial program reads slightly above 1 on
  some kernels (accounting granularity: 1.04 measured on WSL2).
- **Throughput**: `work / median`.
- **Load**: the 1-minute load average before each run; a busy machine is reported.

## Comparing

**`--compare REF`**: the revision is extracted and the working tree copied into scratch copies (as
[diff-run](/advanced/diff-run) does: your tree and repository are never written), both built, then measured
**interleaved** — one run of each side in turn — so a drift of the machine (another job starting, thermal
throttling) affects both alike.

**The verdict** is decided by the intervals, not by the medians: **faster** when the working tree's interval lies
entirely below the revision's, **slower** when entirely above, otherwise **no measurable difference**. The
speedup (`old median / new median`) comes with a conservative interval `[old low / new high, old high / new low]`.
Exit status 1 when a case is measurably slower (or fails), so CI can gate on it.

**History.** `--record` appends the measurement to `verification/bench/<case>.jsonl` (`[verification] bench_dir`):
date, commit, dirty flag, mode, flags, the statistics, and the machine key (CPU model, cores, GPU models, compiler
and version; GPU serial numbers are not recorded). A plain `fobis bench` compares with the newest record of the
same machine, compiler and mode. Nothing is recorded without `--record`.

## Compiler feedback

`--compare REF --feedback` builds both sides once more with the compiler's report flags added to the benchmark's
own (gfortran `-fopt-info-vec-optimized -fopt-info-vec-missed`, nvfortran `-Minfo=accel,mp,vect`), reads the
reports with the parsers of [compiler feedback](/ai/lint#compiler-feedback) and compares, per procedure, the number
of vectorised loops, loops not vectorised, implicit host/device copies (per variable) and sequential device loops.
Counts, not lines: code that moved does not matter. A loop that lost vectorisation, a new implicit copy or a new
sequential device loop is a **REGRESSION**, located at the new side's lines; a change in a procedure that exists on
one side only is reported as *added/removed procedure*, never as a regression.

## Notes

The report says when a measurement deserves less trust:

- the interval did not reach the target (stopped at `max_runs`/`max_time`), or there are too few runs for one;
- the median run is shorter than 10 ms: wall time is then mostly process start-up — enlarge the case or let the
  program time itself (`time = NAME`);
- the machine was busy (load average above half the cores);
- a device build (OpenACC, CUDA Fortran, OpenMP offload flags) timed by wall time includes start-up, device
  initialisation and transfers: print a wait-bracketed `system_clock` time instead (hpc-practice pack, *GPU
  Benchmark Timing*);
- a consumer GPU (GeForce): its FP64 throughput is 1/64 of FP32 (hpc-practice pack, *the FP64 trap*).

## Real runs

**A slowdown caught and explained.** An `axpy` loop over 2·10⁶ doubles, 100 steps; the working tree adds a
loop-carried recurrence (`y(i) = y(i) + a*x(i) + 1e-30*y(i-1)`). gfortran 16, `-O3`, on a machine running other jobs:

```text
bench axpy (mode gnu, wall time)
  v1: median 0.1301 s [0.1249, 0.1333] 95%, MAD 0.006599 s, min 0.108 s, 30 runs, CPU/wall 1.04; throughput 1.538e+09 updates/s
  working tree: median 0.2801 s [0.2762, 0.2895] 95%, MAD 0.00816 s, min 0.2689 s, 30 runs, CPU/wall 1.05; throughput 7.141e+08 updates/s
  vs v1: speedup 0.464 [0.431, 0.482]: slower
  REGRESSION: axpy: loop not vectorized 0 -> 1 at src/kern.f90:9
  REGRESSION: axpy: vectorized loop 1 -> 0 was at src/kern.f90:9
```

The same with nvfortran 26.1 `-fast`: speedup 0.517 [0.476, 0.580], slower, the same loop no longer vectorised.

**No difference claimed where there is none.** Adding a second statement to the same memory-bound loop: medians
0.131 s and 0.141 s, speedup 0.931 [0.827, 1.121] — *no measurable difference (the intervals overlap)*; a
comparison of medians alone would have reported a 7% slowdown.

**A performance claim checked.** StringiFor's commit "perf(string_t): make split, replace, unique, escape, join
and read_* linear" against its parent, on a program splitting, joining and replacing a 20 kB string:

```text
bench split (mode tests-gnu, wall time)
  bold: median 0.03695 s [0.03163, 0.04953] 95%, MAD 0.004763 s, min 0.03163 s, 8 runs, CPU/wall 1.04
  working tree: median 0.001096 s [0.0009794, 0.002058] 95%, MAD 9.799e-05 s, min 0.0009794 s, 8 runs, CPU/wall 0.85
  vs bold: speedup 33.721 [15.370, 50.576]: faster
  change: split: loop not vectorized 13 -> 3 at src/lib/stringifor_string_t.F90:2945, ...
  added procedure: join_raws: loop not vectorized 0 -> 2 at src/lib/stringifor_string_t.F90:5231, ...
  note: a median run of 1.1 ms: wall time this short is mostly process start-up; ...
  note: the machine was busy: 1-minute load average up to 10.1 on 16 cores while measuring ...
```

The commit is faster beyond doubt; by how much is known only to within [15, 51] here, and the notes say why: the
new side's runs last a millisecond, on a busy machine.

## Limits

- One machine at a time: a comparison across machines is refused by the history key, not adjusted.
- The interval of the speedup is conservative (built from the two medians' intervals), so "no measurable
  difference" can hide a small real change: more runs (`max_runs`, `target`) narrow it.
- Intel compilers are not yet covered by `--feedback` (their reports go to files).

The MCP server exposes the command as the `bench` tool (it never records history). See
[JSON output](/advanced/json-output#fobis-bench-json).
