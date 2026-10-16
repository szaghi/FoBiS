---
title: 2. References
---

# 2. References

`fobis verify` runs the cases and compares their quantities with **references**: files recording the values a
correct version produced. The first time, write them:

<<< @/examples/output/5-numerics/02/update.txt{console}

A reference is written only with `--update`, never as a side effect: it is the claim "these numbers are right",
made by you. It holds the quantities and the provenance of the run that produced them, and belongs in the
repository (`verification/references/area.json`; the chapter commits it).

<<< @/examples/output/5-numerics/02/pass.txt{console}

## A wrong change

Now a slip in Simpson's rule: the weights 4 and 2 swapped (`mod(i, 2) == 0` for `== 1`). It compiles, and the
program still prints a number close to 2:

<<< @/examples/output/5-numerics/02/diff.txt{console}

<<< @/examples/output/5-numerics/02/fail.txt{console}

The failure names the quantity, by how much it is off, and what changed since the reference: here only the
working tree (`dirty`, and the hash of the uncommitted diff). A different compiler version or another dependency
commit would be listed too, which is how a last-digit drift after a toolchain upgrade is told apart from a bug.

The default comparison is exact. Chapter 5 declares a tolerance, when a refactoring is allowed to move the last
bits.

::: tip What you learned
`fobis verify`, `--update`, references in the repository, a failure explained by its provenance. Reference:
[verifying results](/cookbook/verification#accept-results-then-catch-a-change).
:::

Next: [3. Defects only some builds see](./03-shadows).
