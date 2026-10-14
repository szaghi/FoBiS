# Test Runner

FoBiS includes a lightweight test runner that discovers, compiles, and runs
Fortran test programs — no external test harness required.

## Quick start

```bash
# Discover, build, and run all tests
fobis test

# Run only tests tagged with a specific suite name
fobis test --suite physics

# Run only tests whose names match a glob pattern
fobis test --filter "test_*_rk8"

# List the tests found, without building or running them
fobis test --list
```

## How discovery works

`fobis test` scans the source tree for files that contain a `program` statement
(i.e. Fortran main programs). Every such file is treated as a test program and
compiled independently.

To assign a test to a named suite, add a special comment in the source file:

```fortran
! fobis: suite=physics
program test_gravity
  implicit none
  ! ...
end program
```

Tests without a `! fobis: suite=` tag belong to the implicit `default` suite and
are always included unless `--suite` filters them out.

## Options

| Option | Default | Description |
|---|---|---|
| `--suite NAME` | `[test] suite`, else all | Run only tests tagged `! fobis: suite=NAME` |
| `--filter GLOB` | (all) | Run only tests whose name matches this glob |
| `--timeout N` | `[test] timeout`, else `60` | Seconds before a single test is considered failed |
| `--no-build` | `False` | Run the test binaries already built |
| `--list` | `False` | List the tests found, without building or running them |
| `--quiet` | `False` | Build without printing the builder's settings for each test |
| `--launcher CMD` | mode key `launcher`, else `[test] launcher` | Start every test through `CMD` (`mpirun -np {ranks}`, `valgrind ...`) |
| `--ranks N` | `1` | Replace `{ranks}` in the launcher; alone, `mpirun -np N` |

## `[test]` fobos section

Set defaults in the fobos file so you never have to type them:

```ini
[test]
test_dir = test
suite    = unit
timeout  = 120
launcher = mpirun -np {ranks}
```

## MPI tests, debuggers and checkers

A launcher starts every test program: `fobis test --launcher "mpirun -np {ranks}" --ranks 4` runs each test on 4
MPI ranks, `fobis test --launcher "valgrind --error-exitcode=1"` under valgrind. The order of precedence is
`--launcher`, then the mode's `launcher` key, then `[test] launcher`. See [launchers](/reference/run#launchers).

## Output format

```
Running 5 test(s)...
  PASS  test_vector_norm       (0.12 s)
  PASS  test_matrix_mult       (0.34 s)
  FAIL  test_solver_converge   (exit 1)
  PASS  test_io_roundtrip      (0.08 s)
  SKIP  test_mpi_reduce        (binary not found)

Results: 3 passed, 1 failed, 1 skipped
```

The runner exits with code `0` if all executed tests passed, `1` otherwise.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | All tests passed |
| `1` | One or more tests failed or timed out |

## Typical CI workflow

```yaml
- name: Build and test
  run: |
    fobis build --build-profile debug
    fobis test --timeout 120
```

Or with coverage:

```yaml
- run: fobis build --build-profile coverage
- run: fobis test
- run: fobis coverage --format xml --fail-under 75
```

See [Coverage](/reference/coverage) for the full coverage reporting workflow.
