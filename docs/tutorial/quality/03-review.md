---
title: 3. Reviewing a change
---

# 3. Reviewing a change

The linter reports on a whole project; a reviewer looks at a change. `fobis review` reports only the findings on the
lines a change touches: the uncommitted changes by default, the staged ones with `--staged` (a pre-commit hook), or
the commits of a branch with `--base master` (a pull request).

A change to `sweep`: the number of intervals goes into a variable.

<<< @/examples/output/4-quality/03/diff.txt{console}

<<< @/examples/output/4-quality/03/review.txt{console}

`n` is shared by the OpenMP threads, and every thread writes it: a data race. The results would still look right
most of the time, which is what makes races expensive. The whole project is analysed (the rule needs the directive
around the loop), but only the changed lines are reported.

For a pull request, the review is a comment:

<<< @/examples/output/4-quality/03/markdown.txt{console}

The fix is a `private(n)` clause:

<<< @/examples/output/4-quality/03/fixed.txt{console}

::: tip What you learned
`fobis review` (working tree, `--staged`, `--base`), `--format markdown`. Reference:
[`review`](/reference/review), [reviewing a change](/ai/review).
:::

Next: [4. Querying the code](./04-query).
