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

## Device link-time optimisation

`-acc -gpu=cc89,lto` (any capability with `lto`, with a GPU programming model: alone, the lto suboption is refused) optimises the device code of the whole program at the link:
`nvlink` runs NVVM and ptxas over every object's device code, by default on one thread. Measured with nvfortran 26.9
(CUDA 13.3) on an OpenACC solver of about 230 objects: the link took 491 s, 98% of it in `nvlink`, against a few
seconds without `lto`; it was the larger part of every build that linked.

`-Wnvlink,OPTION` passes OPTION to `nvlink` (`-Xnvlink` and `--nvlink-options` are synonyms). nvlink 13.3 offers
`--split-compile=N` and `--split-compile-extended=N` (threads used by LTO; the two exclude each other, nvlink keeps
the extended one). Measured on the same program, 16 cores, link only:

| Link option | Link | Peak memory of the link | Program |
|---|---|---|---|
| none | 491 s | 6.2 GB | 112.19 MB |
| `-Wnvlink,--split-compile=16` | 157 s | 17.0 GB | 112.23 MB |
| `-Wnvlink,--split-compile=0` | 180 s | 17.0 GB | 112.22 MB |
| `-Wnvlink,--split-compile-extended=16` | 212 s | 2.5 GB | 108.80 MB |

The host symbols of the four programs are identical; the device code is not (other sizes), so the kernels' speed
must be measured again before adopting one: split compilation optimises partitions separately. The option goes into
the mode's `lflags` (link only).

## Standard conformance and profiling

`-Mstandard` warns about non-standard code; with `-Werror` the warnings are errors
(`fobis build --shadow strict`). `-pg` instruments for gprof (`fobis profile --tool gprof`).

## Known bug: CUDA error 719 on a reduction into a declare-create variable

An OpenACC `reduction` into a module variable declared with `!$acc declare create` has failed at run time with
CUDA error 719 (launch failure); documented with a reproducer in the hpc-practice pack, which
`fobis run --explain` cites when it recognises the error.
