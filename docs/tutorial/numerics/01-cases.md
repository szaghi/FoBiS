---
title: 1. Cases and quantities
---

# 1. Cases and quantities

A test answers yes or no. A numerical code needs more: *which numbers* it computes, so that a change can be judged
by what it does to them. This track gives `quad` a declared **case** — a program run with given arguments, and the
numbers to read from what it prints — and then builds on it: references, shadow builds, error assessment,
differential runs, benchmarks, and a gate that runs everything.

The case program integrates `sin(x)` over `[0, pi]` (exactly 2) with both rules and `n` intervals, the first
argument:

<<< @/examples/tutorial/5-numerics/01-cases/files/src/area.F90{fortran}

The case, in the fobos:

<<< @/examples/output/5-numerics/01/case.txt{ini}

`quantities = stdout` reads every `name = number` line the program prints; a quantity can also be a regular
expression, a column of a file, a JSON key, an HDF5 dataset, a record of an unformatted file or the exit status
(see [cases and quantities](/cookbook/verification#read-the-quantities)).

<<< @/examples/output/5-numerics/01/list.txt{console}

<<< @/examples/output/5-numerics/01/run.txt{console}

The case is built with its mode (here `release`) and run in a fresh directory of its own, where the program's
output is kept:

<<< @/examples/output/5-numerics/01/files.txt{console}

`.fobis/` holds what FoBiS produces for verification (runs, shadow builds, variants): the chapter adds it to
`.gitignore`.

## Provenance

A number means little without what produced it. `fobis provenance` prints what a result produced now would depend
on: the commit and whether the tree is dirty (an untracked *source* counts, an untracked output does not), the
pinned dependencies, the mode's compiler, its version and flags, the loaded environment modules:

<<< @/examples/output/5-numerics/01/provenance.measured.txt{console}

The output stops before the `machine:` section, which names the host, the CPU model and cores and the GPUs. The
compiler's version and the commit are those of the machine that recorded this page: yours will differ.

Every result of the next chapters carries this record, and every comparison reports what changed in it.

::: tip What you learned
`[case:NAME]`, quantities, `fobis case list` and `case run`, run directories, `fobis provenance`. Reference:
[cases, quantities and provenance](/cookbook/verification#declare-a-case-and-run-it).
:::

Next: [2. References](./02-verify).
