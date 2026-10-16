---
title: 8. Where the time goes
---

# 8. Where the time goes

`fobis profile CASE` builds a case with a profiler's flags, in its own directory, runs it, and maps the
profiler's report to the project: procedures by their module, source lines with their text, the time spent outside
the sources and who calls it.

The default tool is gprof, a sampling profiler:

<<< @/examples/output/5-numerics/08/gprof.measured.txt{console}

The case runs in a few hundredths of a second, so gprof took no sample: only its call counts are facts, as the
note says. callgrind counts the instructions every line executes instead, however short the run (and runs the
program some tens of times slower):

<<< @/examples/output/5-numerics/08/callgrind.measured.txt{console}

85% of the instructions are in `sin`, a library routine, called 8 million times from `integrands::sine`. The
quadrature loops are the rest: making them faster could not gain more than 15%. The new Simpson loops (lines 84
and 88) execute half the instructions of the trapezoid loop each, as they visit half the nodes.

::: info Measured, not generated
Profiles depend on the machine and on its libraries (here glibc's `__sin_fma`): these outputs were recorded once.
:::

On a GPU, `--tool nsys` maps the kernel time to the OpenACC or OpenMP directive lines and reports the host-device
transfers per direction and per source line: chapter 9 uses it on a cluster.

::: tip What you learned
`fobis profile`, `--tool gprof|callgrind|nsys`, reading the share outside the sources. Reference:
[profiling](/cookbook/verification#where-does-the-time-go).
:::

Next: [9. On a cluster](./09-cluster).
