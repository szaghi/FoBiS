---
title: Verifying results
---

# Verifying results

## Declare what a program computes

```ini
[case:sod]
target     = src/sod.f90
mode       = release
args       = input.nml
inputs     = input.nml
quantities =
    stdout
    l1   : column errors.dat 3 last
    mass : regex stdout "total mass =\s*(\S+)" last
```

```bash
fobis case run sod
```

Quantities come from the standard output (`name = number` lines), regular expressions, columns of text files, JSON,
HDF5 datasets and unformatted files. Tutorial: [cases and quantities](/tutorial/numerics/01-cases). Guide:
[cases](/advanced/cases).

## Catch a change of the results

```bash
fobis verify --update      # once, when the results are right; commit verification/references/
fobis verify               # every time after
```

A failure names the quantity, the worst point and what changed since the reference (compiler, flags, commits,
machine). Tutorial: [references](/tutorial/numerics/02-verify).

## Allow round-off differences

In the case:

```ini
[case:sod]
target     = src/sod.f90
quantities = stdout
tolerance  = mass: rel 1e-12; l1: abs 1e-14; *: ulp 4
```

Tutorial: [is a refactoring harmless?](/tutorial/numerics/05-diff-run).

## Results that change from run to run

```bash
fobis verify --repeat 3
```

Three runs must agree exactly before they are compared with the reference: a race or an unseeded random number
shows up here. `fobis assess` with the `parallel` family measures the spread across thread counts.

## Compare with another revision

```bash
fobis diff-run main            # build and run main and the working tree, compare every case
fobis diff-run v1.2.0 --assess
```

Neither your tree nor your repository is touched. Guide: [differential runs](/advanced/diff-run).

## How accurate is a result?

```ini
[assess:sod]
families = refinement precision rounding
refine   = n: arg 1 values 100 200 400 800 inverse
budget   = l1: order >= 1.9
```

```bash
fobis assess sod
```

Observed order of convergence, extrapolated value, digits that survive higher precision and compiler
perturbations. Tutorial: [how accurate is the result?](/tutorial/numerics/04-assess).

## Is it faster?

```ini
[bench:sod]
min_runs = 10
target   = 0.02
```

```bash
fobis bench sod --compare main
fobis bench sod --record
```

Faster or slower only when the 95% intervals of the medians do not overlap. Tutorial: [is it faster?](/tutorial/numerics/06-bench).

## Everything in one command

```bash
fobis gate
fobis gate --base main
```

Tutorial: [one command for all of it](/tutorial/numerics/07-gate).
