---
title: Testing
---

# Testing

## Test programs

Every program in `test/` is a test: it passes when it exits with 0. Stop a failing check with `error stop` (or any
non-zero exit). The test directory may be one of the mode's sources, so the tests can use your modules.

```bash
fobis test --list
fobis test --quiet
fobis test --filter "test_order*"
```

Tutorial: [tests](/tutorial/first-steps/04-tests). Guide: [testing](/advanced/testing).

## Fast and slow tests

Tag a test in its first 20 lines, and pick a suite:

```fortran
! fobis: suite=slow
program test_convergence
```

```ini
[test]
; the default selection; --suite overrides it
suite   = fast
; seconds per test; --timeout overrides it
timeout = 120
```

```bash
fobis test --suite slow
```

## Run the tests in parallel

```ini
[test]
; test programs at a time; --jobs/-j overrides it
jobs = 4
```

```bash
fobis test -j 8                                            # eight at a time
fobis test -j 8 --launcher "mpirun -np {ranks}" --ranks 4  # two MPI tests at a time
```

Built one after the other, run in parallel, reported in the usual order. Tests writing the same file need distinct
names or `-j 1`. Reference: [parallel tests](/reference/test#parallel-tests).

## Examples in the documentation that run

A `!<` comment block with a Fortran example and its expected output is a doctest:

```fortran
pure function trapezoid(f, a, b, n) result(s)
!< Composite trapezoidal rule with n intervals.
!<```fortran
!< use integrands, only : sine
!< print '(F8.5)', trapezoid(sine, 0._R8P, acos(-1._R8P), 64)
!<```
!=> 1.99960 <<<
```

```bash
fobis doctests
```

Guide: [doctests](/advanced/doctests).

## Coverage

```ini
[coverage]
compiler  = gnu
cflags    = -c -O0 -g
coverage  = True
src       = ./src/ ./test/
build_dir = ./build/coverage/
```

```bash
fobis test --mode coverage
fobis coverage --mode coverage --format html --exclude "test/.*"
```

Reference: [fobis coverage](/reference/coverage).

## Defects only a checked build sees

Run the tests of an optimised mode rebuilt with runtime checks and floating-point traps, without a second mode:

```bash
fobis test --mode release --shadow checks
fobis matrix --modes release --shadows none,checks,sanitize
```

Tutorial: [defects only some builds see](/tutorial/numerics/03-shadows).

## Why a test failed

```bash
fobis test --explain
```

The location of the crash, the statement, the declarations involved, and a model's cited explanation when the
facts leave something to explain. Tutorial: [crashes, located](/tutorial/ai/03-crash).
