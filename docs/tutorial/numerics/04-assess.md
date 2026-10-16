---
title: 4. How accurate is the result?
---

# 4. How accurate is the result?

`fobis verify` says whether a number changed. `fobis assess` says how far it can be trusted: it runs an
**ensemble** of variants of the case and reads the spread. Three families here:

<<< @/examples/output/5-numerics/04/section.txt{ini}

- `refinement`: the case at `n` = 8 ... 128 intervals (`arg 1`: the program's first argument), `inverse` because the
  interval width is `h = 1/n`. The observed order of convergence comes from successive triples.
- `precision`: the case rebuilt with its reals promoted (gfortran's `-freal-8-real-16`): how many digits of the
  base run survive in a more precise run.
- `rounding`: the case rebuilt with compiler-level perturbations (optimisation level, FMA contraction,
  `-ffast-math`, vectorisation): how many digits every variant shares.

The budget makes the assessment a check: the orders the two rules must reach.

<<< @/examples/output/5-numerics/04/assess.txt{console}

Reading it:

- **refinement**: the trapezoidal rule converges with order 2, Simpson's with order 4, both in the asymptotic range
  (the last triples agree). The Richardson extrapolation and the error estimate say how far the 128-interval
  result is from the limit; the GCI is the grid convergence index, a conservative error band.
- **precision** and **rounding**: about 16 digits agree. In this program the error that matters is the
  discretisation error, not round-off.
- **budgets**: both orders met. `fobis assess` exits with 1 when one is not.

Each family names the section of the `numerics` knowledge pack that describes its method and its assumptions:

<<< @/examples/output/5-numerics/04/method.txt{console}

::: tip What you learned
`[assess:NAME]`, the refinement, precision and rounding families, budgets. Other families vary the compiler,
the thread count and the inputs. Reference: [error and uncertainty assessment](/cookbook/verification#how-many-digits-can-you-trust).
:::

Next: [5. Is a refactoring harmless?](./05-diff-run).
