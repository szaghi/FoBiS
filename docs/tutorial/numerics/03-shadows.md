---
title: 3. Defects only some builds see
---

# 3. Defects only some builds see

A new test: every rule integrates an odd function over a symmetric interval to zero. It compares relative errors
with a tolerance:

<<< @/examples/tutorial/5-numerics/03-shadows/files/test/test_symmetry.F90{21 fortran}

The tests run in a new mode, `fast`: the optimised flags of the release profile, with the tests among the sources
(the way a CI would run them):

<<< @/examples/output/5-numerics/03/fast.txt{ini}

<<< @/examples/output/5-numerics/03/test.txt{console}

It passes, and it cannot fail: the exact value is zero, so `relative` divides by zero. The midpoint rule's result
is exactly 0 here, 0/0 is NaN, and `NaN > tolerance` is false. An optimised build computes NaN silently.

## Shadow builds

A **shadow** rebuilds a mode with checking flags added, in its own directory (`.fobis/shadow/<mode>-<shadow>/`),
without touching the mode's build: `checks` (runtime checks, floating-point traps, signalling-NaN
initialisation, at -O0 with -g), `sanitize` (AddressSanitizer and UndefinedBehaviorSanitizer), `strict` (standard
conformance). The flags come from a table per compiler family:

<<< @/examples/output/5-numerics/03/checks.txt{console}

The floating-point trap stops the program at the division: line 21, called from line 10.

## The matrix

`fobis matrix` builds and tests every mode × shadow combination, each from scratch:

<<< @/examples/output/5-numerics/03/matrix.txt{console}

`sanitize` does not see the defect (an invalid operation is not a memory error), `checks` does. With several
modes on several compilers (each loaded by a `[verification] setup` line, such as `module load`), the same
command gives the table of what works where; `--verify` adds the cases, compared with their references and
across cells.

With the relative error made absolute near zero (`abs(s - exact) / max(abs(exact), 1)`):

<<< @/examples/output/5-numerics/03/fixed.txt{console}

::: tip What you learned
`--shadow checks|sanitize|strict` on build, run, test and verify, `fobis matrix`, `--verify`. Reference:
[the compiler matrix](/cookbook/verification#every-mode-every-shadow-every-compiler-the-matrix).
:::

Next: [4. How accurate is the result?](./04-assess).
