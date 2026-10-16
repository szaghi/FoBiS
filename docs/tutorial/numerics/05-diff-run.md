---
title: 5. Is a refactoring harmless?
---

# 5. Is a refactoring harmless?

Simpson's rule is rewritten to sum the odd and the even nodes apart, without the `merge` in the loop:

<<< @/examples/tutorial/5-numerics/05-diff-run/files/src/quad_rules.F90{82-90 fortran}

The tests pass:

<<< @/examples/output/5-numerics/05/test.txt{console}

The reference does not:

<<< @/examples/output/5-numerics/05/verify.txt{console}

The result moved by one unit in the last place (2.2e-16 relative): the sums are added in another order. Tests
with a tolerance of 1e-14 cannot see this; an exact reference can.

## Against a revision

A reference is one point in history. `fobis diff-run REF` compares the working tree with any revision directly:
both are copied to a scratch directory (your tree and repository are never touched), built, and run on every case:

<<< @/examples/output/5-numerics/05/diffrun.txt{console}

It also names the procedures whose lines changed (`quad_rules::simpson`), so a difference points to its cause.
`--assess` weighs the difference against the working tree's own spread under compiler perturbations (the rounding
and precision families of the case's assessment):

<<< @/examples/output/5-numerics/05/assess.txt{console}

Here every variant of the new code gives the same simpson value, so even a one-ulp difference is beyond the spread:
the change is real, not compiler noise. Whether it is acceptable is a decision the case has to state.

## Saying what equivalent means

A **tolerance** in the case: four ulps for every quantity (`*`). Absolute (`abs A`), relative (`rel R`) and ulp
tolerances can be combined, per quantity:

<<< @/examples/output/5-numerics/05/case.txt{ini}

<<< @/examples/output/5-numerics/05/equivalent.txt{console}

<<< @/examples/output/5-numerics/05/verified.txt{console}

The reference stays as it was: the new result is within the declared tolerance of it. "Results unaffected" is the
verdict on the listed changes.

::: tip What you learned
`fobis diff-run REF`, `--assess`, `tolerance = q: spec; *: spec` (`exact`, `abs`, `rel`, `ulp`). Reference:
[differential runs](/cookbook/verification#is-a-change-harmless), [tolerances](/cookbook/verification#allow-round-off-differences).
:::

Next: [6. Is it faster?](./06-bench).
