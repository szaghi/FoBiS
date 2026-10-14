---
title: 3. A library
---

# 3. A library

`quad_rules` is meant for other programs too. Two more modes build it as a library, static and shared:

<<< @/examples/tutorial/1-first-steps/03-library/files/fobos{ini}

- `target` is the module's file, `mklib` the kind of library, `output` its name.
- The shared library needs position-independent code: `-fPIC`.
- `track_build` records what the build produced, for `fobis install`.
- Each library has its own `build_dir`: two modes that build the same target into one directory would overwrite each
  other's record.

<<< @/examples/output/1-first-steps/03/static.txt{console}

<<< @/examples/output/1-first-steps/03/shared.txt{console}

<<< @/examples/output/1-first-steps/03/tree.txt{console}

The module file `quad_rules.mod` is part of the library: a program using the library needs it to compile.

## Installing

`fobis install` copies what a mode built into a prefix, executables to `bin/`, libraries to `lib/`, module files to
`include/`:

<<< @/examples/output/1-first-steps/03/install.txt{console}

## Using the installed library

Another project, elsewhere, computes the area under a parabola with `simpson`. Its fobos points the compiler to the
installed module file (`include`) and the linker to the library (`lib_dir`, `ext_libs`):

::: code-group

<<< @/examples/tutorial/1-first-steps/03-library/consumer/fobos{ini} [fobos]

<<< @/examples/tutorial/1-first-steps/03-library/consumer/src/area.F90{fortran} [src/area.F90]

<<< @/examples/tutorial/1-first-steps/03-library/consumer/src/curves.F90{fortran} [src/curves.F90]

:::

<<< @/examples/output/1-first-steps/03/consumer.txt{console}

FoBiS does not find `quad_rules` among the project's sources, so it does not try to compile it: the module comes
from the include path. Simpson's rule is exact on a parabola, even with two intervals.

::: tip What you learned
`mklib = static | shared`, `track_build`, `fobis install --prefix`, and a project linking an installed library with
`include`, `lib_dir`, `ext_libs`. When the library is a FoBiS project you build yourself, the next chapters show
better ways: fetching it as a dependency (chapter 5).
:::

Next: [4. Tests](./04-tests).
