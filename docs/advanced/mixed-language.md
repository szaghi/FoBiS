# Mixed-language projects

C files (`.c`) among the sources are compiled with a C compiler and linked with the Fortran objects: a project that
carries a few C files (system calls, a timer, a wrapper of a C library called through `bind(c)`) builds with FoBiS
alone, with no separate library or custom rule.

## A timer in C

```c
/* src/clock.c */
#define _POSIX_C_SOURCE 199309L
#include <time.h>
#include "clock.h"

double wall_seconds(void) {
  struct timespec now;
  clock_gettime(CLOCK_MONOTONIC, &now);
  return (double)now.tv_sec + 1.0e-9 * (double)now.tv_nsec;
}
```

```c
/* src/clock.h */
double wall_seconds(void);
```

```fortran
module clock
use iso_c_binding, only: c_double
implicit none
interface
  function wall_seconds() bind(c, name="wall_seconds") result(t)
    import :: c_double
    real(c_double) :: t
  end function
end interface
end module
```

Nothing in the fobos names the C file: it is among the sources, so it is built.

```ini
[default]
compiler  = gnu
cflags    = -c -O2
c_cflags  = -c -O2 -std=c11
src       = ./src/
build_dir = ./build/
```

```console
$ fobis build
...
Building src/clock.c
Compiling src/clock.c serially
Building src/main.f90
Compiling src/clock.f90 serially
Compiling src/main.f90 serially
Linking build/main
Target src/main.f90 has been successfully built
```

## What FoBiS does with a C file

- **Scanning.** `.c` is among the default extensions. A mode that sets `extensions` itself must list `.c`.
- **Dependencies.** A C file is read for its `#include "..."` lines only, never as Fortran. Each names a project
  header: when the header changes, the C file is compiled again. `#include <...>` headers are the system's and are
  not followed. A header in a directory (`#include "sys/clock.h"`) is found by the end of its path, and the directory
  it is relative to is added to the include path. Every `#include` counts, whatever `#if` it sits under: an extra
  dependency only costs a recompile.
- **Headers.** A `.h` file written in C (a `/* */` comment, `typedef`, `extern`, `#include <...>`) is a C header:
  never compiled, never read as a Fortran include file.
- **Objects.** `clock.c` compiles to `clock.c.o`, so a `clock.f90` beside it keeps its `clock.o`.
- **Linking.** C objects are linked like Fortran files that define no module: every program gets every C object,
  because a call through `bind(c)` is not visible as a `use`. A library build puts them in the library (checked with
  `nm` on a static and a shared library).
- **Errors.** A C file that does not compile fails the build. A Fortran file without modules that fails is dropped
  from the link with a warning; a C file never is.

## The C compiler

Each compiler family has its C compiler. `--mpi` selects the family's MPI C wrapper, and `--openmp`, `--coverage` and
`--profile` add the C compiler's flag for the same thing:

| `compiler` | C compiler | with `mpi` | OpenMP |
|---|---|---|---|
| `gnu`, `opencoarrays-gnu` | `gcc` | `mpicc` | `-fopenmp` |
| `intel` | `icx` | `mpiicc -cc=icx` | `-qopenmp` |
| `intel_nextgen` | `icx` | `mpiicx` | `-qopenmp` |
| `nvfortran` | `nvc` | `mpicc` | `-mp` |
| `pgi` | `pgcc` | `mpicc` | `-mp` |
| `amd` | `amdclang` | `mpicc` | `-fopenmp` |
| `ibm` | `xlc_r` | `mpicc` | `-qsmp=omp` |
| `nag` | `gcc` | `mpicc` | `-fopenmp` |
| `g95`, `lfortran`, `custom` | `gcc` (`g95`), `cc` | `mpicc` | none |

Measured: gcc 16 with gfortran, nvc 26.5 with nvfortran, icx 2026.1 with ifx 2025.3, `mpicc` of Open MPI 5.0. The
other C compilers in the table are the vendors' documented names; they were not on the test machine.

Three mode keys, and the matching command-line options, set the C side:

| Key | Option | Default | What |
|---|---|---|---|
| `cc` | `--cc` | the table above | the C compiler command |
| `c_cflags` | `--c-cflags` | `-c` | compile flags of the C files (`-c` is added when missing) |
| `c_preproc` | `--c-preproc` | none | preprocessor flags of the C files (`-DNAME`, `-I...`) |

The Fortran `cflags` and `preproc` are **never** applied to C: the two languages share few flags (`-fcheck=all` is
not a C option, `-std=f2018` is not a C standard). Write the C flags in `c_cflags`:

```ini
[release]
compiler  = gnu
cflags    = -c -O3
c_cflags  = -c -O3 -march=native
c_preproc = -DNDEBUG
```

A shared library needs `-fPIC` in both: `cflags = -c -fPIC` and `c_cflags = -c -fPIC`.

### Build profiles

A [build profile](/advanced/build-profiles) adds C flags too, before the mode's `c_cflags` (which therefore win). For
example `gnu` + `debug` gives `-O0 -g -Wall -Wextra` and `gnu` + `asan` gives
`-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer`, so the C code is instrumented with the Fortran code.
`fobis build --list-profiles` shows them after `[C: ...]`. Each one was compiled with gcc, icx and nvc; the `amd`
ones are the plain Clang `-O0 -g` and `-O3`.

## Everywhere else

- **Compilation database.** `compile_commands.json` has an entry per C file, with the C compiler's command, so a C
  language server finds the include paths and the macros. See
  [compilation database](/reference/build#compilation-database).
- **Makefile export.** The Makefile gets `CC` and `OPTSCC` and a rule per C file, with its headers as prerequisites.
  See [GNU Makefile export](/advanced/makefile).
- **Compiler change.** The record that triggers a full rebuild when the compiler changes (a `module load`) holds the C
  compiler's path and version too.
- **`--json`.** A C compile error is a diagnostic of `build --json` with file and line, and `tool: "c"` (the GCC
  and Clang form, and nvc's `"file", line N: error:` form).
- **`introspect`.** `--compiler` shows `cc` and `c_cflags` as resolved for the mode; `--sources` gives each file's
  `language`.
- **`cflags_heritage`.** The heritage file holds the C command and flags as well, when the mode sets any C key.

## What C files are left out of

- **Analysis.** `lint`, `query`, `review` and the other analysis commands read Fortran only and skip `.c` files.
- **`--explain`.** It explains Fortran errors: the first error of a build in a C file is left to the C compiler's
  message.
- **Shadow modes and assessment variants.** Shadow modes (`--shadow checks`) and the flags of `fobis assess` apply to
  the Fortran flags only.
- **PreForM.** The Fortran preprocessor never runs on C files.
