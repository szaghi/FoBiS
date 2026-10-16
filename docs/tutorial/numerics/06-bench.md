---
title: 6. Is it faster?
---

# 6. Is it faster?

Removing `merge` from the loop could make Simpson's rule faster. A measurement says, a single timing does not: run
times vary from run to run, and only an interval tells whether two medians differ.

The case `fine` runs `area` with four million intervals, and a `[bench:fine]` section says how precisely to
measure it: at least 10 runs, until the median is known within ±2% (95% interval):

<<< @/examples/output/5-numerics/06/bench.txt{ini}

`--compare REF` builds the revision and the working tree in scratch copies and measures them **interleaved**, one
run of each in turn, so that a change of the machine's load affects both alike (the progress lines go to the
standard error, discarded here):

<<< @/examples/output/5-numerics/06/compare.measured.txt{console}

The verdict comes from the intervals, not from the medians: they overlap, so the refactoring is not measurably
faster. The speedup's interval says the same, it contains 1.

::: info Measured, not generated
Timings depend on the machine: the outputs of this page were recorded once and are not compared by the CI. Yours
will differ.
:::

`--record` appends a measurement to `verification/bench/fine.jsonl` with the machine's identity (CPU model, cores,
GPUs, compiler and version). A plain `fobis bench` then compares with the last record of the same machine and
mode, and exits with 1 when the case is measurably slower:

<<< @/examples/output/5-numerics/06/record.measured.txt{console}

<<< @/examples/output/5-numerics/06/history.txt{console}

`--feedback` adds what the compiler did differently on both sides: loops that lost vectorisation, new implicit
host-device copies.

::: tip What you learned
`[bench:NAME]`, `fobis bench`, `--compare`, `--record`, verdicts from intervals. Reference:
[benchmarks](/cookbook/verification#is-it-faster).
:::

Next: [7. One command for all of it](./07-gate).
