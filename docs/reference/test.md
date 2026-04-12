# `test` command

Discover, build, and run Fortran test programs with a single command.

```bash
fobis test [options] [-- EXTRA_ARGS...]
```

## Options

| Option | Default | Description |
|---|---|---|
| `--suite SUITE` | — | Run only tests tagged with the given suite name |
| `--filter GLOB` | — | Run only tests whose name matches the glob pattern |
| `--timeout SECONDS` | `60` | Per-test timeout in seconds |
| `--no-build` | `False` | Skip compilation; execute pre-built binaries directly |
| `--list` | `False` | Print discovered tests without running them |
| `--coverage` | `False` | Enable coverage instrumentation during the test build |

## fobos options

| Option | Description |
|---|---|
| `-f`, `--fobos` | Specify a fobos file with a different name or path |
| `--mode` | Select a fobos mode |

## Test discovery

`fobis test` scans the `test/` directory (configurable in fobos `[test]`) for
Fortran source files containing a `program` statement. Each such file is a test
target. The test name is the program name declared in the source.

```fortran
! fobis: suite=integration
program test_io
  implicit none
  ! ... test code ...
  ! exit 0 = pass, exit non-zero = fail
end program test_io
```

The `! fobis: suite=NAME` comment (anywhere in the first 20 lines) assigns the
test to a named suite for filtering.

## `[test]` fobos section

```ini
[test]
test_dir = tests        ; default: test
suite    = unit         ; default suite for all tests in this dir
timeout  = 120          ; global timeout (seconds)
compiler = gnu          ; compiler override for test builds
cflags   = -g -fcheck=all
```

## Output format

```
fobis test [gnu]

  Building test suite (3 targets)...

  PASS  test_grid       (0.12 s)
  PASS  test_solver     (1.43 s)
  FAIL  test_io         (0.08 s)
        exit code: 1
        stdout: ASSERTION FAILED: expected 42, got 0 (test_io.F90:37)

  Results: 2 passed, 1 failed, 0 skipped
  Total:   1.63 s
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | All tests passed |
| `1` | One or more tests failed, a build error occurred, or no `test/` directory found |

## Examples

```bash
# Discover and run all tests
fobis test

# Run only unit-suite tests
fobis test --suite unit

# Run only tests matching a glob
fobis test --filter "test_grid*"

# List discovered tests without running
fobis test --list

# Run with a per-test timeout of 30 s
fobis test --timeout 30

# Run with coverage instrumentation
fobis test --coverage

# Pass extra args to every test binary
fobis test -- --verbose
```

::: tip Framework integration
`fobis test` is compatible with any test framework that uses process exit codes to
signal pass/fail (pFUnit, test-drive, FRUIT, etc.). No adaptor needed — just
`error stop` or `call exit(1)` on failure.
:::
