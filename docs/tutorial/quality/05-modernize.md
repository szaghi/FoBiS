---
title: 5. Verified modernisation
---

# 5. Verified modernisation

An automatic fix is only as good as the evidence that it changes nothing. `fobis modernize` applies the fixable rules
in a scratch copy of the project, builds it, runs the tests (and the [cases](../#tracks) when there are), and keeps a
fix only when they pass exactly as on an untouched copy:

<<< @/examples/output/4-quality/05/modernize.txt{console}

When the whole set fails, each rule is tried alone, so a wrong fix is isolated. Nothing is written without
`--apply`:

<<< @/examples/output/4-quality/05/apply.txt{console}

<<< @/examples/output/4-quality/05/diff.txt{console}

<<< @/examples/output/4-quality/05/lint.txt{console}

Without tests or cases the only evidence is the build, which does not prove that a fix keeps the results: then
`--apply` needs `--unverified` too.

::: tip What you learned
`fobis modernize`, `--apply`, what counts as evidence. Reference: [verified modernisation](/advanced/modernize).
:::

Next: [6. C and Python bindings](./06-bindings).
