---
title: 4. A project that depends on quad
---

# 4. A project that depends on quad

In [chapter 3 of First steps](../first-steps/03-library) a separate project used `quad` once installed. While both are
being developed, installing after every change is a chore; `dependon` builds the library first, every time, and wires
its module files and its archive in:

::: code-group

<<< @/examples/tutorial/2-growing/04-dependon/area/fobos{ini} [area/fobos]

<<< @/examples/tutorial/2-growing/04-dependon/area/src/area.F90{fortran} [area/src/area.F90]

<<< @/examples/tutorial/2-growing/04-dependon/area/src/curves.F90{fortran} [area/src/curves.F90]

:::

`dependon = ../quad/fobos:static((direct))` reads: the fobos at that path (relative to this one), its `static`
mode, and link the library by its full path (`((indirect))` links it by name, with `-L` and `-l`).

<<< @/examples/output/2-growing/04/build.txt{console}

FoBiS built `quad`'s static library in its own directory, then added its module directory to the include path and
the archive to the libraries. When nothing changed, the library build is a no-op:

<<< @/examples/output/2-growing/04/uptodate.txt{console}

## When the library changes

A change to the body of a procedure recompiles the library and relinks `area`; `area`'s own files need not compile
again:

<<< @/examples/output/2-growing/04/touch.txt{console}

A change to the library's **interface** is different: `area`'s objects were compiled against the old one. Here a
new rule, `midpoint`, is added to `quad_rules`:

```fortran
public :: R8P, integrand, midpoint, trapezoid, simpson
```

<<< @/examples/output/2-growing/04/interface.txt{console}

gfortran rewrites a module file only when the module's interface changes, so FoBiS compares the time of the
`.mod` files of the modules a file uses from outside the project with the file's object: `curves` and `area` were
recompiled.

::: tip What you learned
`dependon = PATH:MODE((direct|indirect))`: another project's library rebuilt first, its module files and archive
wired in, its interface changes followed. For dependencies from GitHub, [`[dependencies]`](../first-steps/05-dependencies)
does the same from a clone. Reference: [interdependent projects](/advanced/interdependent).
:::

Next: [5. Rules](./05-rules).
