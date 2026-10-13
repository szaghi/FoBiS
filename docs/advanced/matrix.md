# Shadow modes and the matrix

A release build tells you little about whether the code is right: optimised, without runtime checks, it lets an
index run past the end of an array, reads an uninitialised variable as whatever was in memory, and reorders a sum.
FoBiS rebuilds any mode as a **shadow** that checks, in its own build directory, and runs every mode in every
shadow — with every compiler on the machine — as a **matrix**.

```bash
fobis build --shadow checks          # the mode with runtime checks, -O0 -g, floating-point traps
fobis test --shadow checks           # its tests, built that way
fobis verify --shadow checks         # its cases, against the references
fobis matrix                         # every mode x {none, checks}: build, test
fobis matrix --shadows none,checks,sanitize,strict --verify --recheck
```

## Shadow modes

A shadow keeps everything of the mode — sources, include paths, libraries, preprocessor flags, MPI and OpenMP
settings — and changes only the compiler flags: it removes the mode's flags that would defeat it (optimisation,
fast math, link-time optimisation, conflicting checks or standards) and adds its own. Its objects and programs go
to `.fobis/shadow/<mode>-<shadow>/`; the mode's own build directory is never touched.

| Shadow | gfortran | ifx / ifort | nvfortran |
|--------|----------|-------------|-----------|
| `checks` | `-O0 -g -fcheck=all -ffpe-trap=invalid,zero,overflow -finit-real=snan -finit-integer=-9999 -finit-derived -fbacktrace` | `-O0 -g -check all -fpe0 -init=snan,arrays -traceback` | `-O0 -g -Mbounds -Mchkptr -Ktrap=fp -Minit-real=snan -traceback` |
| `sanitize` | `-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined` | ifx: `-O1 -g -fsanitize=address`; ifort: not available | not available |
| `strict` | `-std=f2018 -pedantic -Werror` | `-stand f18 -warn stderrors -warn errors` | `-Mstandard -Werror` |
| `none` | the mode's own flags, in its own directory | | |

What each one catches was measured, not assumed: small programs holding one defect each (an index out of bounds,
an uninitialised real, a division by zero, a heap overflow through an assumed-size dummy, a `real*8` declaration),
built with gfortran 16, ifx 2025.3, ifort 2024.2 and nvfortran 26.1:

| | gfortran | ifx | nvfortran |
|-|----------|-----|-----------|
| `checks` | bounds (located), uninitialised real and division by zero (SIGFPE) | bounds, uninitialised real (located), division by zero | bounds (located), division by zero; an uninitialised real becomes a quiet NaN (`-Minit-real=snan` writes `7FC00000`), not a trap |
| `sanitize` | stack and heap overflows, also through an assumed-size dummy | stack and global overflows; the assumed-size heap overflow is missed | — |
| `strict` | `real*8` rejected | `real*8` rejected | `real*8` rejected |

Two compilers lack a shadow, and FoBiS says so instead of building something that checks nothing: nvfortran has
no sanitizer (`Unknown switch: -fsanitize=address`), and ifort *accepts* `-fsanitize=address` with a warning
and ignores it (`warning #10006: ignoring unknown option`): a sanitize build with ifort would pass every test
without checking anything. AddressSanitizer also misses an overflow that stays inside one object (writing past
`a(4)` into the next component of the same derived type): `checks` finds it.

`--shadow` works with `build`, `run`, `test`, `case run`, `verify` and `introspect`. When a program crashes in an
optimised build, `run --explain` and `test --explain` advise rebuilding the mode with `--shadow checks`; a
[case](/advanced/cases)'s provenance records the shadow it was built with.

## The matrix

`fobis matrix` takes the modes of the fobos (`--modes` to choose) and the shadows (`--shadows`, default
`none,checks`) and, for each cell:

1. builds the mode as the shadow, **from scratch** (a compiler swapped by `module load` under the same command name
   would otherwise leave the old compiler's objects), in the shadow's directory;
2. runs the tests (`fobis test`, when the project has test programs);
3. with `--verify`, runs the [cases](/advanced/cases): each against its [reference](/advanced/verify), and every
   quantity across cells.

A mode whose compiler is not found is **skipped**, a shadow its compiler lacks is **n/a**: the matrix runs what this
machine has, and says what it could not run. With `--recheck`, a test or case that fails in a cell is run again
under `checks` (once per mode), whose runtime checks often turn a crash or a wrong number into a located message.

### One matrix, several compilers

Compilers often live in environment modules. Tell FoBiS how to get each one: the commands run in bash before the
mode's cells, and the environment they leave is the cells' environment.

```ini
[verification]
setup =
    gnu15-release: source /usr/share/lmod/lmod/init/bash; export MODULEPATH=$HOME/.modules; module load gcc/15.2.0
    nvfortran: source /usr/share/lmod/lmod/init/bash; export MODULEPATH=$HOME/.modules; module load nvhpc/26
    intel_nextgen: source /opt/intel/oneapi/compiler/2025.3/env/vars.sh
```

A line is looked up by mode name, then compiler name, then compiler family (`gnu`, `intel`, `nvfortran`). Every
cell records the first line of its compiler's `--version` in that environment, so the matrix shows what really
compiled it: below, the `gnu15-release` cells report `GNU Fortran (GCC) 15.2.0`, the others the system gfortran 16.

### A real matrix

A small project with five release modes (the system gfortran 16; gfortran 15.2 and nvfortran 26.1 from Lmod; ifx
2025.3; nagfor, not installed), two tests and one case computing a series sum. One test writes one element past an
array that is followed, in the same derived type, by a guard value, then checks the guard; the other reads an
uninitialised variable. `fobis matrix --shadows none,checks,sanitize,strict --verify --recheck` (real output,
abridged):

```text
mode           none      checks    sanitize  strict
gnu-release    FAIL      FAIL      FAIL      FAIL
gnu15-release  FAIL      FAIL      FAIL      FAIL
nvf-release    ok        FAIL      n/a       ok
ifx-release    FAIL      FAIL      FAIL      FAIL
nag-release    skipped   skipped   skipped   skipped

Failures:
gnu-release/none (GNU Fortran (Ubuntu 16-20260315-1ubuntu1~24~ppa1) 16.0.1 20260315 (experimental) [trunk r16-8100-g3aca3bae8ee]):
  test test_overrun: the program stopped itself: error stop at test/test_overrun.f90:10
  recheck of test test_overrun with --shadow checks: failed: index 5 of array x is above its upper bound 4 at test/test_overrun.f90:18
gnu-release/checks (GNU Fortran (Ubuntu 16-20260315-1ubuntu1~24~ppa1) 16.0.1 20260315 (experimental) [trunk r16-8100-g3aca3bae8ee]):
  test test_overrun: index 5 of array x is above its upper bound 4 at test/test_overrun.f90:18
  test test_uninit: floating-point exception at test/test_uninit.f90:9
gnu-release/sanitize (GNU Fortran (Ubuntu 16-20260315-1ubuntu1~24~ppa1) 16.0.1 20260315 (experimental) [trunk r16-8100-g3aca3bae8ee]):
  test test_overrun: the program stopped itself: error stop at test/test_overrun.f90:10
  recheck of test test_overrun with --shadow checks: failed: index 5 of array x is above its upper bound 4 at test/test_overrun.f90:18
...
nvf-release/checks (nvfortran 26.1-0 64-bit target on x86-64 Linux -tp alderlake):
  test test_overrun: index 5 of array x is above its upper bound 4 at test/test_overrun.f90:18
...

Not run:
  nvf-release/sanitize: shadow sanitize is not available: nvfortran has no sanitizer (nvfortran 26.1: 'Unknown switch: -fsanitize=address')
  nag-release: compiler nagfor not found (a [verification] setup line can load it)

Disagreements between cells (beyond the case's tolerance):
  series.zeta2: gnu-release/checks vs gnu-release/none: fail at exact (max abs 3.66e-14, max rel 2.23e-14, worst at [0]: 1.6449335668483875 vs 1.6449335668484242)
  series.zeta2: nvf-release/none vs gnu-release/none: fail at exact (max abs 3.97e-14, max rel 2.42e-14, worst at [0]: 1.6449335668483844 vs 1.6449335668484242)
  ...
```

What it shows:

- In the release builds the overrun surfaces as the program's own `error stop`, far from the cause, or — with
  nvfortran `-fast` — not at all. `--recheck` ran the failing test again under `checks`: the write past the end of
  `x` is located at line 18. AddressSanitizer did not see it: the overflow stays inside one object.
- The uninitialised variable passes silently in every release build; `checks` traps it with gfortran and ifx.
  nvfortran's `checks` leaves it a quiet NaN (the test only prints it), as the table above says.
- The series sum disagrees by about 2e-14 relative between the release builds (`-O3 -ffast-math`, `-fast`, ifx
  `-O3`: vectorised, reassociated) and the `-O0` builds (sequential order). With an exact tolerance that is
  reported; whether it matters is what the case's [tolerance](/advanced/verify#tolerances) declares.

A disagreement compares each cell with the first cell that produced the quantity, with the case's tolerance;
`--verify` also compares each cell with the stored reference.

## What a matrix finds in real libraries

Run on FLAP, FiNeR, StringiFor, PENF, BeFoR64 and json-fortran (their own test programs, gfortran 16, ifort
2024.2 for json-fortran's Intel modes):

- **A compiler-specific failure.** json-fortran's sources do not build with gfortran 16 (a character length
  error in `json_value_module.F90`) in any mode or shadow, while its ifort modes build: the failure belongs to
  the compiler, not to the code's configuration.
- **Conformance.** `strict` reports what the projects rely on beyond the standard: a literal outside the
  symmetric integer range, finalized structure constructors ("removed by f08/0011"), `$` in an identifier.
- **Leaks.** `sanitize` fails most of FLAP's and FiNeR's tests with LeakSanitizer reports, each named with its
  size and allocation site (`memory leak (LeakSanitizer): 164 byte(s) leaked in 3 allocation(s), allocated at
  src/tests/finer_test_get.f90:25`).
- **Traps on intended IEEE behaviour.** A test of StringiFor converts out-of-range strings to `real(4)` on purpose
  and checks that the result is infinite; the `checks` shadow traps the overflow inside the C library's number
  parsing (`floating-point exception at src/lib/stringifor_string_t.F90:4088`). A floating-point trap reports
  every overflow, intended or not: read such a failure before calling it a bug.

## Notes

- Every cell is a full build: a matrix of 5 modes x 4 shadows is 20 builds. `--modes`, `--shadows`,
  `--compilers` and `--no-tests` keep it to what you need.
- `fobis matrix --json` gives every cell and disagreement (see [JSON output](/advanced/json-output#fobis-matrix-json));
  the MCP server exposes it as the `matrix` tool.
- Add `.fobis/` to `.gitignore`: shadow builds, case runs and their programs live there.
