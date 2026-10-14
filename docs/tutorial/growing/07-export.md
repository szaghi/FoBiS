---
title: 7. Other build systems
---

# 7. Other build systems

Not every user of `quad` will have FoBiS. Two exports give them a build without it.

## fpm

The [Fortran Package Manager](https://fpm.fortran-lang.org) reads an `fpm.toml`. `fobis fpm export` writes one from
the fobos and the sources (`--print` shows it without writing):

<<< @/examples/output/2-growing/07/fpm.txt{console}

The notes say what does not translate: fpm has its own profiles instead of modes, and it compiles every file of the
library directory into the library, programs included. `fobis fpm import` goes the other way, from an `fpm.toml` to a
fobos.

## A GNU Makefile

`--makefile FILE` writes a Makefile for the mode instead of building:

<<< @/examples/output/2-growing/07/makefile.txt{console}

The Makefile holds a compile rule for every source the mode scans (the fetched PENF checkout included); its default
goal is the mode's target, and `make` compiles only what that needs:

<<< @/examples/output/2-growing/07/make.txt{console}

The exports are snapshots: generate them again when the fobos changes, for instance with a [rule](./05-rules).

::: tip What you learned
`fobis fpm export` (and `import`), `fobis build --makefile`. Reference: [fpm](/advanced/fpm),
[Makefile export](/advanced/makefile).
:::

This is the end of the second track. The [third](../ecosystem/01-register) leaves `quad` for a while: a family of projects that
depend on each other, managed together.
