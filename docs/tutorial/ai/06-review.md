---
title: 6. A second reader for a change
---

# 6. A second reader for a change

The OpenMP race of track 4 comes back: `n` written by every thread of the parallel loop in `sweep.F90`, without
`private(n)`. `fobis review` lints the changed lines only:

<<< @/examples/output/6-ai/06/review.txt{console}

`--deep` adds a model's reading of the change: the diff, the changed lines in their procedure, the OpenMP region
they belong to, the documentation of the rules that fired, and the files that use a module whose interface
changed:

::: details The model's input (`fobis review --deep-context`)
<<< @/examples/output/6-ai/06/context.txt{console}
:::

<<< @/examples/output/6-ai/06/deep.measured.txt{console}

The findings and the exit status are the linter's; the model adds a summary of the risks, cited, and never
removes a finding. `fobis lint --deep` does the same for the findings of a whole project, region by region.

::: tip What you learned
`fobis review --deep`, `--deep-context`, `fobis lint --deep`. Reference: [reviewing a change](/ai/review),
[linting with a model](/ai/lint).
:::

Next: [7. Commit messages](./07-commit).
