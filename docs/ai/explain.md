# Explaining failures

`fobis build --explain` explains why a build failed; `fobis run --explain` and `fobis test --explain` explain
why a program failed at run time (see [Runtime failures](#runtime-failures)).
For a build, FoBiS answers the failures it can diagnose from the
project's own facts, with no model; for the first error that needs reading the code, it asks the LLM for a
cause and a fix that cite the code they come from.

```bash
fobis build --explain                 # facts first, then the model for what they do not cover
fobis build --explain-context         # print what the model would receive, run no model
fobis build --mode gnu-debug --explain
```

Without `--explain` the build behaves as before. With it, the compiler output is printed as usual, followed by
the explanation; the exit status is still 1.

## Failures explained from facts

These need no model. FoBiS parses the compiler or linker messages (gfortran, Intel ifx/ifort, nvfortran,
LFortran, GNU ld, lld), scans the project, and looks at what the build compiled and linked.

| Failure | What FoBiS finds out |
|---------|----------------------|
| **Missing module** (`Cannot open module file`, ifx `#7002`, `NVFORTRAN-F-0004`, LFortran `modfile was not found`) | Which file defines it, and whether this build compiles it (excluded by `exclude`/`exclude_dirs`, outside `src`); a definition hidden by a preprocessor branch the mode's `-D` flags disable; a fetched dependency defining it; a library module (`mpi`, `mpi_f08`, `omp_lib`, `openacc`, `cudafor`, `hdf5`, `netcdf`) with the flag it needs; a declared dependency not fetched yet |
| **Undefined reference** | The symbol demangled (gfortran `__mod_MOD_proc`, ifx `mod_mp_proc_`, nvfortran `mod_proc_`), where it is defined, and why its object is not in the link: not compiled, in a file the program never reaches, a dependency not linked, a library (MPI, OpenMP, OpenACC, HDF5, netCDF, BLAS/LAPACK) missing from the link flags, no main program |
| **Objects of another compiler** | Missing runtime symbols (`_gfortran_*`, `for_*`, `pgf90_*` ...) of a compiler other than the mode's: stale objects from another mode |
| **Multiple definition** | The files that define the symbol, or two main programs in one link |
| **Internal compiler error** | Reported as a compiler defect, with the usual workarounds |

Errors that follow from an explained one are counted, not explained again: after a missing module, the
compiler often reports every name the module would have provided.

Two real outputs:

```text
Explanation (fobis build --explain)
src/linkmain.f90:2: module geometry is not available when src/linkmain.f90 is compiled
  - geometry is defined in extra/geometry.f90, which this build does not compile: `exclude_dirs` lists extra.
  fix: add the file to the build (fobos mode `src`, `exclude`, `exclude_dirs`)
```

```text
Explanation (fobis build --explain)
link: external_thing is referenced (referenced from MAIN__) but not linked
  - external_thing is defined in src/things.f90:6.
  - the target src/main.f90 does not link that file: no file it links uses the module(s) things.
  fix: FoBiS links the files a program reaches through `use`, plus the files without modules: put external_thing in a module that the caller uses, or in a file without modules
```

The second one is a FoBiS behaviour worth knowing: a program links the files it reaches through `use`
statements, plus the files that contain no module. An external procedure placed in a file that also holds a
module nobody uses is never linked.

## Errors explained by the model

For the first error no fact covers (a type mismatch, a syntax error, a constraint violation), FoBiS builds the
model's input from facts and asks for claims of two kinds, `cause` and `fix`, each citing its sources:

- the compiler message and the build settings (compiler, mode, flags);
- the source lines around the error, the error line marked `>`;
- the declarations of the procedure that contains it;
- the interfaces of the project procedures named on the error line (their header and dummy arguments);
- up to two sections of the knowledge packs found by searching the message, when they match well enough.

As with [`fobis ask`](/ai/ask), a claim that cites nothing is dropped, and with the managed runtime the
citations are constrained by a JSON Schema. Only the first such error is explained: fix it and rebuild,
since later errors often follow from it.

`--explain-context` prints that input and stops. For a type mismatch in a call, the sources are:

```text
[S1] semantic.f90 lines 4-14 (code:semantic.f90:4-14)
4  | contains
...
10 > total = area(1, 2)
...
[S2] declarations of subroutine bad (semantic.f90:5) (fact:semantic.f90#bad)
subroutine bad(n, x)
integer, intent(in) :: n
...
[S3] interface of function area (module geometry), geometry.f90:6 (fact:geometry.f90#area)
pure function area(r) result(a)
real, intent(in) :: r
real :: a
```

A real answer of coder-7b (the default managed model) on an NVIDIA A30, for the same file built with gfortran 12:
gfortran lists the undeclared symbol of line 11 first, so that is the error the model receives, and the other
three are listed after it:

```text
Explanation (fobis build --explain)
src/semantic.f90:11: Symbol ‘undeclared’ at (1) has no IMPLICIT type
  Cause:
    - The symbol 'undeclared' is used without being declared or implicitly typed. It is referenced on line 11, column 18. [1]
  Fix:
    - Declare the variable 'undeclared' before using it. For example: 'real :: undeclared'. [1]

  Sources:
    [1] src/semantic.f90 lines 5-14  (code:src/semantic.f90:5-14)
  (3 more error(s) not explained: fix this one first, then rebuild)
```

The model is configured as for every LLM feature (see [Local LLM Runtime](/ai/runtime)); without one, the
facts are still printed and FoBiS says why no model explanation is given.

## Limits

- Pack retrieval matches the words of the compiler message, which share few words with the standard: often no
  pack section qualifies, and the explanation rests on the code facts alone.
- The fix is a suggestion, not compiled by FoBiS: read it before applying it.
- Scanning the project after a failure takes a few seconds on large trees (about 5 s for 850 files).
- With `--json` the build output is the JSON report; `--explain` is ignored.

## Runtime failures

```bash
fobis run --explain                   # build (with --explain), run, explain a failure
fobis run --mode debug --explain
fobis test --explain                  # every failed test; the model only for the first one
```

The program's standard error is still printed as it runs, and recorded. When the program fails, FoBiS reads the
runtime message (gfortran, Intel, nvfortran), the backtrace, and the exit status, then says from facts:

| Failure | What FoBiS finds out |
|---------|----------------------|
| **Out-of-bounds access** | The array, index and bound, the failing statement, the array's declaration; for a dummy argument, the caller that passes it |
| **Unassociated pointer** | Intel's message, or gfortran/nvfortran bounds of an empty pointer (`1:0`, `0:-1`) recognised as such |
| **`error stop`** | The statement that printed the message, found by its text (Intel prints only the message) |
| **Optimised build** | The mode is optimised, has no debug information or no runtime checks: the backtrace is not trusted, and FoBiS names the fobos mode to reproduce the crash with (unoptimised, `-g`, same compiler preferred), or the flags of a debug mode to add when there is none |
| **Known compiler bugs** | gfortran -O2+ EFAULT (`errno=14`) on pointer sections passed to explicit-lower-bound dummies; nvfortran CUDA 719 on an OpenACC reduction into a `declare create` module allocatable, with the reductions of the project that match |
| **No location at all** | In a debug build, how to get one with a debugger |

**Optimised-build backtraces lie.** The frames of an `-O2`/`-O3` build are often mis-resolved: the reported
routine or line need not be where the fault is. FoBiS never explains a crash from such frames. It uses a
location only when the runtime message gives it (gfortran and nvfortran print the failing line even at
`-O3`) or when the build is unoptimised with debug information. Two real outputs:

```text
Explanation (fobis run --explain)
segmentation fault (invalid memory access)
  - runtime message: SIGSEGV: Segmentation fault - invalid memory reference.

mode opt is optimised (-O3), without debug information (-g), without runtime checks
  - the backtrace of an optimised build is often wrong: the reported routine or line may not be where the fault is, so FoBiS does not explain the crash from it.
  - with runtime checks a segmentation fault often becomes a located message (an index out of bounds, an unassociated pointer).
  fix: reproduce it in a debug build first: fobis run --mode debug --explain
  see: fobis kb show hpc-practice:gpu-practice#correctness-and-debugging-tools
```

```text
Explanation (fobis run --explain)
index 11 of array a is above its upper bound 10 at src/kernels.f90:18
  - runtime message: Index '11' of dimension 1 of array 'a' above upper bound of 10
  - statement: a(i) = 0.5 * (a(i) + a(i + 1))
  - declaration: real, intent(inout) :: a(:) (src/kernels.f90:14)
  - a is a dummy argument of smooth: the caller passes it, called from src/bounds.f90:6.
```

When the location is trusted, the model gets the runtime output, the build (flags, optimisation, debug
information, checks), the code around the failing line **and around its caller** (from the backtrace of a
debug build), and their declarations, and answers cited `cause`/`fix` claims as for build errors. In the
example above, the failing loop runs `i` to `n` and reads `a(i + 1)`, and the caller passes `a(10)` with
`n = 10`: both are in the model's sources.

## Options

| Option | Description |
|--------|-------------|
| `build --explain` | When the build fails, explain why: from facts, then with the model for the first error they do not cover |
| `run --explain`, `test --explain` | When the program fails, explain why: from facts, then with the model when the location is trusted |
| `--explain-context` | Like `--explain`, but print the model's input instead of running it |
