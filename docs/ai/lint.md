# Linting

`fobis lint` reports bug-prone, obsolescent and non-portable Fortran constructs, and defects specific to
parallel code: data races in OpenMP regions, missing `reduction` clauses, `collapse` on loops that are not
tightly nested, OpenACC device calls without `!$acc routine`, saved locals in procedures that run in
parallel, timers read before `!$acc wait`, MPI requests never completed or their buffers touched too
early, collectives inside rank branches. Every rule is documented in the
[rule reference](/lint-rules/) and in the terminal with `fobis lint --explain <ID>`.

| Family | Covers |
|--------|--------|
| `COR` | Correctness: implicit typing, `intent`, implicit `save`, `stat=` handling, accessibility, `select` without default, misleading one-line `if`, `present()` tested and used in one condition, unreachable code |
| `OBS` | Obsolescent and deleted features: `common`, labelled DO, computed GO TO, `go to` an `end do`, `mpif.h` |
| `MDN` | Modernisation: `(/ /)` constructors, `.eq.` operators, attribute statements |
| `PRT` | Portability: numeric kinds (`real(8)`, `real*8`, `1.0_8`), tabs, compiler extensions |
| `STY` | Structure (opt-in mostly): modules per file, declaration shapes, procedure complexity and argument count. Formatting is left to formatters |
| `FOR` | Fortran practice for HPC: saved locals in parallel code, `f(x)%c`, `cpu_time` timing, default-real literals in double-precision code, finalisers that miss arrays, loop order, ghost-cell bounds lost in assumed-shape dummies |
| `OMP` | OpenMP: shared scalars written in parallel regions, missing reductions, `collapse`, MPI thread level, `critical`/`atomic` in the innermost loop, `nowait` races, per-iteration `target` maps |
| `ACC` | OpenACC: missing `!$acc routine`, atomics in device code, `declare create` reductions, async timing, strided sections passed in kernels, MPI on device data without updates |
| `MPI` | MPI: requests never completed, buffers touched while a request is pending, collectives in rank branches, send-before-receive deadlocks, `MPI_ANY_SOURCE` sums |
| `NUM` | Numerics: global floating-point sums of diagnostics (opt-in) |
| `PRF` | Performance reported by the compiler (needs `--compiler-feedback`) |
| `LNT` | The linter's own suppressions and preprocessor assumptions |

```bash
fobis lint                     # the sources of the fobos mode (or ./), default rules
fobis lint src/solver.F90      # specific files or directories
fobis lint --mode gnu-mpi      # analyse the code as compiled by that mode
```

```text
src/grid.F90:42: COR020 [warning] 'counter' in subroutine 'update' is initialised in its declaration (implicit save)
src/io.f90:7: OBS020 [warning] include of mpif.h (deprecated): use mpi_f08

2 finding(s) in 31 file(s): COR020 x1, OBS020 x1
Explain a rule with: fobis lint --explain <ID>
```

## What is analysed

- **The code your build compiles.** `#if`/`#ifdef` conditionals are resolved with the `-D` defines of the
  selected fobos mode (from `cflags` and `preproc`), so with `--mode gnu-mpi` the `#ifdef USE_MPI` branch is
  analysed and the `#else` branch is not. Without a fobos file no macro is defined. A condition beyond
  the evaluator (a function-like macro) is assumed true and reported as `LNT004` (info).
- **Free and fixed form**, chosen by file extension (`.f`, `.for`, `.fpp`, `.f77` are fixed form; fixed form
  ignores columns beyond 72, like the compilers' default).
- **Which files.** The paths given on the command line; otherwise the `src` directories of the fobos mode
  (default `./`), honouring the mode's `exclude` and `exclude_dirs`. Fetched dependencies (`.fobis_deps/`)
  and VCS directories are always skipped: lint your own code, not your dependencies'. A `.h` file that is
  a C header (it contains `/*`, `typedef`, `extern` or `#include <...>`) is skipped and counted in the
  summary.
- **The whole project at once.** All files are analysed before any rule runs, so rules can use facts
  from other files: a procedure called inside an OpenACC compute region is checked for `!$acc routine`
  wherever it is defined, and a procedure called inside a parallel region is checked for saved locals in
  its own file. Lint the project (or the mode's sources), not a single file, to get these checks.

The analysis works statement by statement; it is not a compiler. On syntax it does not recognise it skips
the statement and continues, so one unusual construct never hides the rest of a file. Macros used inside
Fortran code (a type spelled `VARTYPE(KKP)`) are not expanded; declarations written with them are still
recognised.

## Parallel code

The `FOR`, `OMP`, `ACC` and `MPI` rules analyse the directive regions of each procedure: the statements
between `!$omp parallel` and `!$omp end parallel`, the loop nest following `!$acc parallel loop`, and so on.
Their limits:

- Regions do not cross procedure boundaries: a variable written in a procedure called from a parallel
  region is checked only for SAVE (`FOR001`), not as a shared variable of the caller.
- Procedures are matched across files by name, without resolving `use` renames.
- `OMP001`/`OMP002` apply the Fortran data-sharing rules (loop variables of the region's DO loops are
  private; `private`, `firstprivate`, `lastprivate`, `reduction`, `linear` and `threadprivate` are
  honoured; writes inside `critical`, `atomic`, `single`, `master`/`masked` and `ordered` are not
  reported). Each shared variable is reported once per region, at its first write. A variable first
  assigned and then updated in the same iteration is reported as a shared temporary (`OMP001`), not as a
  missing reduction.

- Data-flow rules follow the statements of one procedure in source order, without unrolling loops:
  `OMP004` (reads after `nowait`, up to the next barrier), `MPI002`/`MPI003` (a request is pending from
  its non-blocking call to the first statement that uses the request again), `ACC009` (updates in the same
  procedure). `MPI002`/`MPI003` check whole-array buffers only: with `buf(k)` the message covers part of
  `buf`, and accesses to other parts are legal.
- `MPI004`/`MPI005` know a branch is rank-dependent when its condition uses a variable that
  `mpi_comm_rank` fills somewhere in the project (`myrank`, `self%rank`, ...).
- Kinds are resolved through the integer named constants of the linted sources (`R8P =
  selected_real_kind(15, 307)`, `rk = real64`, `kind(1.d0)` ...); a kind module outside them (a fetched
  dependency) is unknown, except the PENF names `R4P`/`R8P`/`R16P`. `FOR007` reports only literals that a
  single-precision real cannot represent exactly (`0.1`, `1.e-12`, not `0.5`).
- GPU code is not CPU code: `FOR002` (loop order) skips OpenACC compute regions, OpenMP `target` regions,
  device routines and CUDA Fortran `device` arrays, where the parallel index leads on purpose.

Several of these rules are **opt-in** because they are heuristics or matter only in some codes
(`FOR002`, `FOR003`, `NUM001`, `OMP004`, `OMP006`, `ACC007`, `ACC009`, `ACC010`, `MPI005`, `MPI006`): run
them with `--select` when reviewing parallel code.

When a finding is wrong for a reason the linter cannot see, suppress it with the reason (below): the
reason documents why the code is safe.

## Compiler feedback

The compiler knows things the source does not show: which arrays an OpenACC region copies implicitly at
every launch, which device loop it had to run sequentially, which OpenMP target maps it generated, which
loops it could not vectorise. `--compiler-feedback` reads the compiler's own optimisation report from a
build log and reports it as findings on your source lines, next to the other rules:

```bash
# 1. build once with the report flags (one job: messages of different files must not interleave)
fobis build --mode nvidia --cflags "-Minfo=accel,mp" -j 1 --force-compile --no-cache 2>&1 | tee build.log
# 2. lint with the report
fobis lint --mode nvidia --compiler-feedback build.log
```

```text
src/kernels.f90:9: ACC001 [warning] implicit data movement for the compute region: copyin(x(:n)), copy(y(:n))
src/kernels.f90:19: ACC012 [warning] loop runs sequentially on the device: loop-carried dependence of y
src/kernels.f90:29: OMP008 [warning] implicit map(tofrom:y(:)) for the target region
```

| Compiler | Report flags | Rules fed |
|----------|--------------|-----------|
| nvfortran | `-Minfo=accel,mp` | `ACC001` implicit data movement, `ACC012` sequential device loop, `OMP008` implicit target map |
| gfortran | `-fopt-info-vec-missed` | `PRF001` loop not vectorized (opt-in: `--select PRF001`) |

FoBiS does not run this build for you: a feedback build writes objects, and with a fobos mode the mode's
`build_dir` wins over `--build-dir`, so it would overwrite your build tree. When the log is missing,
`fobis lint` prints the exact command for the mode's compiler. nvfortran names procedures, not files: each
message is attributed through the project's procedures (and, for a name defined in several files, through
the `Compiling ...` lines of the log); a message that cannot be attributed unambiguously is counted in the
summary, never guessed. `-` reads the log from standard input.

These rules see the code the compiler built with *those* flags: a finding refers to the build configuration
of the log, so lint with the same `--mode`.

## Review with the LLM: `--deep`

The rules are deterministic and conservative: a finding says "this pattern is here", not "this is a bug in
your code". `--deep` asks the LLM to judge each finding against the code it is in, with citations, and to
point out related problems the rules missed.

```bash
fobis lint src/solver --select OMP,ACC,MPI --deep         # review the parallel findings
fobis lint --deep --deep-max 25                          # more regions (default 10)
fobis lint --deep-context                                # print what the model would receive, run no model
fobis lint src/flux.F90:120 --ask "is this region race-free?"
```

How it works:

1. **Groups.** Findings are grouped by the code they are about: the innermost OpenMP/OpenACC region, else the
   enclosing procedure (a window around the findings when it is long). Regions are reviewed first. Findings
   of the mechanical families (`OBS`, `MDN`, `PRT`, `STY`, `LNT`) are not sent: they are syntactic facts.
2. **One request per group**, with the code (finding lines marked), the procedure's declarations, the
   documentation of each rule and the pack sections it references, the compiler feedback for those lines
   (with `--compiler-feedback`), the interfaces of the procedures the code calls, and pack sections matching
   the directive's clauses.
3. **A verdict per finding**: `confirmed`, `dismissed` or `uncertain`, with a reason and citations, plus
   advisory concerns. The finding and source labels are enums of a JSON Schema, so a grammar-constrained
   model cannot cite what it was not given.
4. **FoBiS checks the answer.** A confirmed or dismissed verdict that cites nothing becomes `uncertain`; a
   concern that cites nothing is dropped; a finding the model skipped stays `uncertain`.

Nothing is hidden. A dismissed finding is still printed, with the model's reason under it, and still counts
in the exit status: the review informs you, it does not suppress. To silence a finding you agree is a false
positive, suppress it in the code with a reason (`! fobis: ignore[OMP001] ...`) or record it in the baseline.

```text
src/heat.f90:14: OMP001 [warning] 'flux' is shared and written by every thread (missing private?)
    [llm] confirmed: flux is written at line 14 by every iteration and read at line 15, and it is not private. [1][2]
src/heat.f90:16: OMP002 [warning] 'total' is accumulated by every thread: use reduction(+:total)
    [llm] confirmed: total is updated at line 16 by all threads without a reduction clause. [1][3]

Sources cited by the review:
  [1] src/heat.f90 lines 12-17 (!$omp parallel do (line 12))  (code:src/heat.f90:12-17)
  ...
Review [llm]: 1 of 1 group(s); 2 confirmed, 0 dismissed, 0 uncertain. Dismissed findings are still reported and still count.
```

(The shape of the output; the wording depends on the model.) `--format json` adds a `review` object to each
reviewed finding and a top-level `review` (concerns, sources, counts); other formats are not annotated.

`--ask "QUESTION" FILE:LINE` builds the same input for the region or procedure around that line, findings
included, and answers the question as cited claims (as [`fobis ask`](/ai/ask) does), without the lint report.

Cost: one model request per group. A large code has many groups (850 files of an HPC solver gave 580), so
narrow the review with paths and `--select`, and raise `--deep-max` deliberately.

## Automatic fixes

Some rules carry a mechanical fix (`MDN011` array constructors, `MDN021` relational operators). Review
the fixes as a diff, then apply them:

```bash
fobis lint --select MDN011,MDN021 --diff   # print a unified diff, change nothing
fobis lint --select MDN011,MDN021 --fix    # rewrite the files, then report what remains
```

Fixes touch code only: comments and character literals are left alone.

## Choosing rules

By default the rules marked *default* in the [rule reference](/lint-rules/) run. Select explicitly by id
or prefix; an explicit selection also enables *opt-in* rules:

```bash
fobis lint --select OBS                  # only the obsolescent-feature rules
fobis lint --select COR,OBS011           # comma-separated, or repeat --select
fobis lint --select ALL --ignore COR040  # everything except use-without-only
fobis lint --list-rules                  # id, name, severity, default, Fortitude equivalent
```

A project fixes its choice in the fobos [`[lint]` section](/fobos/lint); command-line `--select` replaces
the section's `select`, while `--ignore` adds to its `ignore`.

## Suppressing a finding

Silence one occurrence with a comment naming the rule and giving the reason, on the reported statement
(any of its lines) or alone on the line before it:

```fortran
real(R8P) :: total = 0._R8P  ! fobis: ignore[COR020] running total across calls is intended

! fobis: ignore[COR011, COR010] C interface: the buffer size is passed separately
subroutine fill(buf, n) bind(c)
```

The linter checks its own suppressions: a suppression without a reason is reported (`LNT001`), one that
no longer silences anything is reported (`LNT002`, it would silently hide a future finding on that line),
and a misspelled rule id is reported (`LNT003`).

## Adopting the linter on an existing code: the baseline

On a large existing code the first run reports hundreds of findings. Record them as the accepted state,
then fix them at your own pace while every *new* finding is reported:

```bash
fobis lint --update-baseline    # writes .fobis-lint-baseline.json; commit it
fobis lint                      # now reports only findings not in the baseline
```

```text
0 finding(s) in 214 file(s), 486 hidden by the baseline
```

Findings are matched to the baseline by rule, file and the text of the offending statement, not by line
number: inserting code above a recorded finding does not resurface it, while changing the offending
statement does. Re-run `--update-baseline` after fixing findings to shrink the file. The baseline path is
`--baseline FILE`, else `baseline` in the fobos `[lint]` section, else `.fobis-lint-baseline.json`
(used only when it exists).

## Output formats and CI

| `--format` | Use |
|------------|-----|
| `text` (default) | Terminal: `path:line: ID [severity] message` and a summary |
| `json` | Scripts: findings with rule, name, severity, path, lines, message, fingerprint |
| `sarif` | [SARIF 2.1.0](https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html): GitHub code scanning, IDE viewers |
| `github` | GitHub Actions annotations on the pull-request diff |

The exit code is 1 when a warning- or error-level finding remains (or a file cannot be read), 0 otherwise;
`--exit-zero` always exits 0 (useful when uploading a report).

Annotations on pull requests:

```yaml
- run: pip install FoBiS.py
- run: fobis lint --format github
```

GitHub code scanning (findings tracked across commits in the repository's *Security* tab):

```yaml
- run: pip install FoBiS.py
- run: fobis lint --format sarif --exit-zero > fobis-lint.sarif
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: fobis-lint.sarif
```

## Relation to other tools

The generic rules reimplement, natively and in FoBiS's own words, rules catalogued by
[Fortitude](https://fortitude.readthedocs.io/); the [rule reference](/lint-rules/#relation-to-fortitude)
gives the matching Fortitude code of each. Formatting (line length, spacing, keyword case) is deliberately
out of scope: leave it to a formatter such as fprettify.
