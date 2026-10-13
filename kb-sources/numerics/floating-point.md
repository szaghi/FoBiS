# Floating-point facts behind result differences

Why the same algorithm gives different numbers, and how to compare numbers that are allowed to differ.
References are listed in full in the references document of this pack.

## Rounding and the order of operations

Every floating-point operation rounds its exact result to the nearest representable number (IEEE 754 default
rounding); the relative error of one operation is at most the unit roundoff `u` (2^-24 for 32-bit reals, 2^-53
for 64-bit reals). Addition is therefore not associative: `(a + b) + c` and `a + (b + c)` can differ. Any change
of the order of a sum (vectorisation, a parallel reduction, another compiler's reassociation, a loop
reordering) changes the result within the error bound of the sum, not exactly (Goldberg 1991).

For recursive summation of `n` terms the error bound grows with `n`: `|computed - exact| <= gamma(n-1) * sum|x_i|`
with `gamma(k) = k u / (1 - k u)` (Higham 2002, chapter 4). The bound depends on `sum|x_i|`, not on the sum:
when terms cancel, the relative error of the result can be large.

## Compensated summation

Kahan's compensated summation (Kahan 1965) carries the rounding error of each addition in a correction term and
reduces the bound to about `2u sum|x_i|`, independent of `n` to first order (Higham 2002). It relies on the exact
order of operations: `c = (t - s) - y` is zero in exact arithmetic, so a compiler allowed to reassociate removes
it. Measured: gfortran `-ffast-math`, ifx at its default `-fp-model fast=1`, and ifx `-fp-model fast=2` removed
the compensation; gfortran `-O2`/`-O3`, ifx `-fp-model precise` and nvfortran `-O2`/`-fast` kept it (compilers
pack). Every error-free transformation (TwoSum, TwoProduct, double-double arithmetic) has the same requirement.

## Fused multiply-add

An FMA computes `a*b + c` with one rounding instead of two. It is usually more accurate, but it changes results,
and it breaks code that relies on two roundings: `a*b - a*b` contracted on one side is not 0 (it is the rounding
error of the product), and an expression symmetric in exact arithmetic can become asymmetric. Whether a compiler
contracts depends on its defaults and the target instruction set (compilers pack, comparison): a new `-march`
or a new compiler can change the last digits without any source change.

## NaN, Inf and value-unsafe modes

Under "finite math" assumptions (gfortran `-ffast-math`/`-ffinite-math-only`, ifx `-fp-model fast=2`) the
compiler may delete tests for NaN: measured, `ieee_is_nan(x)` and `x /= x` returned false for a NaN. A code that
checks its results for NaN must be built without these modes, or keep the check in a file compiled without
them. Flush-to-zero modes (nvfortran `-Mflushz`, part of `-fast`) replace subnormal results by zero, which
changes results that pass through very small values.

## Comparing results with a tolerance

Bitwise equality is the right test only for results that must be reproducible exactly (same build, same
inputs, deterministic code). Otherwise compare with a tolerance stated for each quantity:

- absolute `|a - b| <= A`: for quantities that are near zero or have a natural scale;
- relative `|a - b| <= R |ref|`: for quantities far from zero; meaningless where `ref` vanishes;
- in units in the last place (ulp): the number of representable values between `a` and `b`, independent of
  magnitude; a few ulp absorb the reordering of a short computation, not of a long one.

`fobis verify` accepts `abs A rel R ulp N` per quantity (`|a - b| <= A + R |ref|`, or within N ulp); NaN equals
NaN and infinities compare by equality. Derive the tolerance from an assessment of the result (assessment
document) rather than guessing it: the digits that survive harmless perturbations are what a tolerance can
check.

## Reproducibility across runs

A deterministic serial program, built once, gives bitwise-identical results on the same machine unless a
library it calls chooses its code path at run time. Parallel programs do so only when every reduction has a
fixed order: OpenMP `reduction` and `atomic` updates, MPI reductions and GPU atomics do not guarantee one.
Measured: an OpenMP `atomic` sum differed between repeats at 4 threads. `fobis verify --repeat N` checks that N
runs agree exactly before a reference is written; reproducible reduction algorithms exist (Demmel and Nguyen
2015) at extra cost.
