# Intel Fortran (ifx, ifort)

Facts about the Intel Fortran compilers that change what a program computes, how it fails, or whether it
builds. "Measured" means observed on small programs with ifx 2025.3 (and ifort 2024.2 where named) on x86-64
Linux with an AVX2/FMA processor. FoBiS uses this family for `compiler = intel_nextgen` (ifx) and
`compiler = intel` (ifort).

## ifx and ifort

ifx is the LLVM-based compiler; ifort is the classic one. On the measured installation ifort exists only in the
2024.2 release directory and the 2025.3 release ships ifx alone. New builds should use ifx; the two accept
mostly the same flags but differ in sanitizer support (below) and in some defaults.

## Default optimisation and debug information

Without an `-O` flag ifx optimises at `-O2`; with `-g` and no `-O` it compiles at `-O0` (measured from the
driver's `-###` output). An `-O2` build is the default, so a crash in a build without explicit flags comes from
optimised code: its traceback can name the wrong line. Locate it with `-O0 -g -traceback`, which is what
`fobis build --shadow checks` builds.

## Runtime checks

`-check all` enables bounds, pointer, shape and other runtime checks; `-traceback` prints the call stack with
routine, line and file. A bounds error (measured, `-O0 -g -check all -traceback`):

```
forrtl: severe (408): fort: (2): Subscript #1 of the array A has value 11 which is greater than the upper bound of 10

Image              PC                Routine            Line        Source
bounds             000000000040594F  smooth                     18  kernels.f90
bounds             00000000004052F4  bounds                      6  bounds.f90
```

`-fpe0` traps invalid operations, division by zero and overflow (`forrtl: error (73): floating divide by zero`
with the traceback row of the operation, measured). `-init=snan,arrays` initialises local reals, including
arrays, to a signalling NaN: with `-fpe0` the first use of an uninitialised real stops the program at its line
(measured).

## Floating-point model: fast by default

ifx's default floating-point model is `-fp-model fast=1`: the compiler may reassociate and simplify
expressions. Measured consequences at `-O2` without other flags:

- Compensated (Kahan) summation is simplified away: a single-precision Kahan sum of 10^7 terms 0.1 had a relative
  error of 1.1e-2 at `-O2` (the same with `-fp-model fast=2`) and 1.5e-8 with `-O2 -fp-model precise` or at
  `-O0`.
- `ieee_is_nan(x)` and `x /= x` were still true for a NaN at the default model and with `-fp-model precise`;
  with `-fp-model fast=2` both were false.

Use `-fp-model precise` (or `strict`, which also gives access to the floating-point environment) for code whose
accuracy depends on the order of operations: compensated sums, error-free transformations, interval
arithmetic, reproducibility tests. `fobis assess` uses `-fp-model precise` and `-fp-model fast=2` among its
`rounding` variants for this family.

## Floating-point contraction (FMA)

The default target of ifx has no FMA instructions: `a*b + c` was not contracted at `-O2` (measured).
`-xHost` on an FMA processor, or `-march=x86-64-v3`, contracted it (`a*b = 1 - 2**-60`, `c = -1` gave
`-2**-60` instead of 0); `-no-fma` and `-fp-model precise` prevented the contraction in the same measurement.

## Automatic arrays, temporaries and the stack

ifx places automatic arrays and the temporary copies of array expressions on the stack. Measured, with an
8 MB stack limit: an automatic array of 4 million double-precision values and an overlapping section assignment
`a(2:n) = a(1:n-1) + a(2:n)` with n = 4 million both died at `-O2` with

```
forrtl: severe (174): SIGSEGV, segmentation fault occurred
```

and ran with `-heap-arrays`, which puts them on the heap. gfortran and nvfortran ran both programs without
flags (measured), so this crash typically appears when a code that works with other compilers is first built
with ifx. With OpenMP the stacks of the other threads are sized by `OMP_STACKSIZE`.

## Precision promotion flags

Measured `kind()` of each declaration:

| Flags | real | double precision | real(real32) | real(real64) | real(8) |
|-------|------|------------------|--------------|--------------|---------|
| none | 4 | 8 | 4 | 8 | 8 |
| `-real-size 64` | 8 | 8 | 4 | 8 | 8 |
| `-real-size 64 -double-size 128` | 8 | 16 | 4 | 8 | 8 |

Only declarations without an explicit kind are promoted: a code that declares its kinds through a kind module
(`real(R8P)`, `real(real64)`) is not changed by these flags; promote it by changing the kind parameter.
`-integer-size 64` makes default integers 8 bytes (measured).

## Sanitizers

ifx accepts `-fsanitize=address` (compile and link). Measured: it catches stack and global buffer overflows;
a heap overflow through an assumed-size dummy was missed. ifort does not support it: it prints
`warning #10006: ignoring unknown option '-fsanitize=address'` and builds without it, so a sanitized ifort
build runs unchecked. `fobis build --shadow sanitize` refuses ifort for this reason.

## Module files

ifx refuses `.mod` files written by another compiler:

```
error #7013: This module file was not generated by any release of this compiler.   [MPI_F08]
```

(measured with the `mpi_f08` module of an Open MPI built with gfortran). Libraries used through modules (MPI,
HDF5, NetCDF) need a build made with the Intel compiler; Intel MPI ships its own `mpi` and `mpi_f08` modules
(`include/mpi/` of the installation).

## Standard conformance

`-stand f18` warns about non-standard code; `-warn stderrors` makes those warnings errors and `-warn errors`
all warnings. `fobis build --shadow strict` builds with `-stand f18 -warn stderrors -warn errors`.

## Optimisation reports and profiling

`-qopt-report=3` writes the optimisation report to `.optrpt` files (FoBiS does not parse them). `-p`
instruments for gprof (`fobis profile --tool gprof`). `-qopenmp` enables OpenMP.
