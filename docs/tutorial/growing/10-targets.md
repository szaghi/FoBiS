---
title: 10. Several programs and a library for others
---

# 10. Several programs and a library for others

So far each mode built one program. This chapter builds all of `quad`'s programs in one call, each with its own
flags, describes its library so that any build system can link it, and gives editors the exact commands that compile
each file.

## Several programs, one build

`[target.NAME]` sections name the programs of a build; a key in a section replaces the mode's. They live in a fobos
of their own, `programs.fobos`, because a fobos with target sections cannot have modes that name a `target`, and
every mode of `quad`'s fobos does:

<<< @/examples/output/2-growing/10/programs.txt{console}

<<< @/examples/output/2-growing/10/build.txt{console}

`sweep` alone was built with OpenMP:

<<< @/examples/output/2-growing/10/sweep.txt{console}

`--target-filter` builds some of the targets only. The targets share the mode's objects, so nothing is compiled
again:

<<< @/examples/output/2-growing/10/filter.txt{console}

## A library any build system can link

`pkgconfig = True` in a library mode writes a pkg-config file next to the library. Its version is the `[project]`
version:

<<< @/examples/output/2-growing/10/static.txt{ini}

<<< @/examples/output/2-growing/10/library.txt{console}

A program outside the project, built by hand with gfortran, finds the module files and the library through it:

<<< @/examples/tutorial/2-growing/10-targets/consumer/use_quad.f90{fortran}

<<< @/examples/output/2-growing/10/consumer.txt{console}

The same file serves CMake (`pkg_check_modules`) and make (`pkg-config --cflags --libs quad`). `fobis install`
writes one into the prefix it installs to, with the installed paths.

## The compile commands, for editors

Language servers (fortls, clangd for the C files) need each file's compile command. `--compile-commands` writes them
into the build directory and links `compile_commands.json` at the project root:

<<< @/examples/output/2-growing/10/database.txt{console}

<<< @/examples/output/2-growing/10/entries.txt{console}

The database has an entry for every file of the mode's sources, compiled or not (the fetched PENF's too), with the
mode's flags and macros. Build in another mode to point the editor at that mode's flags.

::: tip What you learned
`[target.NAME]` sections, `--target-filter`, `-f`, `pkgconfig = True`, linking through pkg-config,
`--compile-commands`. Reference: [one program out of many](/cookbook/build#build-one-program-out-of-many),
[pkg-config files](/cookbook/libraries#publish-a-pkg-config-file),
[compile commands](/cookbook/libraries#give-editors-the-compile-commands).
:::

This is the end of the second track. The [third](../ecosystem/01-register) leaves `quad` for a while: a family of
projects that depend on each other, managed together.
