---
title: 6. Packages built with fpm and CMake
---

# 6. Packages built with fpm and CMake

Not every library of the lab is a FoBiS project. `strings` is built with fpm (an `fpm.toml`, no fobos), `cmath` with
CMake. Both can be listed, found and added like the others, and `solver` uses all of them: each package is built by
its own build system, with the compiler of `solver`.

## List them

`fobis publish --index`, run in a package's working copy, adds its entry to an index:

<<< @/examples/output/7-packages/06/publish-strings.txt{console}

<<< @/examples/output/7-packages/06/publish-cmath.txt{console}

FoBiS reads no manifest of a CMake project, so the lab gives `cmath` a recipe, kept next to the index:

<<< @/examples/tutorial/7-packages/06-builds/recipes/cmath.toml{toml}

<<< @/examples/output/7-packages/06/entries.txt{console}

`builds` tells what each one needs: `fobis search --build fpm` lists the packages an fpm project can use (the next
chapter).

## Use them

`add` copies the index's recipe into the project, so that building never depends on the index:

<<< @/examples/output/7-packages/06/add.txt{console}

<<< @/examples/output/7-packages/06/dependencies.txt{ini}

`fetch` builds `strings` with fpm and `cmath` with CMake, each with the compiler of `solver`'s default mode, and
installs them into `.fobis_deps/.prefix`:

<<< @/examples/output/7-packages/06/fetch.txt{console}

<<< @/examples/output/7-packages/06/prefix.txt{console}

`build` compiles `solver` and its FoBiS packages, and links the libraries fpm and CMake made:

<<< @/examples/tutorial/7-packages/06-builds/files/src/solver.f90{fortran}

<<< @/examples/output/7-packages/06/run.txt{console}

- **fpm is required** for a package that has an `fpm.toml` and no fobos: FoBiS never compiles an fpm package itself.
  fpm fetches the package's own fpm dependencies.
- **CMake installs no module file** by default: FoBiS collects the ones the build made.
- **Only the compiler reaches them**, not the mode's other flags: a flag that changes the binary interface
  (`-fdefault-real-8`) does not reach a package built by fpm or CMake.

*This chapter needs fpm and CMake; its outputs are recorded where both are installed.*

::: tip What you learned
`fobis publish --index`, recipes in an index, packages built by fpm and CMake in a FoBiS project, the
`.fobis_deps/.prefix` they are installed into. Reference:
[how a dependency is built](/cookbook/packages#how-a-dependency-is-built),
[CMake, make and other packages](/cookbook/packages#cmake-make-and-other-packages).
:::
