---
title: Code quality
---

# Code quality

FoBiS reads your Fortran the way your build compiles it and answers from that reading: `fobis lint` reports
bug-prone, obsolescent and non-portable constructs and parallel-code defects (data races in OpenMP regions, missing
`reduction` clauses, device calls without `!$acc routine`, MPI requests never completed, collectives in rank
branches); `fobis review` reports them on the lines a change touches; `fobis query` says who calls a procedure and
who writes a variable; `fobis modernize` applies the mechanical fixes and keeps them only when the tests and cases
say nothing changed; `fobis bindings` writes the C and Python interface of your modules.

How it works:

1. **Statements, not a parser.** Each file is cut into logical statements (continuation lines joined, comments
   dropped, `;` split, labels detached, OpenMP/OpenACC directives kept as statements). Fixed form is chosen by the
   extension (`.f`, `.for`, `.fpp`, `.f77`, `.fortran`, in either case) and ignores the columns beyond 72, as the
   compilers do by default. A statement the analysis does not recognise is skipped, and the rest of the file is
   still analysed. Macros used inside Fortran code (a type spelled `VARTYPE(KKP)`) are not expanded; the
   declarations written with them are still recognised.
2. **The mode's defines.** `#if`/`#ifdef` are resolved with the `-D` flags of the selected mode (its `cflags`,
   `preproc` and `features`), so `--mode mpi` analyses the `#ifdef USE_MPI` branch and not the `#else`. A mode with
   `openmp = True` makes the `!$` conditional lines code. Without a fobos, no macro is defined. A condition beyond
   the evaluator (a function-like macro) is assumed true and reported as [`LNT004`](/lint-rules/LNT004).
3. **The files.** The paths given on the command line, else the mode's `src` (default `./`) with its `exclude` and
   `exclude_dirs`. Fetched dependencies (`.fobis_deps/`) and VCS directories are always skipped: you lint your
   code, not your dependencies'. C sources are never analysed; a `.h` file holding C (`/*`, `typedef`, `extern`,
   `#include <...>`) is skipped and counted in the summary.
4. **A project index.** Every file is analysed before any rule runs, so a rule uses facts from other files: a
   procedure called inside an OpenACC compute region is checked for `!$acc routine` where it is defined, a kind
   parameter is resolved where it is declared, a branch is rank-dependent when its variable is filled by
   `mpi_comm_rank` anywhere in the project. Lint the project, not one file, to get these checks.

Tutorial: [the linter](/tutorial/quality/01-lint) and the rest of track 4. Reference: [`lint`](/reference/lint),
[`review`](/reference/review), [`query`](/reference/query), [`modernize`](/reference/modernize),
[`bindings`](/reference/bindings). Rules: [lint rules](/lint-rules/).

## Lint a project

```bash
fobis lint                         # the sources of the default mode, with its defines
fobis lint --mode mpi              # the code as that mode compiles it
fobis lint src/solver.F90 src/io/  # files or directories
fobis lint --src lib/              # the sources to scan when there is no fobos (repeatable)
fobis lint --explain COR002        # why a rule exists, and what to write instead
```

<<< @/examples/output/4-quality/01/lint.txt{console}

Every finding names its rule; `--explain` prints the rule's documentation, its Fortitude equivalent and the
knowledge-pack sections it rests on:

<<< @/examples/output/4-quality/01/explain.txt{console}

- **Exit status 1** when a finding of severity warning or error remains, or a file cannot be read; `info` findings
  never fail. `--exit-zero` always exits 0. An unknown rule id or format, or a malformed baseline, exits 1.
- **`--varset NAME`** applies the `[varset:NAME]` bindings first, as for a build.
- **Formatting is out of scope** (line length, spacing, keyword case): leave it to a formatter such as fprettify.
  The `STY` rules check structure only.

## Choose the rules

The rules marked *default* in the [rule reference](/lint-rules/) run unless you choose: 74 of the 105. Every default
rule was checked for false alarms against a corpus of 19 open-source Fortran repositories; the heuristics and the
matters of project policy ship opt-in. An explicit selection, by id or prefix, also turns on the opt-in rules it
matches:

```bash
fobis lint --select OBS,MDN               # comma-separated, or repeat --select
fobis lint --select ALL --ignore COR040   # everything except use-without-only
fobis lint --select COR01                 # a prefix: COR010 to COR019
fobis lint --list-rules                   # id, name, severity, default or opt-in, Fortitude equivalent
```

<<< @/examples/output/4-quality/01/select.txt{console}

The families: `COR` correctness, `OBS` obsolescent and deleted features, `MDN` modernisation, `PRT` portability,
`STY` structure, `FOR` Fortran practice for HPC, `OMP` OpenMP, `ACC` OpenACC, `MPI` MPI, `NUM` numerics, `PRF`
performance reported by the compiler, `LNT` the linter's own suppressions and assumptions. The generic rules
reimplement, natively, rules catalogued by [Fortitude](https://fortitude.readthedocs.io/); each rule page names its
Fortitude code.

A project fixes its choice once, for every developer and the CI, in a `[lint]` section:

```ini
[lint]
; rule ids or prefixes, comma- or space-separated; ALL for every rule
select   = COR, OBS, OMP
; rule ids or prefixes skipped
ignore   = COR040, OBS011
; findings recorded here are not reported
baseline = .fobis-lint-baseline.json
```

- **Precedence:** `--select` replaces `select`, `--ignore` adds to `ignore`, `--baseline` replaces `baseline`.
- **One section for all modes.** The sources, exclusions and defines come from the mode (`--mode`); the rules come
  from `[lint]`. `fobis review` reads the same section.

## Lint parallel code

The `FOR`, `OMP`, `ACC` and `MPI` rules analyse the directive regions of each procedure: the statements between
`!$omp parallel` and `!$omp end parallel`, the loop nest after `!$acc parallel loop`, the statement after
`!$omp atomic`.

```bash
fobis lint --mode openmp --select OMP,ACC,MPI,FOR    # the parallel rules, opt-in ones included
fobis lint --select FOR002,OMP004,MPI005             # opt-in heuristics, one by one
```

- **Data sharing follows the Fortran rules.** Loop variables of the region's DO loops are private; `private`,
  `firstprivate`, `lastprivate`, `reduction`, `linear` and `threadprivate` are honoured; writes inside `critical`,
  `atomic`, `single`, `master`/`masked`, `ordered`, or guarded by `omp_get_thread_num() ==`, are not reported. A
  shared variable is reported once per region, at its first write; a variable assigned and then updated in one
  iteration is a shared temporary ([`OMP001`](/lint-rules/OMP001)), not a missing reduction
  ([`OMP002`](/lint-rules/OMP002)).
- **Regions stop at procedure boundaries.** A procedure called from a parallel region is checked for saved locals
  ([`FOR001`](/lint-rules/FOR001)), not for writes to the caller's shared variables. Procedures are matched across
  files by name, without following `use` renames.
- **Data flow is source order within one procedure**, loops not unrolled: [`OMP004`](/lint-rules/OMP004) (reads
  after `nowait`, up to the next barrier), [`MPI002`](/lint-rules/MPI002)/[`MPI003`](/lint-rules/MPI003) (a request
  is pending from its non-blocking call to the next statement using the request; whole-array buffers only: with
  `buf(k)` the message covers part of `buf`), [`ACC009`](/lint-rules/ACC009) (updates in the same procedure).
- **Rank branches.** [`MPI004`](/lint-rules/MPI004)/[`MPI005`](/lint-rules/MPI005) know a branch is rank-dependent
  when its condition uses a variable that `mpi_comm_rank` fills somewhere (`myrank`, `self%rank`). A construct whose
  branches call the same collectives in the same order is not reported.
- **Kinds** are resolved through the integer constants of the linted sources (`R8P = selected_real_kind(15, 307)`,
  `rk = real64`, `kind(1.d0)`); a kind module outside them is unknown, except PENF's `R4P`/`R8P`/`R16P`.
  [`FOR007`](/lint-rules/FOR007) reports only literals a single-precision real cannot represent (`0.1`, not `0.5`).
- **GPU code is not CPU code:** [`FOR002`](/lint-rules/FOR002) (loop order) skips OpenACC compute regions, OpenMP
  `target` regions, device routines and CUDA Fortran `device` arrays, where the parallel index leads on purpose.
- **Opt-in**, because they are heuristics or matter in some codes only: `FOR002`, `FOR003`, `NUM001`, `OMP004`,
  `OMP006`, `ACC007`, `ACC009`, `ACC010`, `MPI005`, `MPI006`. Select them when reviewing parallel code.

## Adopt the linter on old code

The first run on a large code reports hundreds of findings. Record them as the accepted state; from then on only new
findings are reported, and the linter can run in CI today:

```bash
fobis lint --update-baseline    # record the current findings; commit .fobis-lint-baseline.json
fobis lint                      # only findings not in the baseline
```

<<< @/examples/output/4-quality/02/baseline.txt{console}

<<< @/examples/output/4-quality/02/clean.txt{console}

- **A finding is recorded by rule, file and the normalised text of its statement**, not by line: code added above
  it does not bring it back; editing the statement, or renaming the file, does.
- **Counts matter.** Each record hides one occurrence: a second identical statement in the same file is a new
  finding.
- **`--update-baseline` records what the current selection reports, and overwrites the file.** Run it with the
  selection the CI uses (the `[lint]` section), and again after fixing findings, to shrink the file.
- **The file:** `--baseline FILE`, else `baseline` in `[lint]`, else `.fobis-lint-baseline.json`, read only when it
  exists (paths relative to the current directory).
- **`fobis review` uses no baseline:** it reports the changed lines only, so an old code stays quiet without one.

Tutorial: [suppressions, baselines and fixes](/tutorial/quality/02-fixes).

## Silence one finding, with a reason

When a finding is wrong for a reason the linter cannot see, say so in the code, on the reported statement (any of
its lines) or alone on the line before it:

```fortran
use mpi ! fobis: ignore[COR040] the mpi module's names are all prefixed mpi_

! fobis: ignore[COR011, COR010] C interface: the buffer size is passed separately
subroutine fill(buf, n) bind(c)
```

<<< @/examples/output/4-quality/02/lint.txt{console}

The linter checks its own suppressions: one without a reason is [`LNT001`](/lint-rules/LNT001), one that silences
nothing is [`LNT002`](/lint-rules/LNT002) (it would hide a future finding on that line), a misspelled rule id is
[`LNT003`](/lint-rules/LNT003). A suppression of a rule that is not selected is not reported as unused.

## Fix what can be fixed automatically

Five rules carry a mechanical fix:

| Rule | Rewrite |
|------|---------|
| [`MDN011`](/lint-rules/MDN011) | `(/ ... /)` -> `[ ... ]` |
| [`MDN021`](/lint-rules/MDN021) | `.eq.` `.ne.` `.lt.` `.le.` `.gt.` `.ge.` -> `==` `/=` `<` `<=` `>` `>=` |
| [`OBS005`](/lint-rules/OBS005) | specific intrinsics -> generic (`dsqrt` -> `sqrt`, `alog` -> `log`, `dmax1` -> `max`, `float` -> `real`, `idint` -> `int` ...); not `amax0`, `amin0`, `max1`, `min1`, which convert the result's type |
| [`OBS008`](/lint-rules/OBS008) | `character*n`, `character*(*)` -> `character(len=n)`, `character(len=*)` |
| [`OBS011`](/lint-rules/OBS011) | `do 10 ...` / `10 continue` -> `do ...` / `end do`, only when that loop alone ends on a `continue` and nothing (`go to`, arithmetic `if`, `err=`/`end=`/`eor=`, `assign`, alternate return) refers to the label |

```bash
fobis lint --select OBS005,OBS011,MDN021 --diff   # a unified diff; nothing changes
fobis lint --select OBS005,OBS011,MDN021 --fix    # rewrite the files, then report what remains
```

<<< @/examples/output/4-quality/02/diff.txt{console}

- **Code only.** Comments and character literals are left alone; the case of the code is kept (`DSQRT` -> `SQRT`,
  `END DO`); fixed form works, with `end do` at the column of its `do`.
- **Only the reported findings are fixed:** the selection applies, and suppressed or baselined findings are not
  touched. When two edits overlap, the second is skipped: run `fobis lint` again after `--fix`.
- **`--diff` exits 0**; `--fix` exits as a lint run on what remains.
- **A fix that compiles can still change results.** To keep the fixes only when the tests and cases agree, see
  [Modernise legacy code, verified](#modernise-legacy-code-verified).

## Lint in CI

```bash
fobis lint --format github                          # annotations on the pull request's lines
fobis lint --format sarif --exit-zero > lint.sarif  # GitHub code scanning, IDE viewers
fobis lint --format json                            # scripts
```

<<< @/examples/output/4-quality/01/github.txt{console}

```yaml
- run: pip install FoBiS.py
- run: fobis lint --format github
# or: findings tracked across commits in the repository's Security tab
- run: fobis lint --format sarif --exit-zero > fobis-lint.sarif
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: fobis-lint.sarif
```

- **`json`** holds `files`, `baselined`, `unreadable` and the findings (rule, name, severity, path, line, end_line,
  message, fingerprint).
- **`sarif`** is SARIF 2.1.0; each result carries the line-independent fingerprint, so code scanning follows a
  finding across commits, and each rule links its page of the rule reference.
- **`github`** maps the severities to `error`, `warning` and `notice`.

More in [Continuous integration](./ci).

## Compiler feedback

The compiler knows what the source does not show: which arrays an OpenACC region copies at every launch, which device
loop it ran sequentially, which OpenMP target maps it generated, which loops it did not vectorise.
`--compiler-feedback` reads its optimisation report from a build log and reports it on your source lines, next to
the other rules:

```bash
# 1. a build with the report flags, apart from your build tree (one job: messages must not interleave)
fobis build --mode nv --cflags "-Minfo=accel,mp" --build-dir .fobis/feedback -j 1 --force-compile \
  2>&1 | tee build.log
# 2. lint with the report, in the same mode
fobis lint --mode nv --compiler-feedback build.log
```

On the genuine nvfortran 26.5 log of FoBiS's test fixture (`tests/compiler-feedback/`):

```console
$ fobis lint --mode nv --compiler-feedback build.log
src/kernels.f90:1: COR050 [warning] module 'k' has no default accessibility statement
src/kernels.f90:9: ACC001 [warning] implicit data movement for the compute region: copyin(x(:n)), copy(y(:n))
src/kernels.f90:18: ACC001 [warning] implicit data movement for the compute region: copyout(y(2:n)), copyin(y(:n))
src/kernels.f90:19: ACC012 [warning] loop runs sequentially on the device: loop-carried dependence of y
src/kernels.f90:29: OMP008 [warning] implicit map(tofrom:y(:)) for the target region
src/kernels.f90:31: OMP001 [warning] 't' is shared and written by every thread (missing private?)

6 finding(s) in 2 file(s): ACC001 x2, ACC012 x1, COR050 x1, OMP001 x1, OMP008 x1
Compiler feedback: 18 message(s) read
Explain a rule with: fobis lint --explain <ID>
```

| Compiler | Report flags | Rules fed |
|----------|--------------|-----------|
| nvfortran | `-Minfo=accel,mp` | [`ACC001`](/lint-rules/ACC001) implicit data movement, [`ACC012`](/lint-rules/ACC012) sequential device loop, [`OMP008`](/lint-rules/OMP008) implicit target map |
| gfortran | `-fopt-info-vec-missed` | [`PRF001`](/lint-rules/PRF001) loop not vectorized (opt-in, severity info: `--select PRF001`) |

- **FoBiS does not run the feedback build.** When the log is missing, `fobis lint` exits 1 and prints the command
  for the mode's compiler, as above. An explicit `--build-dir` wins over the mode's `build_dir`, so the feedback
  objects stay out of your build tree.
- **Attribution, never a guess.** nvfortran names procedures, not files: a message is attributed through the
  project's procedures (a name defined in several files through the log's `Compiling ...` lines); what cannot be
  attributed is counted in the summary.
- **The findings describe the build of the log:** lint with the same `--mode`. `-` reads the log from standard
  input. `fobis review` takes `--compiler-feedback` too.

## Ask a model about the findings

The rules say "this pattern is here", not "this is a bug in your code". `--deep` asks a language model to judge each
finding against its code, with citations; `--ask` answers a question about the code at a line:

```bash
fobis lint src/solver --select OMP,ACC,MPI --deep        # a cited verdict per finding, region by region
fobis lint --deep --deep-max 25                          # more regions (default 10)
fobis lint --deep-context                                # print the model's input, run no model
fobis lint src/flux.F90:120 --ask "is this region race-free?"
```

Nothing is hidden: a dismissed finding is still printed, with the model's reason, and still counts in the exit
status. The verdicts annotate the `text` and `json` formats. Setting up a model, and how far to trust a 7B model's
verdicts, in [AI assistance](./ai).

## Review only what changed

`fobis review` lints the whole project (the cross-file rules need every file) with the same mode, `[lint]` section,
rules and `--compiler-feedback` as `fobis lint`, then keeps the findings whose lines touch an added or modified line.
A legacy code with hundreds of findings stays quiet, and a new finding shows the moment it is introduced.

```bash
fobis review                                   # HEAD against the working tree: staged and unstaged changes
fobis review --staged                          # the index against HEAD: a pre-commit hook
fobis review --base origin/master              # the commits since the merge base: a pull request
fobis review --base origin/master --worktree   # the merge base against the working tree
fobis review --context 3                       # also findings up to 3 lines away from a changed line
```

A change that moves the number of intervals into a variable:

<<< @/examples/output/4-quality/03/diff.txt{console}

<<< @/examples/output/4-quality/03/review.txt{console}

The fix is `!$omp parallel do private(n)`; then:

<<< @/examples/output/4-quality/03/fixed.txt{console}

- **A changed directive counts its whole region as changed.** Removing `private(flux) reduction(+:total)` changes
  one line, yet the race on `flux` and the unprotected sum on `total` are on the lines below: the OpenMP/OpenACC
  region of a changed directive is reviewed as a whole.
- **New files count:** without `--staged` or `--base`, a file git does not track yet (and does not ignore) is reviewed
  as wholly added. `--staged` reviews only what is staged.
- **Line numbers.** With `--staged` or `--base` the reviewed side is the index or `HEAD`, while the linter reads the
  files on disk: a reviewed file with other uncommitted changes gets a warning, its lines may not match.
- **Exit status 1** when a warning or error is on the changed lines, a file cannot be read, the directory is not a
  git repository or the base is unknown; `--exit-zero` reports only.
- **What it cannot see:** a finding caused by the change but located elsewhere (a caller of a procedure whose
  interface changed, a module variable now shared). Lint the whole code from time to time, or widen with
  `--context`.
- **Fortran sources only**; other changed files reach the `--deep` summary only.

Tutorial: [reviewing a change](/tutorial/quality/03-review).

## Review in a pre-commit hook and in pull requests

A pre-commit hook runs the rules only, no model: it takes as long as `fobis lint` on the project. With
[pre-commit](https://pre-commit.com), in `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: fobis-review
        name: fobis review
        entry: fobis review --staged
        language: system
        pass_filenames: false
        files: '\.(f|F|for|f90|F90|f95|f03|f08)$'
```

Or a plain `.git/hooks/pre-commit`, executable:

```bash
#!/bin/sh
exec fobis review --staged
```

For a pull request, the findings as a comment:

<<< @/examples/output/4-quality/03/markdown.txt{console}

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0          # the merge base must be in the clone
- run: pip install FoBiS.py
- name: Review the change
  run: |
    fobis review --base origin/${{ github.base_ref }} --format github
    fobis review --base origin/${{ github.base_ref }} --format markdown --exit-zero >> "$GITHUB_STEP_SUMMARY"
```

The first command annotates the changed lines and fails the job on a finding; the second writes the report to the
job summary. Formats: `text`, `markdown`, `github`, `sarif`, `json` (the findings plus `changed_lines`).
`fobis gate --base REF` runs this review with `--worktree` among its stages: see [Verifying results](./verification).

## A risk summary of the change

`--deep` adds a summary written by a language model from facts: the diff of each changed Fortran file, the changed
code in context, the OpenMP/OpenACC regions the change touches, the files that `use` a module whose procedure headers
changed, the findings on the changed lines and their rules. The answer is cited claims of two kinds, **risks** and
**to check**; a claim citing nothing is dropped.

![fobis review and fobis review --deep on an OpenMP change, with coder-7b](/gifs/14_llm_review.gif)

*coder-7b on an NVIDIA A30 of a cluster node, reached through ssh; recorded in real time.*

```bash
fobis review --deep                                      # findings, then the risk summary
fobis review --deep-context                              # the model's input; no model runs
fobis review --base origin/master --deep --format markdown
```

The summary adds to the `text`, `markdown` and `json` formats (`risk` in JSON); with `github` or `sarif` it is
skipped with a warning. It never changes the exit status, and an unavailable model leaves the review without it.
Models and their limits: [AI assistance](./ai).

## Who calls a procedure, who writes a variable

`fobis query` answers from the same analysis, not from a text search: a call on a continuation line, a statement
after a `;`, a module variable renamed on `use`, a type-bound call on an array element are found; comments, strings
and inactive preprocessor branches are not.

```bash
fobis query callers simpson              # call sites: call, function references, obj%run(), objs(i)%run()
fobis query callees solver::step         # what it calls, and how each name was resolved
fobis query uses quad_rules              # the units using a module, with their only-lists
fobis query writers solver::residual     # assignments, read, allocate, intent(out/inout) actual arguments
fobis query readers residual             # every other mention, intent(in/inout) actual arguments
fobis query defines integrand            # modules, procedures, generics, types, bindings, variables, parameters
fobis query interface trapezoid          # header and dummies; a generic's specifics; the types binding a name
fobis query region src/sweep.F90:17      # the directive regions holding the line, with their clauses
fobis query device rho                   # data directives naming it, compute constructs using it unnamed
fobis query mpi collective               # MPI calls: point-to-point, collective, one-sided, io, setup
```

<<< @/examples/output/4-quality/04/callers.txt{console}

<<< @/examples/output/4-quality/04/interface.txt{console}

<<< @/examples/output/4-quality/04/writers.txt{console}

<<< @/examples/output/4-quality/04/region.txt{console}

<<< @/examples/output/4-quality/04/mpi.txt{console}

How a call is resolved, the `how` of each result: `contained` (a procedure of the caller or of its hosts), `generic`
(every specific of the generic: the compiler chooses by argument types; a generic overloading an intrinsic lists the
intrinsic too), `binding` (every procedure bound to that name in any type: the dynamic type decides), `unique` (the
only project procedure of that name), `ambiguous` (several), `unresolved` (nothing in the analysed sources: a library,
a dependency, an intrinsic). Callers reached through a generic or a binding with several procedures are marked
*candidate*.

- **Qualified names:** `module::procedure`, `module::host::internal`. `writers module::VAR` keeps only the sites where
  the name is that module's variable, through host association, `use` or a rename (`use m, only: local => var`); each
  site says what the name is there (local, dummy with its intent, host, module variable, use).
- **Not followed:** generics on argument types and bindings on the dynamic type (those give candidates), pointer
  aliasing, argument association (a variable written through a dummy of another name), components (`obj%field` is
  not a variable for `writers`/`readers`). A name re-exported through a chain of modules is attributed to the module
  the unit uses; a statement only the preprocessor completes is seen as written.
- **An unknown name** gives no result and a note; an unknown query kind or a malformed argument exits 2.
- **Checked against a large code:** on a private 251-file MPI + OpenACC application (2.1 s to analyse), 34 queries
  were compared with `grep` and, where they disagreed, by reading the code; every disagreement was a site `grep`
  missed or misplaced (a call on a continuation line, a `use ::` form, an assignment after a `;`), none a wrong
  answer. On StringiFor (150 files), `callers split` finds 36 call sites, three on a subscripted object
  (`call rows(r)%split(...)`).

`--json` gives `kind`, `argument`, `items`, `notes` and `files`, for scripts and agents. Tutorial:
[querying the code](/tutorial/quality/04-query).

## Modernise legacy code, verified

A mechanical fix is only as good as the evidence that it changes nothing. `fobis modernize` applies the five fixable
rules of [the table above](#fix-what-can-be-fixed-automatically) in a scratch copy, and keeps them only when the
build, the tests and the declared cases say nothing moved:

```bash
fobis modernize                      # find, apply in a scratch copy, verify, report; writes nothing
fobis modernize --apply              # ... and write the verified fixes into the working tree
fobis modernize --select OBS011      # some rules only
fobis modernize --mode debug --keep  # the mode built and tested; keep the scratch copies
```

<<< @/examples/output/4-quality/05/modernize.txt{console}

<<< @/examples/output/4-quality/05/apply.txt{console}

How it decides:

1. **Two copies.** The working tree (tracked and untracked files, git-ignored ones left out) and the fetched
   dependencies are copied into a scratch directory twice: an untouched copy and a fixed one.
2. **The evidence.** The fixed copy must build (when the untouched copy builds: a build failing in both is
   "fails as in the untouched copy", evidence of nothing); the tests passing on the untouched copy (`fobis test` in
   the mode) must still pass; every [case](./verification) must give equivalent quantities, with the case's tolerance
   (exact by default). A case already failing on the untouched copy is not used, and the report says so.
3. **Rule by rule.** When the whole set fails, each rule is checked alone, and the rules that pass are still
   verified.
4. **Writing.** `--apply` writes the verified rules' fixes, only into files unchanged since the analysis.

- **Evidence is named:** `tests`, `cases`, `tests+cases`, or `build`. A build alone does not show unchanged
  behaviour: `--apply` then writes nothing (a note says so, exit 1) unless `--unverified` is given. No evidence at all
  fails the check. A file edited during the check is not written either (exit 1).
- **`--select` a rule with no automatic fix** is an error (exit 2) that lists the fixable ones.
- **Suppressions are honoured**, so `! fobis: ignore[OBS011] reason` keeps a loop as it is; the `[lint]` section and
  the baseline are not used: every fixable finding of the mode's sources is a candidate.
- **Exit status:** 0 when every rule is verified or nothing needs fixing, 1 when a rule is not verified, 2 for an
  unknown rule or a bad case declaration. `--json` gives `status` (`verified`, `partial`, `failed`, `nothing`),
  `fixes` per rule, `checks`, `verified`, `applied`, `notes`.

**Measured on FFTPACK in FORTRAN 77** (59 fixed-form sources, 13 test programs, a fobos from `fobis fpm import`, one
case: the 133 error norms printed by `tstfft`, compared exactly):

```text
fixes found:
  MDN021: 127 edit(s) in 45 file(s)
  OBS005: 20 edit(s) in 1 file(s)
  OBS011: 542 edit(s) in 39 file(s)
check [MDN021, OBS005, OBS011]: PASS (evidence: tests+cases)
    build: fails as in the untouched copy: fftpack::rfft_rk is referenced (referenced from MAIN__) but not linked
    tests: ok
    cases: equivalent
verified: MDN021, OBS005, OBS011
```

`--apply` rewrote 46 files and the 13 tests pass on them. The verification earned its place there: a first version of
the `OBS011` fix put `end do` at the indentation of a labelled `  103 DO 104` line, column 6 in fixed form, the
continuation column; `dzfftf.f` stopped compiling, the check failed on the tests, and the other rules were verified
alone.

The edits that need judgement (implicit typing, COMMON to modules, arithmetic IF) follow the same loop, by hand or
by an agent: each change checked with `fobis diff-run` and `fobis gate`, in [Verifying results](./verification).
Tutorial: [verified modernisation](/tutorial/quality/05-modernize).

## Call Fortran from C or Python

Most Fortran procedures take kinds like `real(R8P)`, assumed-shape arrays and generic names, and have no `bind(c)`
interface. `fobis bindings` writes it from the analysis of the modules, without touching them:

```bash
fobis bindings                                # every module of the mode's sources, into bindings/
fobis bindings quad_rules gauss_legendre
fobis bindings m_morton -o c --name morton    # into ./c, as morton_c.f90, morton.h, morton.py
fobis bindings --print                        # what would be bound and why the rest is not; write nothing
```

<<< @/examples/output/4-quality/06/bindings.txt{console}

Three files, named after `--name`, else the fobos `[project] name`, else the current directory (lowercase, `-` as
`_`):

::: code-group

<<< @/examples/output/4-quality/06/shim.txt{console} [quad_c.f90]

<<< @/examples/output/4-quality/06/header.txt{console} [quad.h]

:::

`NAME_c.f90` is a module of `bind(c)` shims named `<module>_<procedure>`; `NAME.h` the C prototypes (`stdint.h`,
`stdbool.h` types), each with the Fortran signature it calls; `NAME.py` a `ctypes` wrapper: `load(path)`, then one
function per procedure taking numbers and lists, returning the result and the `intent(out)`/`inout` arguments.
Build the shim with the modules into a shared library, a mode like the tutorial's `python`:

```ini
[python]
help      = The C and Python bindings, a shared library
template  = template-gnu
cflags    = -c -O2 -fPIC
src       = ./src/ ./bindings/
build_dir = ./build/python/
target    = bindings/quad_c.f90
mklib     = shared
output    = libquad_c.so
```

<<< @/examples/output/4-quality/06/build.txt{console}

<<< @/examples/tutorial/4-quality/06-bindings/files/gauss.py{python}

<<< @/examples/output/4-quality/06/python.txt{console}

- **C types from what the kind resolves to,** not from its name: `selected_int_kind(15)` is `int64_t`,
  `selected_real_kind(15, 307)` (PENF's `R8P`) is `double`; `iso_fortran_env` and `iso_c_binding` names and literal
  kinds too. Default `integer`, `real` and `logical` are `int32_t`, `float` and `bool`, as gfortran, ifx and nvfortran
  use them without `-i8`/`-r8`.
- **Explicit conversions.** The shim copies every value into a temporary declared with the procedure's own type spec
  (`x_f = real(x, R8P)`) and back for `intent(out)`/`inout` and results, and repeats the module's `use` statements,
  which give the kinds. A dummy without `intent` is treated as `inout`.
- **Arrays:** an assumed-shape `v(:)` gets an extent argument per dimension; explicit-shape arrays keep their extents
  (literals, or other dummies); a function returning an array of literal shape returns it through an output
  argument. Arrays are contiguous and column-major; Python passes and returns flat lists in Fortran order, and an
  output array is passed too: its length sizes the buffer.
- **Generics:** the specifics of a public generic are bound one by one; a private specific is called through its
  generic, which resolves to it because the temporaries have the specific's types.
- **Not bound, with the reason in the report:** character, complex, derived-type and procedure arguments; optional,
  allocatable and pointer dummies; assumed-size and assumed-rank arrays, bounds that are not literal extents,
  extents that are expressions; kinds with no portable C type (quad precision) or that cannot be resolved; array
  results without a literal shape, allocatable or pointer results; procedures already `bind(c)`.
- **Files:** nothing is written when nothing can be bound; existing files are kept (exit 2) unless `--force`; an
  unknown module, or sources without a module, exit 2. `--json` lists each procedure (`module`, `procedure`,
  `c_name`, `kind`, `skipped`) and the files written.

Measured: m_morton (8 public procedures: fixed-shape arguments, array results, `selected_int_kind(15)`) bound
entirely, built with gfortran and called from gcc and Python with the same results; PENF (170 public procedures and
specifics) bound 15 and reported the rest (98 with allocatable arguments, 35 character, 17 optional, 5 the 33-digit
`R16P`). Tutorial: [C and Python bindings](/tutorial/quality/06-bindings).

## For CI and agents

`fobis lint --format json`, `fobis review --format json`, `fobis query --json`, `fobis modernize --json` and
`fobis bindings --json` print one JSON document on standard output. The MCP server (`fobis mcp`) exposes `lint`
(with a fix diff), `review`, `query`, `bindings` (the plan, read-only) and `modernize` (never applies) as tools, and
the rules as resources. Briefing an agent on the project (`fobis agents-md`): [AI setup](./ai-setup).
