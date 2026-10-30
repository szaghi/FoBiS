---
title: 9. One fobos, many machines
---

# 9. One fobos, many machines

`quad` is built on a laptop and on a cluster. The two differ in a few values (here, the processor the code is tuned
for), and a project may be built with other compilers too. Copying the modes for each machine would double the fobos;
this chapter keeps one set of modes and moves what differs into values chosen at build time.

## Values chosen by machine: varsets

A varset is a named set of `$variables`. The machines get their own file, included by the fobos, which also lists an
optional file of the developer's own:

<<< @/examples/output/2-growing/09/include.txt{ini}

<<< @/examples/output/2-growing/09/machines.txt{console}

The `release` mode uses `$TUNE`, and adds a flag only when the compiler is gfortran:

<<< @/examples/output/2-growing/09/release.txt{ini}

`fobis introspect` shows the varsets and the flags they give:

<<< @/examples/output/2-growing/09/varsets.txt{console}

<<< @/examples/output/2-growing/09/laptop.txt{console}

`--varset cluster` selects the other one:

<<< @/examples/output/2-growing/09/cluster.txt{console}

`qualified_keys` reports what `cflags.gnu` and `cflags.intel` did: the first was appended because the mode's compiler
is gfortran, the second was not applied. A key qualified by a system (`cflags.linux`, `ext_libs.windows`) works the
same way.

## Build for the cluster

The first build compiles with the default varset, `laptop`. `cflags_heritage = True` (from the template) records the
flags, so building for the cluster compiles everything again:

<<< @/examples/output/2-growing/09/default.txt{console}

<<< @/examples/output/2-growing/09/build.txt{console}

A varset that does not exist stops the build and lists the defined ones:

<<< @/examples/output/2-growing/09/unknown.txt{console}

## A developer's own values

`?fobos.local` is optional: without the file nothing happens. A developer who wants other values writes it, and it
wins over `machines.fobos` because it comes later in `paths`. It is ignored by git, so it never reaches the
repository:

<<< @/examples/output/2-growing/09/local.txt{console}

<<< @/examples/output/2-growing/09/override.txt{console}

::: tip What you learned
`[varset:NAME]`, `[varsets] default`, `--varset`, keys qualified by a compiler (`cflags.gnu`), `[include] paths`
with an optional `?file`, `fobis introspect --varsets` and `--buildoptions`. Reference:
[varsets](/cookbook/build#choose-machine-paths-at-build-time-varsets),
[qualified keys](/cookbook/build#flags-that-differ-by-compiler-or-system),
[includes](/cookbook/build#split-a-fobos-into-files).
:::

Next: [several programs and a library for others](./10-targets).
