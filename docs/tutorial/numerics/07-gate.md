---
title: 7. One command for all of it
---

# 7. One command for all of it

`fobis gate` runs the checks of this track (and the review of track 4) in order, each as a `fobis ... --json`
command, and reduces each to pass or fail with its first failing fact. A stage that does not apply (no change to
review, no case declared) is skipped with its reason. `[gate]` adjusts it:

<<< @/examples/output/5-numerics/07/section.txt{ini}

`skip = bench` keeps timings out of the gate, since a CI runner is not a quiet machine. The matrix stage runs the
`fast` mode with and without the `checks` shadow.

<<< @/examples/output/5-numerics/07/gate.txt{console}

The new case `fine` of chapter 6 has no reference yet. Once its result is right:

<<< @/examples/output/5-numerics/07/update.txt{console}

<<< @/examples/output/5-numerics/07/pass.txt{console}

`fobis gate` exits with 0 when every blocking stage passes: one line in a CI workflow, or the check an agent runs
before it says it is done. `--base main` gates a topic branch against its merge base (the review covers the whole
branch), `--fail-fast` stops at the first failure, `advisory = ...` reports stages without blocking.

::: tip What you learned
`fobis gate`, `[gate]` (`skip`, `advisory`, `matrix_modes`), `--base`. Reference: [the gate](/advanced/gate).
:::

Next: [8. Where the time goes](./08-profile).
