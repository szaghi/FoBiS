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
| `--explain` | `False` | Explain each failed test (see [Explaining failures](/ai/explain#runtime-failures)); the model is asked for the first one only |
| `--explain-context` | `False` | Like `--explain`, but print what the model would receive instead of running it |
| `--runner local\|slurm` | `local` | Run the test programs locally or as Slurm jobs (see [Running on a cluster](/advanced/scheduler)) |
| `--launcher CMD` | mode key `launcher`, else `[test] launcher` | Start every test program through `CMD`: `mpirun -np {ranks}`, `valgrind --error-exitcode=1` (see [launchers](/reference/run#launchers)) |
| `--jobs N`, `-j N` | `[test] jobs`, else `1` | Run up to `N` test programs at once (see [parallel tests](#parallel-tests)) |
| `--ranks N` | `1` | MPI ranks: replace `{ranks}` in the launcher; without a launcher, `mpirun -np {ranks}` (under `--runner slurm`: the `[scheduler]` launcher, `srun`, and `--ntasks=N` for the job) |
| `--quiet`, `-q` | `False` | Build the tests without printing the builder's settings for each |
| `--json` | `False` | Build and run silently, then one JSON object: each result with its status and, for a failure, the facts of `--explain` (see [JSON output](/advanced/json-output#fobis-test-json)) |

## fobos options

| Option | Description |
|---|---|
| `-f`, `--fobos` | Specify a fobos file with a different name or path |
| `--mode` | Select a fobos mode |
| `--shadow NAME` | Rebuild the mode as a [shadow](/advanced/matrix#shadow-modes): `checks`, `sanitize`, `strict` (or `none`), in `.fobis/shadow/<mode>-<shadow>/` |

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
; default: test
test_dir = tests
; default suite for all tests in this dir
suite    = unit
; global timeout (seconds)
timeout  = 120
; every test through MPI (a mode's own launcher wins)
launcher = mpirun -np {ranks}
; test programs running at once (--jobs overrides it)
jobs     = 4
```

## Parallel tests

`fobis test -j N` builds the selected tests first, one after the other (the builds share the mode's object and
module directories), then runs up to `N` programs at once. The results are listed in discovery order, as in a
serial run, with the same statuses; the summary adds the elapsed time, and `--json` adds `jobs` and `elapsed`
(seconds). Each test keeps its own timeout.

- A test started with `--ranks R` takes `R` of the `N` slots: `-j 8 --ranks 4` runs two MPI tests at a time.
- Under `--runner slurm`, `N` is the number of jobs in the queue at once.
- The tests run in the current directory, as in a serial run: tests that write the same file must not run in
  parallel (give the files distinct names, or keep `-j 1`).

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

# Four test programs at a time
fobis test -j 4

# MPI tests on 4 ranks; every test under valgrind
fobis test --launcher "mpirun -np {ranks}" --ranks 4
fobis test --launcher "valgrind --error-exitcode=1"
```

::: tip Framework integration
`fobis test` is compatible with any test framework that uses process exit codes to
signal pass/fail (pFUnit, test-drive, FRUIT, etc.). No adaptor needed — just
`error stop` or `call exit(1)` on failure.
:::

<!-- cli:begin -->
<!-- generated by docs/scripts/gen_cli_reference.py from the command line: do not edit -->

## All options

| Option | Value | Default | Description |
|---|---|---|---|
| `--fobos`, `-f` | TEXT |  | Specify a "fobos" file named differently from "fobos" |
| `--fci` |  |  | Assume fobos inputs as case insensitive |
| `--mode` | TEXT |  | Select a mode defined into a fobos file |
| `--shadow` | TEXT |  | Rebuild the mode as a shadow (checks, sanitize or strict): the mode's settings with checking flags, in its own build directory (.fobis/shadow/&lt;mode&gt;-&lt;shadow&gt;/). |
| `--compiler` | TEXT | `gnu` | Compiler used (case insensitive, default gnu) |
| `--suite` | TEXT |  | Run only tests tagged with this suite name |
| `--filter` | TEXT |  | Run only tests whose name matches this glob pattern |
| `--timeout` | FLOAT |  | Per-test timeout in seconds [default: fobos [test] timeout, else 60] |
| `--no-build` |  |  | Skip (re-)compilation; run existing test binaries |
| `--list` |  |  | List discovered tests without running them |
| `--coverage` |  |  | Generate coverage report after running tests |
| `--explain` |  |  | When the program fails, explain why: from facts (location, declarations, debug mode to use, known compiler bugs), then with the LLM (cited cause and fix) when the location can be trusted. |
| `--explain-context` |  |  | Like --explain, but print what the model would receive instead. |
| `--runner` | TEXT | `local` | Where the programs run: local, or slurm (jobs submitted with sbatch; [scheduler] settings). |
| `--launcher` | TEXT |  | Start the program through this command: an MPI launcher, a debugger, a checker ('mpirun -np {ranks}', 'gdb --args', 'valgrind'); {ranks} is replaced by --ranks [default: mode key launcher] |
| `--ranks` | INTEGER |  | Number of MPI ranks: replaces {ranks} in the launcher (without a launcher: mpirun -np {ranks}) |
| `--jobs`, `-j` | INTEGER |  | Test programs running at the same time (built first, one after the other); a test with --ranks takes as many [default: fobos [test] jobs, else 1] |
| `--quiet`, `-q` |  |  | Less verbose output |
| `--json` |  |  | Emit structured JSON to stdout instead of human-readable output (useful for scripting / agents) |

<!-- cli:end -->
