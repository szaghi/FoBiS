# Comparing gfortran, ifx and nvfortran

The defaults that make the same source give different numbers, or fail differently, under each compiler. Every
row was measured on small programs (gfortran 16, ifx 2025.3, nvfortran 26.1, x86-64 Linux with FMA); the
compiler documents of this pack give the details.

## Defaults that change results

| | gfortran | ifx | nvfortran |
|---|---|---|---|
| optimisation without `-O` | 0 | 2 (0 with `-g`) | 1 (0 with `-g`) |
| FMA contraction by default | only when the target has FMA (`-march=...`), not at `-O0` | only with an FMA target (`-xHost`, `-march=...`) | yes, at every level (host target) |
| turn contraction off | `-ffp-contract=off` | `-no-fma` or `-fp-model precise` | `-Mnofma` |
| value-unsafe optimisation by default | no | yes (`-fp-model fast=1`) | no |
| Kahan sum kept at `-O2` | yes | no (needs `-fp-model precise`) | yes |
| NaN tests broken by | `-ffast-math`, `-ffinite-math-only` | `-fp-model fast=2` | not observed (`-fast` kept them) |

Consequence: a result that differs between compilers in the last digits is not, by itself, a bug. To find
where the difference comes from, rebuild with contraction off and value-safe models on every compiler
(`-ffp-contract=off`; `-fp-model precise`; `-Mnofma`): if the results then agree within rounding, the
difference was FMA or reassociation. `fobis assess` measures this spread for a declared case with its
`compiler` and `rounding` families.

## Defaults that change failures

| | gfortran | ifx | nvfortran |
|---|---|---|---|
| automatic arrays and temporaries | heap (stack with `-fstack-arrays`, part of `-Ofast`) | stack (`-heap-arrays` moves them) | heap in the measured cases |
| uninitialised real with checks | SIGFPE (`-finit-real=snan -ffpe-trap=invalid`) | located (`-init=snan,arrays -fpe0`) | quiet NaN, no trap (`-Minit-real=snan`) |
| bounds error message | `At line N of file F` | `forrtl: severe (408)` + traceback table | `Subscript out of range for array a (F: N)` |
| sanitizer | `-fsanitize=address,undefined` | `-fsanitize=address` (ifort: ignored) | none |

`fobis build --shadow checks` and `--shadow sanitize` apply the right flags per compiler; `fobis matrix` runs a
project's tests and cases under several compilers and shadows.

## Promotion flags promote different declarations

| Flags | real | double precision | real(real32) | real(real64) |
|-------|------|------------------|--------------|--------------|
| gfortran `-fdefault-real-8` | 8 | 16 | 4 | 8 |
| gfortran `-freal-4-real-8` | 8 | 8 | 8 | 8 |
| ifx `-real-size 64` | 8 | 8 | 4 | 8 |
| nvfortran `-r8` | 8 | 8 | 4 | 8 |

Only gfortran's `-freal-4-real-8` promotes explicit kinds. A code with a kind module (`R8P`, `real64`) is promoted
portably by changing the kind parameter, not by flags.

## Module files and libraries

`.mod` files are compiler-specific: ifx (`error #7013`) and nvfortran (`NVFORTRAN-F-0004-Corrupt or Old
Module file`) refuse gfortran's, and old gfortran releases refuse the format of new ones. Every library used
through modules (MPI, HDF5, NetCDF, a fetched FoBiS dependency built as a library) must be built by the same
compiler, in a module format it reads. With `use=sources` dependencies FoBiS compiles them with the project's
compiler, which avoids the problem.

## Symbol names in linker errors

Module procedures get different link names: `__m_MOD_p` (gfortran), `m_mp_p_` (ifx, ifort), `m_p_` (nvfortran)
for procedure `p` of module `m`. An undefined reference to a name of another compiler's form means objects or
libraries built by a different compiler are being linked: rebuild everything with one compiler
(`fobis build --force-compile`). `fobis build --explain` recognises these names and reports the procedure and
module.
