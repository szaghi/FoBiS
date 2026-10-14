---
title: 4. Tests
---

# 4. Tests

A test is a program that stops with an error when a check fails. `quad` gets two, in `test/`:

::: code-group

<<< @/examples/tutorial/1-first-steps/04-tests/files/test/test_exactness.F90{fortran} [test_exactness.F90]

<<< @/examples/tutorial/1-first-steps/04-tests/files/test/test_order.F90{fortran} [test_order.F90]

<<< @/examples/tutorial/1-first-steps/04-tests/files/test/polynomials.F90{fortran} [polynomials.F90]

:::

- `test_exactness` checks what the rules must get exactly right: the trapezoid rule integrates a line, Simpson's a
  cubic.
- `test_order` checks how fast the error falls: halving the intervals divides it by 4 (trapezoid, second order) and
  by 16 (Simpson, fourth order).
- `error stop` ends the program with a non-zero exit status: that is what makes a test fail.

The tests are built like any program, so the debug mode now lists `test/` among its sources:

<<< @/examples/tutorial/1-first-steps/04-tests/files/fobos{ini}

## Running the tests

Every program in `test/` (the default test directory; `test_dir` in a `[test]` section changes it) is a test:

<<< @/examples/output/1-first-steps/04/list.txt{console}

<<< @/examples/output/1-first-steps/04/test.txt{console}

`fobis test` builds each test with the default mode (here `debug`, with run-time checks: a test should run in the
build that catches the most), runs them, and exits with status 1 when any fails. `--filter 'test_ord*'` selects tests
by name, `--suite` by a `! fobis: suite=NAME` comment in the file.

## Doctests

A doctest is a check written in a procedure's documentation, next to the code it describes. `quad_rules` gets one per
rule: the code between the fences runs, and its output must be the value after `=>`:

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
the expected one. The snippet doubles as an example in the documentation the comments generate.

## Coverage

The `coverage` mode instruments the build (`coverage = True`); the tests run in it write the counts that `fobis
coverage` reads, through [gcovr](https://gcovr.com) (or lcov):

```bash
fobis test --mode coverage
```

<<< @/examples/output/1-first-steps/04/report.txt{console}

`--format html` (the default) writes a browsable report in `coverage/`, `--fail-under 90` fails a CI job below 90%
of the lines.

::: tip What you learned
Test programs and `fobis test`, doctests and `fobis doctests`, a coverage mode and `fobis coverage`. Reference:
[`test`](/reference/test), [`doctests`](/reference/doctests), [`coverage`](/reference/coverage).
:::

Next: [5. Dependencies](./05-dependencies).
