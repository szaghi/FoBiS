# GNU Fortran (gfortran)

Facts about gfortran that change what a program computes, how it fails, or whether it builds. Each behaviour
marked "measured" was observed on small programs (gfortran 11 to 16 on x86-64 Linux, an AVX2/FMA processor);
flags are those of the GCC manual. FoBiS uses this family for `compiler = gnu` and `compiler = opencoarrays-gnu`.

## Default optimisation and debug information

Without an `-O` flag gfortran compiles at `-O0`; `-O` alone means `-O1`; the last `-O` on the command line wins.
`-g` adds debug information and does not change the optimisation level. An optimised build with `-g` still
reorders and inlines code: its backtraces and line numbers can point at the wrong statement. Locate a crash with
an unoptimised build (`-O0 -g`), which is what `fobis build --shadow checks` builds.

## Runtime checks

`-fcheck=all` enables every runtime check: `bounds` (array subscripts, and character lengths of dummy
arguments), `pointer` (pointers and allocatables),
`mem` (allocation failures), `do` (changes to a DO variable inside the loop), `recursion`, `bits` and
`array-temps` (a run-time warning when an array temporary is created). A bounds error is reported with its
location (measured, gfortran 16, `-O0 -g -fcheck=all`):

```
At line 18 of file kernels.f90
Fortran runtime error: Index '11' of dimension 1 of array 'a' above upper bound of 10
```

`-fbacktrace` (on by default) prints a backtrace on runtime errors; frames show `???` without debug information.
Bounds checks cannot check the last dimension of an assumed-size dummy (`a(*)`): it has no upper bound. The
address sanitizer (below) catches an overflow through it.

## Floating-point traps and uninitialised reals

`-ffpe-trap=invalid,zero,overflow` turns invalid operations, division by zero and overflow into `SIGFPE`; the
program stops at the offending operation instead of carrying NaN or Inf. `-finit-real=snan` initialises local
reals to a signalling NaN, so with the `invalid` trap the first arithmetic use of an uninitialised real stops
the program (measured: SIGFPE). Other initialisers: `-finit-integer=N`, `-finit-logical=true`,
`-finit-derived` (components of derived types).

The SIGFPE report is a backtrace; with `-g` it names the line (measured):

```
Program received signal SIGFPE: Floating-point exception - erroneous arithmetic operation.
...
#3  0x6061c8416278 in fpe
	at fpe.f90:5
```

The traps are set for the whole process when the main program starts: code from other libraries running in the
same process traps too, including code that produces an Inf or NaN on purpose.

## Sanitizers

`-fsanitize=address` (AddressSanitizer) finds stack and heap buffer overflows, including a heap overflow
through an assumed-size dummy that `-fcheck=bounds` cannot see (measured), and use after free. LeakSanitizer,
part of it on Linux, reports allocations never freed at exit. `-fsanitize=undefined` adds undefined-behaviour
checks. Both flags must be given to the link as well; keep `-fno-omit-frame-pointer` and `-g` for readable
reports. `fobis build --shadow sanitize` builds with `-O1 -g -fno-omit-frame-pointer
-fsanitize=address,undefined`.

## Floating-point contraction (FMA)

gfortran contracts `a*b + c` into a fused multiply-add when the target instruction set has FMA: the default is
`-ffp-contract=fast`. The plain x86-64 target has no FMA, so `-O2` alone gives no contraction; `-march=native`
on an FMA processor, `-march=x86-64-v3` or `-mfma` do. Measured: `a*b + c` with `a*b = 1 - 2**-60` and
`c = -1` gives 0 without FMA and `-2**-60` with it at `-O2`; no contraction at `-O0`; `-ffp-contract=off`
disables it. A change of the `-march=` target alone can therefore change results in the last bits: compare runs built for
the same target, or declare a tolerance.

## Fast math

`-ffast-math` (also part of `-Ofast`) lets the compiler reassociate, assume no NaN or Inf
(`-ffinite-math-only`) and ignore signed zeros. Measured consequences:

- Compensated (Kahan) summation is simplified away: a single-precision Kahan sum of 10^7 terms 0.1 had a relative
  error of 1.5e-8 at `-O2` and 8.8e-2 with `-O2 -ffast-math` (2.4e-2 with `-Ofast`).
- `ieee_is_nan(x)` and `x /= x` return false for a NaN `x` with `-ffast-math` or `-ffinite-math-only`: NaN
  guards silently stop working.

`-O3 -march=native` alone kept IEEE semantics in the same measurement (Kahan sum unchanged).

## Precision promotion flags

Measured `kind()` of each declaration:

| Flags | real | double precision | real(real32) | real(real64) | real(8) |
|-------|------|------------------|--------------|--------------|---------|
| none | 4 | 8 | 4 | 8 | 8 |
| `-fdefault-real-8` | 8 | 16 | 4 | 8 | 8 |
| `-fdefault-real-8 -fdefault-double-8` | 8 | 8 | 4 | 8 | 8 |
| `-freal-4-real-8` | 8 | 8 | 8 | 8 | 8 |
| `-freal-4-real-8 -freal-8-real-16` | 8 | 16 | 8 | 16 | 16 |

`-fdefault-real-8` promotes only declarations without a kind (and `double precision` to 16 unless
`-fdefault-double-8`); `-freal-4-real-8` promotes every kind-4 real, explicit kinds included. Promotion changes
record lengths of unformatted files, `storage_size` results and C interoperability: code that stores a real
into an integer of fixed size, or reads binary files written by an unpromoted build, breaks.
`-fdefault-integer-8` makes default integers 8 bytes (measured), which breaks calls into libraries compiled with
4-byte integers (MPI, BLAS) unless they were built the same way. `fobis assess` uses
`-freal-4-real-8 -freal-8-real-16` for its `precision` family with gfortran.

## Automatic arrays and the stack

gfortran allocates large automatic arrays and array temporaries on the heap unless `-fstack-arrays` is given;
`-Ofast` enables `-fstack-arrays`. Measured: an automatic array of 4 million double-precision values (32 MB)
in a subroutine runs at `-O2` and dies with SIGSEGV at `-Ofast` or `-O2 -fstack-arrays` under an 8 MB stack
limit (`ulimit -s 8192`). Raise the limit, or keep large work arrays allocatable. With OpenMP each thread other
than the initial one has a stack sized by `OMP_STACKSIZE`.

## Module files

`.mod` files carry a format version: gfortran 11 to 14 write version 15, gfortran 15 and 16 write version 16
(measured). gfortran 15 and 16 read both versions; gfortran 14 and older refuse version 16 with:

```
Fatal Error: Cannot read module file 'm.mod' opened at (1), because it was created by a different version of GNU Fortran
```

The same rule applies to the `.mod` files of installed libraries (`mpi`, `mpi_f08`, `hdf5`): they must come
from a gfortran that writes a format the compiler reads. After changing compiler, rebuild the project from
scratch (`fobis build --force-compile`): FoBiS's timestamp check does not notice a new compiler with the same
command name. The verification commands (`case`, `verify`, `assess`, `diff-run`, `bench`) rebuild
automatically when the compiler's path or `--version` changes.

## Optimisation reports

`-fopt-info-vec-optimized` and `-fopt-info-vec-missed` report which loops were vectorised and why others were
not, as `file:line:column: optimized: ...` and `missed: ...` lines. `fobis bench --feedback` compares these
reports between two revisions; `fobis lint --compiler-feedback LOG` attributes them to procedures.

## Profiling

`-pg` instruments for gprof: the program writes `gmon.out` at exit (one file per process with
`GMON_OUT_PREFIX`). Compile and link with `-pg`. `fobis profile --tool gprof` builds this variant and maps the
flat profile to the project's procedures.

## Standard conformance

`-std=f2018` (or `f2008`, `f2023`) rejects extensions such as `real*8`; `-pedantic` reports more; `-Werror`
turns warnings into errors. `-Wall -Wextra` warn about unused variables, character truncation and more;
`-Wconversion` about implicit conversions. `fobis build --shadow strict` builds with
`-std=f2018 -pedantic -Werror`.

## Parallel models

`-fopenmp` enables OpenMP (and links its runtime); `-fopenacc` enables OpenACC, which offloads only with a
gfortran built with an offload target (otherwise the regions run on the host). `-fcoarray=single` compiles
coarray code for one image; `-fcoarray=lib` with the OpenCoarrays library runs several images
(`compiler = opencoarrays-gnu` in a fobos mode uses the `caf` wrapper).

## Known bug: EFAULT with pointer sections at -O2

A pointer array section passed to a dummy declared with an explicit lower bound has produced wrong addresses
(EFAULT, "Bad address") in gfortran at `-O2` and above; documented with a reproducer in the hpc-practice pack,
which `fobis run --explain` cites when it recognises the error.
