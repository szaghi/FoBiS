---
title: Testing
---

# Testing

A test is a Fortran program that ends with a non-zero exit status when a check fails: `error stop`, `stop 1`, or
`call exit(1)`. `fobis test` finds the programs, builds each one with a mode of your fobos, runs them and reports.
Any framework that signals failure through the exit status works unchanged: pFUnit, test-drive, FRUIT.

How it works:

1. **Discovery.** Every file in the test directory (`test/` by default) holding a `program` statement is a test, named
   after its program. When two files declare the same program name, the tests are named after their files.
2. **Build.** Each test is built as the target of the selected mode (the default mode when none is given), so the
   tests use your modules as the programs do. The test directory must be among the mode's sources (`src`); a test
   outside them is not built, and fails.
3. **Run.** The binaries go to `<build_dir>/test/<name>`, are run from the current directory, and the report lists
   them in discovery order. The exit status of `fobis test` is 1 when any test fails, times out or does not build.

Tutorial: [tests, doctests, coverage](/tutorial/first-steps/04-tests). Reference: [`test`](/reference/test),
[`doctests`](/reference/doctests), [`coverage`](/reference/coverage).

## Write and run tests

Put the programs in `test/` and add the directory to the sources of the mode the tests build in. A debug mode with
runtime checks is the right one: a test should run in the build that catches the most.

<<< @/examples/tutorial/1-first-steps/04-tests/files/fobos{ini}

<<< @/examples/output/1-first-steps/04/list.txt{console}

<<< @/examples/output/5-numerics/05/test.txt{console}

```bash
fobis test                          # every test, in the default mode
fobis test --mode release           # the tests built in another mode
fobis test --filter "test_ord*"     # by name (a glob)
fobis test --no-build               # run the binaries a previous fobis test built
fobis test -- --verbose             # arguments after -- are passed to every test program
```

`--quiet` prints nothing of a build that succeeds; a test whose build fails shows all of it, compiler errors included.

## Suites and timeouts

Tag a test with a comment in its first 20 lines, then select a suite:

```fortran
! fobis: suite=slow
program test_convergence
```

```bash
fobis test --suite slow             # only the tests tagged slow (untagged ones are left out)
fobis test --timeout 600            # seconds per test; a test still running is killed and fails
```

The `[test]` section holds the defaults, and the command line overrides them:

```ini
[test]
; the directory holding the test programs
test_dir = test
; the suite run when --suite is not given
suite    = fast
; seconds per test (default 60)
timeout  = 120
; test programs running at once
jobs     = 4
```

## Run the tests in parallel

```bash
fobis test -j 8
```

The tests are built first, one after the other (they share the mode's object and module directories), then run up to
eight at a time, and reported in the usual order with the elapsed time. Each keeps its own timeout. The tests run in
the current directory as in a serial run: tests writing the same file need distinct file names, or `-j 1`.

## MPI tests, valgrind, a debugger

A launcher starts every test program:

```bash
fobis test --ranks 4                                       # mpirun -np 4 ./test
fobis test --launcher "mpirun -np {ranks}" --ranks 4       # the same, spelled out
fobis test --launcher "valgrind --error-exitcode=1"        # every test under valgrind
fobis test -j 8 --launcher "mpirun -np {ranks}" --ranks 4  # two MPI tests at a time: each takes 4 of the 8 slots
```

`{ranks}` is replaced by `--ranks` (1 when not given). The launcher comes from `--launcher`, else the mode's
`launcher` key, else `[test] launcher`. A launcher that is not on the PATH stops `fobis test` before it builds
anything (exit 2). On a cluster, `--runner slurm` submits the tests as jobs: see [HPC and clusters](./hpc).

## Test-only dependencies

A testing framework the library itself does not need is a test-only dependency: it is fetched, and built only for
`fobis test`, `fobis doctests` and `fobis check`.

```ini
[dependencies]
test-drive = https://github.com/fortran-lang/test-drive :: tag=v0.6.1 :: dev
```

A plain `fobis build` whose sources include test programs using it fails: give the build a target, or keep the
tests out of the release mode's sources. More in [Dependencies](./dependencies).

## Doctests: checks in the documentation

A check written in a procedure's documentation, next to the code it describes. The code between the fences runs, and
its output must equal the text between `=>` and `<<<`:

```fortran
pure function trapezoid(f, a, b, n) result(s)
!< Composite trapezoidal rule with n intervals.
!<```fortran
!< use integrands, only : sine
!< print '(F8.5)', trapezoid(sine, 0._R8P, acos(-1._R8P), 64)
!<```
!=> 1.99960 <<<
```

<<< @/examples/output/1-first-steps/04/doctests.txt{console}

FoBiS writes each snippet into a small program that uses the module, builds it, runs it and compares its output with
the expected text; `fobis doctests` exits 1 when any fails, printing what was obtained and what was expected.

- **The comment character is yours.** Use the one your documentation tool reads (`!<` for FORD), and the snippet
  doubles as an example in the generated documentation.
- **Anything Fortran goes in a snippet:** declarations, `use` statements, a derived type. A procedure may carry
  several doctests, and a module may carry some in its own header.
- **Print with an explicit format.** The output is compared as text (surrounding blanks stripped): list-directed
  `print *` changes with the compiler.
- **Public procedures only:** the snippet is a program that uses the module.
- **Standard output only** is compared.

The doctests build with a mode too, and mode keys control them:

```ini
[doctests]
compiler               = gnu
cflags                 = -c
build_dir              = ./build/doctests/
; keep the generated programs, to look at them
keep_volatile_doctests = True
; cpp or fpp, for the sources' #if lines
doctests_preprocessor  = cpp
; files whose doctests are not run
exclude_from_doctests  = src/slow_module.F90
```

```bash
fobis doctests --mode doctests
```

With `keep_volatile_doctests`, the programs stay in `<build_dir>/doctests-src/<file>/<module>-doctest-N.f90`, with
their expected output in `.result` files next to them.

## Coverage

An instrumented mode, the tests run in it, then the report:

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
fobis coverage --mode coverage --format text --exclude "test/.*"
```

<<< @/examples/output/1-first-steps/04/report.txt{console}

- **The report needs [gcovr](https://gcovr.com)** (`pip install gcovr`), or lcov + genhtml. With lcov, only an HTML
  report is written, and `--exclude` and `--fail-under` are not applied: FoBiS warns when they are given.
- **`--exclude` is a regular expression** matched by gcovr against the file path: `"test/.*"`, not `test/*`.
- **Formats:** `--format html` (the default, `coverage/index.html`), `xml` (Cobertura, for Codecov), `text`, or `all`
  (the three); repeat `--format` for several.
- **A CI threshold:** `--fail-under 80` exits 1 below 80% of the lines.
- **gcovr 7.2 with gcov 13** reports Fortran module procedures; gcovr 8.6 reports 0 lines for them.

A `[coverage]` section sets the report's defaults (`format`, `output_dir`, `exclude`, `fail_under`). It is the same
section as a mode named `coverage`: both kinds of key can live in it.

```ini
[coverage]
fail_under = 80
exclude    = test/.*
```

In CI, the threshold and an upload:

```yaml
- run: fobis test --mode coverage
- run: fobis coverage --mode coverage --format xml --fail-under 80
- uses: codecov/codecov-action@v4
  with:
    files: coverage/coverage.xml
```

## Defects only a checked build sees

A test can pass in an optimised build and be wrong: here a division by zero gives NaN, and `NaN > tolerance` is
false. Rebuild the mode with runtime checks and floating-point traps, without writing a second mode:

<<< @/examples/output/5-numerics/03/checks.txt{console}

```bash
fobis test --mode fast --shadow checks       # runtime checks and traps
fobis test --mode fast --shadow sanitize     # AddressSanitizer and UndefinedBehaviorSanitizer
```

The shadow builds in `.fobis/shadow/<mode>-<shadow>/` and leaves the mode's own build alone. Every mode against
every shadow, at once: `fobis matrix`, in [Verifying results](./verification). Tutorial:
[defects some builds see](/tutorial/numerics/03-shadows).

## Why a test failed

```bash
fobis test --explain
```

For every failed test: the kind of failure (bounds, unallocated pointer, floating-point exception, `error stop`,
timeout), the statement and the declarations involved, and the caller when the build has debug information. The
model is asked only for the first failure the facts leave unexplained. An optimised build's backtrace is not trusted:
FoBiS names a debug mode to rerun in. Tutorial: [crashes, located](/tutorial/ai/03-crash); more in
[AI assistance](./ai).

## For CI and agents

```bash
fobis test --json
```

One JSON document on standard output: each test with its status (`passed`, `failed`, `build-failed`, `timeout`,
`error`), its output, and for a failure the facts `--explain` would print. Building and running are silent. More in
[Continuous integration](./ci).
