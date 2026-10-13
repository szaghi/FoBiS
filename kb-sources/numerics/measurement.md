# Measuring run time

How to decide whether a change made a program faster, slower, or neither. These are the statistics `fobis bench`
applies; references are listed in full in the references document of this pack.

## Use the median and its interval

Run times are skewed: most runs cluster near a minimum, and interference (other processes, frequency changes,
page cache) adds a long tail of slow runs. The mean and a normal confidence interval assume a symmetric
distribution; the median does not. A distribution-free confidence interval of the median comes from order
statistics: with the `n` times sorted, the interval `[t(k), t(n+1-k)]` covers the median with probability at
least 95% for the largest `k` with `P(Binomial(n, 1/2) < k) <= 0.025` (Conover 1999). Below 6 runs no such
interval exists at 95%: the minimum number of runs is a property of the statistics, not a choice.

Report the median with its interval and the spread (median absolute deviation), not the best run: the best run
is the least representative one (Hoefler and Belli 2015 give twelve rules for reporting performance).

## Compare interleaved, decide by the intervals

Run the two versions alternately (A, B, A, B, ...) rather than all of A then all of B: slow drifts of the
machine (thermal throttling, a job starting elsewhere) then affect both. Call a version faster only when the two
median intervals do not overlap; the speedup `old/new` then lies in `[old.low/new.high, old.high/new.low]`.
Overlapping intervals mean "no measurable difference with these runs": more runs narrow the intervals, and
`fobis bench` keeps running until the relative half-width of each interval is below the declared target (default
2%) or a run or time limit is reached.

Measured: a memory-bound loop with one more statement gave medians of 0.131 s and 0.141 s and a speedup interval
of [0.827, 1.121], which contains 1: no measurable difference, although the medians differ by 8%.

## Conditions that invalidate a measurement

- Very short runs: below about 10 ms the program's start-up (loader, runtime initialisation, MPI start) is a
  large part of the time; measure a larger problem or time the kernel inside the program.
- A loaded machine: a load average above half the cores means the runs compete for processors and memory
  bandwidth; the intervals widen and the medians move. Note the load with the result.
- Warm-up: the first run pays for page faults, file cache misses and, on GPUs, context creation and code
  loading; discard it.
- GPU timing: device work is asynchronous. A host timer around a kernel launch measures the launch, not the
  kernel, unless the code waits for the device before reading the timer (hpc-practice pack, GPU benchmark
  timing). Consumer GPUs run 64-bit arithmetic at a small fraction of their 32-bit rate (hpc-practice pack).
- Different machines, compilers or modes: comparing against history is meaningful only for the same CPU, core
  count, GPU models, compiler and version, and mode.

## CPU time versus wall time

The CPU time of the child processes (`getrusage`) divided by the wall time shows how parallel a run was: about 1
for a serial program, about the thread count for a well-parallelised OpenMP run, much less when threads wait.
Measured on WSL2: serial programs showed a ratio of about 1.04, from accounting granularity (confirmed with
`/usr/bin/time`), not from parallelism.
