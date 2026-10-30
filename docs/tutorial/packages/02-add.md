---
title: 2. Find, add and remove
---

# 2. Find, add and remove

`solver` is a new project of the lab: it computes the length of a vector with `kinds` and `vectors`.

<<< @/examples/tutorial/7-packages/02-add/files/src/solver.f90{fortran}

## Find

By words (in names, descriptions and keywords), by the module a program uses, or by build system:

<<< @/examples/output/7-packages/02/search.txt{console}

<<< @/examples/output/7-packages/02/module.txt{console}

<<< @/examples/output/7-packages/02/build-system.txt{console}

`fobis info` reads the source itself, not the index: its versions are the repository's tags, its modules those of
the newest version.

<<< @/examples/output/7-packages/02/info.txt{console}

## Add

A name found in two indexes, from two different sources, is never resolved silently:

<<< @/examples/output/7-packages/02/ambiguous.txt{console}

The qualified name chooses:

<<< @/examples/output/7-packages/02/qualified.txt{console}

A module names the package providing it, when only one does:

<<< @/examples/output/7-packages/02/by-module.txt{console}

A URL needs no index at all. `timer` is in none:

<<< @/examples/output/7-packages/02/by-url.txt{console}

## Remove

`solver` does not need `timer` after all:

<<< @/examples/output/7-packages/02/remove.txt{console}

`remove` takes out the entry and the comment line `add` wrote above it. What is left in the fobos:

<<< @/examples/output/7-packages/02/dependencies.txt{ini}

Each entry names a source and a range starting at the newest version. The fobos never names an index: `fetch` and
`build` never read one, so the project keeps building if every index disappears.

## Fetch and build

<<< @/examples/output/7-packages/02/fetch.txt{console}

<<< @/examples/output/7-packages/02/run.txt{console}

::: tip What you learned
`fobis search` (`--module`, `--build`), `fobis info`, `fobis add` with a name, a qualified name, `--module` or a
URL, `fobis remove`. Reference: [`search`](/reference/search), [`add`](/reference/add),
[`remove`](/reference/remove).
:::
