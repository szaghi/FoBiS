# Assessing the numerical error of a result

How many digits of a computed result can be trusted, and where the error comes from. The methods below are those
`fobis assess` applies to a declared case, one per family of variants; each section names the method, its
assumptions and its references (full entries in the references document of this pack).

## Significant digits of an ensemble

Run the same computation several times with a perturbation that should not matter (another rounding, compiler,
thread count, input within its uncertainty) and look at the spread of a result `x` over the `n` members. With
mean `mu` and sample standard deviation `sigma`, the number of significant digits the members share is

```
s = -log10(sigma / |mu|)
```

the estimator of Monte Carlo arithmetic (Parker, Pierce and Eggert 2000), also used by Verificarlo. All members
equal means every digit is reproduced (`s` infinite); `mu = 0` makes `s` meaningless (0 reported): assess such a
quantity through a quantity that does not vanish, or by absolute difference.

`sigma` from a few members is itself uncertain. A one-sided 95% lower bound on `s` follows from the chi-square
upper bound of `sigma`, `sigma_up = sigma * sqrt(k / chi2(0.05, k))` with `k = n - 1` degrees of freedom
(exact quantiles for k = 1 and 2, the Wilson and Hilferty 1931 approximation above). With 3 members the bound is
far below the estimate; it tightens as members are added. The bound assumes independent random samples (Sohier
et al. 2021 discuss confidence intervals for stochastic arithmetic): for deterministic variants, such as
compiler flags, it is indicative only.

## Precision family

Rebuild with every real promoted to a wider kind and compare: the digits on which the normal build agrees with the
promoted one estimate the rounding error of the normal build (the promoted build serves as the more accurate
reference, `-log10(|x - x_ref| / |x_ref|)` per point). Measured: a single-precision sum agreed with its promoted
build to 2.0 digits.

Assumptions and limits: the promoted build must be much more accurate (its own rounding negligible), and
promotion must not change the program's logic. Promotion flags cover different declarations per compiler
(compilers pack): a code with a kind module is promoted by changing the kind parameter. Promotion changes binary
record lengths and integer storage tricks: measured, blanket 128-bit promotion broke PENF (`storage_size` stored
into an `integer(1)` parameter).

## Rounding family

Rebuild with flags that change rounding without changing the algorithm: optimisation levels, FMA contraction on
and off, value-unsafe math, vectorisation off. The spread over these members is a cheap, deterministic stand-in
for stochastic arithmetic: it shows how sensitive the result is to the order and fusion of operations, but it
samples a few rounding patterns, not a distribution. Monte Carlo arithmetic (Verificarlo: Denis, de Oliveira
Castro and Petit 2016) and discrete stochastic arithmetic (CADNA: Jézéquel and Chesneaux 2008) perturb every
operation randomly and give a statistically founded estimate; use them when the result matters and they are
available.

Measured: a compensated (Kahan) sum kept every printed digit in every member except `-ffast-math`, which removes
the compensation (Kahan 1965; compilers pack); in FOODIE an exact floating-point equality test
(`final_time - int(final_time/Dt)*Dt == 0`) failed under FMA contraction.

## Compiler family

Build and run the case with the project's other modes (other compilers). Differences in the last digits come
from contraction, reassociation and intrinsic implementations; differences in leading digits from bugs: a
compiler-dependent behaviour (uninitialised variables, aliasing violations, argument mismatches) or a compiler
bug. Rebuild with value-safe flags on every compiler to separate the two (compilers pack, comparison).

## Parallel family

Run with several thread and rank counts, and repeat each. Results that differ between repeats at the same count
are non-deterministic: an unordered floating-point reduction (OpenMP `atomic` or `reduction`, `MPI_Allreduce`
with a varying algorithm) sums in a different order each run. Measured: an OpenMP `atomic` reduction gave
repeats differing by about 3e-5 relative at 4 threads and identical results at 1 thread. Results that differ
between counts but repeat exactly come from a count-dependent order of operations (decomposition-dependent
sums), or from a race that a different count exposes. Bitwise reproducibility needs a fixed reduction order or a
reproducible summation algorithm (Demmel and Nguyen 2015).

## Inputs family

Perturb declared inputs and measure the response. One at a time (each parameter low and high around its
nominal value, the others fixed) gives the elasticity

```
E = ((q_high - q_low) / q0) / ((p_high - p_low) / p0)
```

the relative change of the output per relative change of the input: |E| > 1 amplifies the input's uncertainty.
Measured: for `k^2 exp(-dt)` the elasticities were 2 for `k` and -0.5 for `dt`, the analytic values (`2` and
`-dt` at the nominal `dt = 0.5`). One-at-a-time analysis misses interactions between parameters (Saltelli et al.
2008). Sampling all inputs from their distributions (Monte Carlo) gives the output's spread, with a standard
error decreasing as 1/sqrt(N), and correlations between each input and the output. Measured: a Monte Carlo
standard deviation of 6.1 % matched first-order propagation of the input uncertainty.

## Refinement family

Run the case at three or more levels of a resolution parameter `h` (grid spacing, time step, tolerance) and
measure how a scalar result converges. With levels 3 (coarse), 2, 1 (fine), refinement ratios `r21 = h2/h1`,
`r32 = h3/h2` and differences `e21 = f2 - f1`, `e32 = f3 - f2`:

- ratio `R = e21/e32`: `0 < R < 1` monotonic convergence, `-1 < R < 0` oscillatory, `|R| >= 1` divergent
  (Stern et al. 2001);
- observed order `p` by fixed-point iteration on `p = |ln|e32/e21| + q(p)| / ln r21`,
  `q(p) = ln((r21^p - s)/(r32^p - s))`, `s = sign(e32/e21)` (Celik et al. 2008; with a constant ratio `q = 0`);
- Richardson extrapolation `f_ext = (r21^p f1 - f2) / (r21^p - 1)` (Richardson 1911) and the error estimate
  `|f_ext - f1|`;
- Grid Convergence Index of the fine level `GCI = 1.25 |e21/f1| / (r21^p - 1)` (Roache 1994; factor 1.25 for
  three or more levels).

These hold only in the asymptotic range, where the leading error term dominates. With four or more levels FoBiS
compares the orders of the last two triples and calls the study asymptotic when they agree within 10% (a FoBiS
criterion, not a standard one); otherwise the order is reported as not converged rather than as a property of
the method. Measured: trapezoid rule for the integral of `exp(x)` on [0, 1], order 2.000, the extrapolated value
equal to the exact `e - 1` to 9 digits and the error estimate equal to the true error; RK4 4.06; FOODIE's schemes 1.012 (explicit Euler), 2.016, 3.016 (SSP Runge-Kutta 2 and 3), 4.012 (SSP-RK(5,4)).
Oberkampf and Roy (2010) treat code and solution verification at length.

## Budgets

A budget states what a result must achieve: `digits >= 6`, `order >= 1.9`, `error <= 1e-4`. Choosing it from the
assessment, not before it, keeps it honest: the measured digits of the normal build bound what any tolerance
on the result can promise. A `fobis verify` tolerance tighter than the assessed digits fails on harmless
changes (another compiler, thread count); a looser one hides real changes.
