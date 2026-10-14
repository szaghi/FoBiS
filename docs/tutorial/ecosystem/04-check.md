---
title: 4. Before releasing
---

# 4. Before releasing

A change to `core` is safe only if `mathx` and `app` still build and pass their tests with it. `check` tries
exactly that, before anything is committed or released: it copies each dependent into a scratch directory, puts
`core`'s **working copy** in place of the fetched one, and runs the dependent's checks (its fobos
`[ecosystem] check` commands; the demo's build and run the test program).

<<< @/examples/output/3-ecosystem/04/check.txt{console}

Now a change that breaks the others: `twice` renamed `double` in `core`, not committed.

<<< @/examples/output/3-ecosystem/04/diff.txt{console}

## What the change breaks

`impact` compares the public interface of `core`'s modules with the last release, and finds the code of the
dependents that uses what changed, without building anything:

<<< @/examples/output/3-ecosystem/04/impact.txt{console}

- A removed or changed public entity is a breaking change; an added one is not.
- A dependent is affected only when its code refers to a changed name (a plain `use` of the module is not enough).

## Proof by building

<<< @/examples/output/3-ecosystem/04/broken.txt{console}

The staged copies are kept when a check fails, to look at; the projects themselves were not touched.

::: tip What you learned
`fobis ecosystem check PROJECT` (dependents built against your working copy) and `fobis ecosystem impact PROJECT`
(which public names changed, and who uses them).
:::

Next: [5. Shared boilerplate](./05-scaffold).
