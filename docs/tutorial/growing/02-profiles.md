---
title: 2. Build profiles and features
---

# 2. Build profiles and features

Two more ways to stop writing flags by hand:

- a **build profile** is a named set of flags FoBiS knows for each compiler (`debug`, `release`, `asan`,
  `coverage`): the same mode works with gfortran, ifx or nvfortran;
- a **feature** is a named, optional piece of configuration (here a preprocessor define) that a mode or the command line
  switches on.

<<< @/examples/output/2-growing/02/profiles.txt{console}

`quad`'s Simpson rule needs an even number of intervals. With an odd one it returns a wrong value without a word;
a check costs a test per call, so it becomes a feature, `checks`, compiled in only when asked:

```fortran
#ifdef QUAD_CHECKS
   if (mod(n, 2) /= 0) error stop 'simpson: the number of intervals must be even'
#endif
```

(The `.F90` extension tells the compiler to run the preprocessor.) The fobos declares the feature, gives the debug
mode the `debug` profile and the feature, the release mode the `release` profile:

<<< @/examples/tutorial/2-growing/02-profiles/files/fobos{ini}

- `build_profile` prepends the profile's flags to the mode's `cflags`; the mode's own flags come after and win.
- `features = checks` activates the feature in the mode; `--features` on the command line adds or removes features.
- `cflags_heritage = True` records the flags used in the build directory: when they change, everything is recompiled.
  Without it FoBiS compares only file times, and objects compiled with the old flags would stay.

A program that calls Simpson's rule with 3 intervals, in `test/`:

<<< @/examples/tutorial/2-growing/02-profiles/files/test/odd_intervals.F90{fortran}

<<< @/examples/output/2-growing/02/debug.txt{console}

The flags are the profile's, then `-c`, then the feature's define. The check stops the program:

<<< @/examples/output/2-growing/02/debug-run.txt{console}

The same build without the feature (`--features -checks` removes it): the flags changed, so everything is recompiled,
and the program prints a wrong integral without complaint:

<<< @/examples/output/2-growing/02/unchecked.txt{console}

The release mode cannot build that program at all: its sources are `src/` only.

<<< @/examples/output/2-growing/02/release.txt{console}

(The program is removed after this chapter: a test that is meant to fail does not belong in `test/`.)

::: tip What you learned
`build_profile`, `--list-profiles`, `[features]` and `--features` (`-name` to remove one), `cflags_heritage`.
Reference: [build profiles](/advanced/build-profiles), [feature flags](/advanced/features).
:::

Next: [3. OpenMP and MPI](./03-parallel).
