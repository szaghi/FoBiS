# NVIDIA Fortran (nvfortran)

Facts about nvfortran (the NVIDIA HPC SDK compiler, formerly PGI) that change what a program computes, how it
fails, or whether it builds. "Measured" means observed on small programs with nvfortran 26.1 on x86-64 Linux
(an Alder Lake class processor with FMA); option texts are those printed by `nvfortran -help`. FoBiS uses this
family for `compiler = nvfortran` and `compiler = pgi`.

## Default optimisation and target

Without an `-O` flag nvfortran optimises at level 1; with `-g` and no `-O` at level 0; `-O` alone means level 2
(measured from `nvfortran -dryrun`, which shows `-opt N` in the back-end command).

nvfortran compiles for the processor it runs on: `nvfortran --version` names the target (`-tp alderlake` on
the measured machine). Binaries built on a newer processor may not run on an older one: set the target with `-tp=` explicitly
(`-tp=px` for a generic x86-64 target) when the build and the compute nodes differ.

## FMA is on, even at -O0

Because the default target has FMA, nvfortran contracts `a*b + c` into a fused multiply-add at every
optimisation level. Measured: `a*b = 1 - 2**-60`, `c = -1` gave `-2**-60` (contracted) at `-O0`, at the default
level, at `-O2`, with `-fast` and with `-Kieee`; it gave 0 with `-Mnofma` or `-tp=px`. `-Kieee` does not
disable contraction. When nvfortran results differ from another compiler's in the last bits, build both with
contraction off (`-Mnofma` here, `-ffp-contract=off` for gfortran) to see whether FMA explains it.

## -fast

`nvfortran -help -fast`: "Common optimizations; includes -O2 -Munroll=c:1 -Mlre -Mautoinline. Implies
-Mvect=simd -Mflushz -Mcache_align". `-Mflushz` flushes subnormal results to zero. Measured: a single-precision
Kahan sum kept its accuracy with `-fast` (relative error 1.5e-8, as at `-O2`), and `ieee_is_nan` still detected a
NaN.

## Runtime checks

`-Mbounds` checks array subscripts (measured, `-O0 -g -Mbounds -traceback`):

```
0: Subscript out of range for array a (kernels.f90: 18)
    subscript=11, lower bound=1, upper bound=10, dimension=1
```

`-Mchkptr` checks for null pointers; `-traceback` adds a call stack to runtime errors. `-Ktrap=fp` traps
invalid operations, division by zero and overflow: the measured division by zero ended with SIGFPE and no
message on stderr, so the location must come from a debugger.

`-Minit-real=snan` does not give a trap on uninitialised reals: measured, it writes the quiet NaN `7FC00000`,
so the program runs on with NaN instead of stopping at the first use. Compare its results with a gfortran or
ifx build under their checks to locate an uninitialised real.

## No sanitizer

nvfortran 26.1 rejects `-fsanitize=address` with `nvfortran-Error-Unknown switch: -fsanitize=address`.
Memory errors in host code are found with a gfortran or ifx sanitized build of the same sources, or with
Valgrind; device memory errors with NVIDIA's `compute-sanitizer`.

## Precision promotion flags

Measured `kind()` of each declaration:

| Flags | real | double precision | real(real32) | real(real64) | real(8) |
|-------|------|------------------|--------------|--------------|---------|
| none | 4 | 8 | 4 | 8 | 8 |
| `-r8` | 8 | 8 | 4 | 8 | 8 |

`-r8` promotes only default `real`; explicit kinds are unchanged. `-i8` makes default integers 8 bytes
(measured).

## Module files

nvfortran refuses `.mod` files written by another compiler:

```
NVFORTRAN-F-0004-Corrupt or Old Module file /opt/openmpi/.../lib/mpi_f08.mod (pm.f90: 3)
```

(measured with an Open MPI built with gfortran). The HPC SDK ships an Open MPI (HPC-X) built for nvfortran under
`comm_libs/`; use its `mpifort` or its modules.

## Compiler messages

Errors are reported as `NVFORTRAN-S-NNNN-message (file: line)` (severity letters: I information, W warning,
S severe, F fatal). `-Minfo=accel,mp,vect` reports what the compiler did with OpenACC and OpenMP regions and
loops, procedure by procedure (implicit data copies, loops run sequentially on the device, vectorised loops);
`fobis lint --compiler-feedback LOG` and `fobis bench --feedback` read these messages.

## GPU options

`-acc` enables OpenACC, `-mp=gpu` OpenMP target offload, `-cuda` CUDA Fortran. `-gpu=cc80` selects the compute
capability (8.0 here; `ccnative`: the visible GPUs). `-gpu=mem:managed` puts allocatable data in CUDA managed memory,
which hides missing data clauses: a code that is correct only with managed memory can fail with
`-gpu=mem:separate`. Device code uses FMA unless `-gpu=nofma`.

## Standard conformance and profiling

`-Mstandard` warns about non-standard code; with `-Werror` the warnings are errors
(`fobis build --shadow strict`). `-pg` instruments for gprof (`fobis profile --tool gprof`).

## Known bug: CUDA error 719 on a reduction into a declare-create variable

An OpenACC `reduction` into a module variable declared with `!$acc declare create` has failed at run time with
CUDA error 719 (launch failure); documented with a reproducer in the hpc-practice pack, which
`fobis run --explain` cites when it recognises the error.
