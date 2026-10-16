---
title: AI assistance
---

# AI assistance

FoBiS knows every source file of the project, the module graph, the build modes with their compiler, flags and `-D`
defines, and the git history. The AI commands put that knowledge in front of a language model run on your machine:
why a build failed, why a program crashed, what a procedure does, a test for a module, a second reading of lint
findings or of a change, a commit message, a resolution of a merge conflict. The model is always the last step, and
nothing it says is written anywhere without you.

How it works:

1. **Facts first.** A deterministic step does what it can before any model runs: a missing module, an unlinked
   object, a located crash, the findings of the rules, the scopes the history uses, the merge hunks that need no
   judgement. Often that is the whole answer, and no model is started.
2. **A context you can read.** What the model sees is assembled by FoBiS, not searched for by the model: the error
   and the code around it, the declarations and interfaces it names, the build mode and its flags, a few sections of
   the knowledge packs. The same inputs give the same context, and every command prints it without running a model.
3. **Cited claims, checked.** The answer is a JSON object of claims, each citing the numbered sources (`S1`,
   `S2`, ...) of the context. The schema lists the labels as an enumeration, so a model run with a grammar cannot
   invent one; FoBiS still checks every citation and drops the claims citing nothing it gave.
4. **Outputs that can be checked are checked.** A generated test is kept only when it builds, runs and checks
   something; a merge proposal is compiled; a lint verdict without a citation becomes `uncertain`; a commit scope
   must be one the facts allow. The exit status of `lint` and `review` never depends on a model.
5. **Local, explicit, bounded.** The default model runs on your machine (a pinned llama.cpp build and pinned
   models); nothing is downloaded unless you ask. Every answer has bounded lengths and a token cap. Nothing is
   written to your files or to git without `--apply`, and merges and commits ask first.

Tutorial: [AI-assisted development](/tutorial/ai/01-model). Reference: [`build`](/reference/build),
[`run`](/reference/run), [`test`](/reference/test), [`ask`](/reference/ask), [`testgen`](/reference/testgen),
[`lint`](/reference/lint), [`review`](/reference/review), [`commit`](/reference/commit),
[`merge-assist`](/reference/merge-assist), [`ecosystem`](/reference/ecosystem).

## Set up a local model

```bash
fobis llm runtime install     # once: the pinned llama.cpp build (CUDA, Metal or CPU, detected)
fobis llm pull coder-7b       # once: 4.7 GB, the default model
```

Every command of this page then starts the model when it needs it and stops it at the end. Other models, Ollama or
an OpenAI-compatible server, a persistent server for many commands, a cluster without internet, the knowledge
packs, the MCP server for agents: [Setting up the AI](./ai-setup).

## Why the build failed

```bash
fobis build --explain                    # facts first, then the model for what they do not cover
fobis build --mode debug --explain
fobis build --explain-context            # print what the model would receive; no model
```

The compiler output is printed as usual, then the explanation; the exit status is still 1. Most failures need no
model. A misspelt module name:

<<< @/examples/output/6-ai/02/missing.txt{console}

FoBiS parses the messages of gfortran, ifx/ifort, nvfortran, LFortran, GNU ld and lld, scans the project, and looks
at what the build compiled and linked:

- **A missing module:** which file defines it and why this build does not compile it (outside `src`, listed in
  `exclude` or `exclude_dirs`), a definition hidden by a preprocessor branch the mode's `-D` flags disable, a fetched
  dependency defining it, a declared dependency not fetched yet, a library module (`mpi`, `mpi_f08`, `omp_lib`,
  `openacc`, `cudafor`, `hdf5`, `netcdf`) with the flag it needs, or a close name of an existing module.
- **An undefined reference:** the symbol demangled (gfortran `__mod_MOD_proc`, ifx `mod_mp_proc_`, nvfortran
  `mod_proc_`), where it is defined, and why its object is not linked: not compiled, in a file the program never
  reaches, a dependency not linked, a library (MPI, OpenMP, OpenACC, HDF5, netCDF, BLAS/LAPACK) missing from the
  link flags, no main program.
- **Objects of another compiler:** runtime symbols (`_gfortran_*`, `for_*`, `pgf90_*`) of a compiler other than
  the mode's, left by another mode.
- **A multiple definition** (the files defining the symbol, or two main programs), **an internal compiler error**
  (a compiler defect, with the usual workarounds).

Errors that follow from an explained one are counted, not explained again. Two more real outputs:

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

For the first error no fact covers (a type mismatch, a syntax error, a constraint), the model gets the compiler's
message, the build (compiler, mode, flags), the lines around the error with the error line marked `>`, the
declarations of the enclosing procedure, the interfaces of the project procedures named on the line, and at most
two knowledge-pack sections that match the message well enough. It answers claims of two kinds, cause and fix:

::: details The model's input (`fobis build --explain-context`)
<<< @/examples/output/6-ai/02/context.txt{console}
:::

<<< @/examples/output/6-ai/02/explain.measured.txt{console}

![fobis build --explain and fobis ask with coder-7b, run locally on the CPU](/gifs/13_llm_explain.gif)

*coder-7b on 6 CPU cores and no GPU; each answer takes about 45 s there, cut from the recording.*

- **Only the first unexplained error goes to the model**, then `(N more error(s) not explained: fix this one
  first, then rebuild)`: later errors often follow from it.
- **The fix is a suggestion, not compiled.** Read it before applying it: on the `fobis new` demo, coder-7b on the
  CPU proposed `1.0` for a `real64` argument.
- **A C source's error is not explained:** FoBiS says so and stops (the prompt and the packs are Fortran's).
- **Pack retrieval matches the words of the message**, which share few with the standard: often no section
  qualifies, and the answer rests on the code facts alone.
- **The scan runs only after a failure** and takes a few seconds on large trees (about 5 s for 850 files).
- **`--json` wins:** with it the output is the JSON report, which carries the same diagnoses; `--explain` is ignored.
- **No model configured:** the facts are still printed, and FoBiS says why no model explanation follows.

Tutorial: [build failures, explained](/tutorial/ai/02-explain).

## Why the program crashed

```bash
fobis run --explain                  # build (with --explain), run, explain a failure
fobis run --mode debug --explain
fobis test --explain                 # every failed test
```

The program's standard error is printed as it runs and recorded; the exit status is the program's. On a failure,
FoBiS reads the runtime message (gfortran, Intel, nvfortran), the backtrace and the exit status:

<<< @/examples/output/6-ai/03/crash.txt{console}

- **An out-of-bounds access:** the array, the index and the bound, the statement, the declaration; for a dummy
  argument, the caller that passes it.
- **An unassociated pointer:** Intel's message, or the bounds of an empty pointer (`1:0`, `0:-1`) that gfortran and
  nvfortran print.
- **`error stop`:** the statement that printed the message, found by its text (Intel prints only the message).
- **Known compiler bugs:** gfortran `-O2`+ EFAULT (`errno=14`) on pointer sections passed to explicit-lower-bound
  dummies; nvfortran CUDA error 719 on an OpenACC reduction into a `declare create` module allocatable, with the
  matching reductions of the project.
- **No location at all:** in a debug build, how to get one with a debugger.

**An optimised build's backtrace is not trusted.** The frames of an `-O2`/`-O3` build are often mis-resolved, so
FoBiS uses a location only when the runtime message gives it (gfortran and nvfortran print the failing line even at
`-O3`) or when the build is unoptimised with `-g`. Otherwise it names the mode to rerun in (unoptimised, `-g`, the
same compiler preferred), or the flags to add when there is none:

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

In a debug build the same defect is located:

```text
Explanation (fobis run --explain)
index 11 of array a is above its upper bound 10 at src/kernels.f90:18
  - runtime message: Index '11' of dimension 1 of array 'a' above upper bound of 10
  - statement: a(i) = 0.5 * (a(i) + a(i + 1))
  - declaration: real, intent(inout) :: a(:) (src/kernels.f90:14)
  - a is a dummy argument of smooth: the caller passes it, called from src/bounds.f90:6.
```

The model is asked only when the location is trusted and the facts leave something to explain. It gets the
runtime output, the build (flags, optimisation, debug information, checks), the code around the failing line and
around its caller, and their declarations, and answers cited cause and fix claims.

- **`test --explain` asks the model once:** every failed test gets its facts, the model only the first failure the
  facts leave open. A test whose build failed is explained by the build, not here.
- **Rebuild under checks without a debug mode:** `fobis run --shadow checks --explain` (see [Testing](./testing)).

Tutorial: [crashes, located](/tutorial/ai/03-crash).

## Ask about the code and the standards

```bash
fobis ask "why does my MPI code hang when every rank sends first?"
fobis ask -p src -p test "which rule integrates cubic polynomials exactly?"   # the project's units too
fobis ask --pack openmp "is a loop variable private in a parallel do?"       # one pack only
fobis ask --show-context -p src "..."                                         # the model's input; no model
echo "..." | fobis ask -                                                      # the question from standard input
```

The answer is drawn from the knowledge packs shipped with FoBiS (the Fortran standard, OpenMP, OpenACC, MPI, HPC
practice, compilers, libraries, numerics) and, with `-p DIR`, from the project's own units: each module, procedure
and program described by its header, its documentation comment, its arguments, the modules it uses, its calls, its
MPI calls and directives, its location:

::: details The model's input (`fobis ask --show-context`)
<<< @/examples/output/6-ai/04/context.txt{console}
:::

<<< @/examples/output/6-ai/04/ask.measured.txt{console}

A real answer of coder-7b on an NVIDIA A30, from the MPI pack, in 3.4 s with the server running:

```text
- MPI code hangs when every rank sends first because mutual send-before-recv in standard mode can deadlock (buffering not guaranteed). Use `MPI_Sendrecv` or nonblocking communication instead. [1][2]
- Relying on standard-mode buffering for correctness is not guaranteed; a program that 'works' may deadlock at larger message sizes. [3]

Sources:
  [1] Cheatsheet — MPI 5.0 > Decision rules > Avoid deadlock - MPI 5.0: distilled reference  (mpi:cheatsheet#avoid-deadlock)
  [2] Chapter 3: Point-to-Point Communication > Code Examples - MPI 5.0: distilled reference  (mpi:ch03-point-to-point#code-examples)
  [3] Chapter 3: Point-to-Point Communication > Anti-patterns - MPI 5.0: distilled reference  (mpi:ch03-point-to-point#anti-patterns)
```

Read a cited section in full with `fobis kb show <id>`.

- **Routing.** A question naming a programming model (`omp`, `!$acc`, `MPI_Isend`), a compiler (`ifx`,
  `nvfortran`), a library or launcher (`hdf5`, `mpirun`) or a numerical-assessment topic (significant digits,
  Richardson, tolerance, benchmark) searches that pack plus the Fortran standard, HPC practice and the project, so
  OpenMP and OpenACC sections do not compete on the words they share. `--pack` replaces the routing.
- **Retrieval is lexical: words, not meanings.** The OpenMP pack says "loop iteration variables are private"; a
  question about "the index of a sequential loop" does not reach it among the first sections. Rephrase with the
  standard's terms, raise `-k` (6 sections by default), or look first with `fobis kb search`.
- **Document your procedures.** A FORD `!<` comment after the header, or a Doxygen `!>` before it, becomes the
  unit's `doc:` line, which the model may cite. The answer above comes from one.
- **No match, no model:** when retrieval finds nothing, `ask` says so and exits 1. When the model's claims do not
  survive the check, the answer is "The sources found do not answer this question." `--verbose` prints the dropped
  statements.
- **A citation proves the source exists, not that it says what the claim says.** Asked how long `simpson` takes on
  a GPU, coder-7b answered three statements, each citing something real, none answering the question:

<<< @/examples/output/6-ai/04/beyond.measured.txt{console}

Tutorial: [questions about the code](/tutorial/ai/04-ask).

## Generate tests

```bash
fobis testgen gauss_legendre --skeleton          # no model: the compile-checked skeleton
fobis testgen gauss_legendre                     # a model fills it; printed if accepted
fobis testgen gauss_legendre --apply             # ... and written to test/test_gauss_legendre.f90
fobis testgen penf_b_size -p byte_size --max 4   # one generic, at most 4 procedures
fobis testgen gauss_legendre --context           # the model's input; no model
```

The skeleton comes from facts: one test subroutine per public procedure (each specific of a public generic, called
through the generic; each public binding of a public non-abstract type, called as `obj%binding(...)`), a local
variable for each dummy argument, and a call with keyword arguments. FoBiS builds it with your mode in a scratch copy
of the project and drops a subroutine that does not compile, with the compiler's message as the reason:

<<< @/examples/output/6-ai/05/skeleton.txt{console}

With the model, the skeleton, the public API, the code of the tested procedures (80 lines each at most) and an
existing test of the project (for its style) go to the model. The program it returns is built and run in the
scratch copy, and **accepted** only when it exits 0 within the timeout (60 s, `--timeout`), uses the module, calls
one of its public procedures, and holds a check that can fail: `error stop`, a non-zero `stop`, or a failure
counter incremented. Otherwise the compiler's errors on the test's lines, the exit status and the output, or what is
missing, go back to the model, which is told never to remove a check to make a test pass: up to three more attempts
(`--retries`).

<<< @/examples/output/6-ai/05/testgen.measured.txt{console}

![fobis testgen writes a test for the tutorial's gauss_legendre module, then fobis test runs it](/gifs/15_llm_testgen.gif)

*coder-7b on an NVIDIA A30 of a cluster node, reached through ssh; recorded in real time. The test was accepted at
the first attempt.*

The values above are those of the 3-point Gauss-Legendre rule, checkable against any table. On PENF, with the
`-Werror` mode `tests-gnu`, coder-7b got `penf_b_size` accepted at the first attempt (20 s, 8 checks) and
`penf_stringify` at the second (53 s, through the generics `bcton` and `bstr`).

- **A passing test proves the code does what the model read in it, not that it is right.** For a procedure without
  a known answer the checks can only repeat the code. Review the test before committing it.
- **Your tree is never written** but by `--apply` (or `-o PATH`, which implies it), and never over an existing
  file. The scratch copy holds the working copy (ignored files excluded) and the fetched dependencies, and is
  deleted at the end.
- **The test directory must be among the mode's sources** for `fobis test` to build the written test.
- **FoBiS fixes two mistakes itself:** lines longer than 132 columns are continued before building, and a compile
  failure's feedback names the public generic of each private specific the program calls.
- **Not tested:** procedures in submodules, operators and assignments, `class(*)` and assumed-rank arguments,
  procedure arguments. `--max` (8 with the model, all with `--skeleton`) keeps the input small: test a large module a
  few procedures at a time with `-p`.
- **Small models fail here.** coder-0.5b: four attempts, nothing accepted (it broke a string literal and could not
  fix it from the message); coder-1.5b on the CPU: three attempts in 450 s, nothing accepted.
- **Exit status:** 0 a program accepted (or the skeleton built), 1 none accepted, the project or the skeleton does not
  build, no model, or the output file exists; 2 module not found or nothing public to test.

Tutorial: [generated tests](/tutorial/ai/05-testgen).

## A second reader for lint findings

The rules say "this pattern is here", not "this is a bug in your code". `--deep` asks the model to judge each
finding in the code it is in, with citations, and to point out related problems the rules missed:

```bash
fobis lint src/solver --select OMP,ACC,MPI --deep        # the parallel findings
fobis lint --deep --deep-max 25                         # more groups (default 10)
fobis lint --deep-context                               # the model's input; no model
fobis lint src/flux.F90:120 --ask "is this region race-free?"
```

The findings are grouped by the innermost OpenMP/OpenACC region, else by the enclosing procedure (a window around
the findings when it is long); regions go first, then the most severe. The mechanical families (`OBS`, `MDN`, `PRT`,
`STY`, `LNT`) are not sent. One request per group carries the code with the finding lines marked, the declarations,
each rule's documentation and the pack sections it references, the compiler feedback for those lines (with
`--compiler-feedback`), the interfaces of the procedures called, and pack sections matching the directive's
clauses. A real answer of coder-7b on an NVIDIA A30, for a loop that lost its `private(flux) reduction(+:total)`:

```text
src/heat.f90:14: OMP001 [warning] 'flux' is shared and written by every thread (missing private?)
    [llm] confirmed: The variable 'flux' is shared and written by every thread, leading to a data race. [1][2]
src/heat.f90:16: OMP002 [warning] 'total' is accumulated by every thread: use reduction(+:total)
    [llm] confirmed: The variable 'total' is accumulated by every thread without using a reduction clause, leading to incorrect results. [1][3]
Sources cited by the review:
  [1] src/heat.f90 lines 12-17 (!$omp parallel do (line 12))  (code:src/heat.f90:12-17)
  [2] rule OMP001 shared-scalar-written-in-parallel-region  (rule:OMP001)
  [3] rule OMP002 accumulation-without-reduction  (rule:OMP002)
Review [llm]: 1 of 1 group(s); 2 confirmed, 0 dismissed, 0 uncertain. Dismissed findings are still reported and still count.
```

- **Nothing is hidden.** A dismissed finding is printed with the model's reason and still counts in the exit status.
  To silence a false positive, suppress it in the code with a reason (`! fobis: ignore[OMP001] ...`) or record it in
  the baseline: see [Code quality](./analysis).
- **Uncited verdicts are downgraded.** A confirmed or dismissed verdict citing nothing becomes `uncertain`, a finding
  the model skipped stays `uncertain`, an uncited concern is dropped.
- **A 7B model's verdict carries no information.** On a labelled set of 10 findings (7 real defects, 3 false alarms
  of the linter), coder-7b confirmed all 10, the false alarms included, restating the finding's message where the
  code contradicted it. Its value is the reasoning attached to the real ones; use a larger model when the verdicts
  matter.
- **One request per group, and groups are many:** 850 files of an HPC solver gave 580. Narrow with paths and
  `--select`, and raise `--deep-max` deliberately.
- **`--ask "QUESTION" FILE:LINE`** builds the same input for the region or procedure around that line, findings
  included, and answers cited claims as `fobis ask` does, without the lint report.
- **Formats:** text and json are annotated (`--format json` adds a `review` to each reviewed finding and a
  top-level `review`); the other formats are not, with a warning.

Tutorial: [a second reader](/tutorial/ai/06-review).

## A risk summary of a change

`fobis review` reports the lint findings on the changed lines (see [Code quality](./analysis)); `--deep` adds a
model's risk summary of the change:

```bash
fobis review --deep                       # every uncommitted change
fobis review --base origin/master --deep  # the commits of a branch
fobis review --deep-context               # the model's input; no model
```

The model gets the diff of each changed Fortran file (what was removed matters as much as what was added), the
changed code in context with the changed lines marked, the OpenMP/OpenACC regions the change touches, the files that
`use` a module whose procedure headers changed, and the findings on the changed lines with their rules'
documentation. It answers cited claims of two kinds, risks and things to check:

::: details The model's input (`fobis review --deep-context`)
<<< @/examples/output/6-ai/06/context.txt{console}
:::

<<< @/examples/output/6-ai/06/deep.measured.txt{console}

- **The findings and the exit status are the linter's.** The summary never removes a finding and never changes the
  exit status.
- **Formats:** the summary is added to text, markdown (a pull-request comment) and json (`risk`); other formats warn.
- **A 7B model repeats itself and skips the checks.** On a heat-equation change coder-7b gave three right risks, one
  of them twice, and no "to check" item.

## Commit messages

```bash
git add -p                    # one logical change staged
fobis commit --show-facts     # what FoBiS knows of the change; no model
fobis commit                  # print a message; nothing is committed
fobis commit --apply          # print it, ask, then git commit
```

Before the model, FoBiS computes facts of the staged change:

- **Scope candidates from the history:** for each staged file, the scopes of the last 300 commits that touched it;
  with fewer than 3, those of its nearest directory that has them (stopping below `src/` and the package), the file's
  own commits breaking the ties. A path new to the whole history is named after its directory under `src/`.
- **Fortran line kinds:** each removed or added line is code, an OpenMP or OpenACC directive, or a comment or blank,
  from the staged and the HEAD versions lexed by FoBiS; the procedures whose code changed and the changed procedure
  headers.
- **Type hints:** only documentation, tests, CI or build files; only directives (`perf(acc)`, and the model becomes
  the first scope candidate); only comments; a changed procedure header (breaking, if that API is published).

<<< @/examples/output/6-ai/07/facts.txt{console}

A directive-only change in an HPC code (a real output, names changed: OpenACC `async` added to one loop):

```text
## Facts of the change (computed by FoBiS from git and the sources)

Scope candidates (use one of these, or an empty scope for a cross-cutting change):
- acc: only these directives changed
- lib: 9 of 24 past commits touching src/lib/gpu/ used it
- gpu: 1 of 24 past commits touching src/lib/gpu/ used it; 1 of 2 past commits touching src/lib/gpu/gpu_ib_kernels.F90 used it
- lib/ib: 1 of 24 past commits touching src/lib/gpu/ used it; 1 of 2 past commits touching src/lib/gpu/gpu_ib_kernels.F90 used it
Type hint: perf(acc) (only OpenACC directive lines changed, no code)

Fortran sources (changed lines classified by the lexer; comment = comment or blank):
- src/lib/gpu/gpu_ib_kernels.F90: changed lines (removed + added): 2 acc
```

The model receives the complete file list (`git diff --cached --name-status`, never truncated), the stat, the staged
diff, the last 5 commits as a style reference, the branch and the facts. It answers a JSON object (type, scope,
breaking, description, body, footers) and FoBiS writes the `type(scope)!: description` header itself, with the scope
restricted to the candidates (kept as written, `solver/gpu` included) or empty:

<<< @/examples/output/6-ai/07/commit.measured.txt{console}

![fobis llm doctor and fobis commit with a local model](/gifs/12_llm_commit.gif)

The scope is right, the type is wrong: a program printing a new result is a `feat`. That is why `fobis commit`
commits nothing, and `--apply` asks `Commit with this message? [y/N]` before running `git commit`.

```ini
; the user configuration, ~/.config/fobis/config.ini
[llm]
; staged-diff characters sent to the model (default 12000)
max_diff_chars = 30000
; critique-and-rewrite passes after the draft (default 0)
refine_passes  = 1
```

- **A long diff is cut at file boundaries:** every file keeps its header, a cut hunk is marked
  `@@ [+N chars not shown] @@`, files with no room are listed by name; the file list still names them all.
  `--max-diff N` for one run.
- **`--refine-passes N`** (1 to 3) gives a small model a critique-and-rewrite pass on a shallow first draft.
- **A server that rejects the schema** (HTTP 400 or 422) gets the free-text request; the answer is cleaned
  (`<think>` blocks removed, a repeated message dropped) and wrapped at 72 columns.
- **`--no-facts`** leaves the scope free. `--show-facts --json` prints the facts as JSON and exits 1 when nothing is
  staged.
- **Another server for one run:** `--provider ollama|openai`, `--url`, `--model`, `--api-key-env NAME`; the key is
  read only from the variable you name, and a hosted endpoint receives your staged diff. More in
  [Setting up the AI](./ai-setup).

Tutorial: [commit messages](/tutorial/ai/07-commit).

## Merge conflicts

```bash
git merge feature                     # stops on conflicts
fobis merge-assist --no-model         # deterministic resolutions only
fobis merge-assist                    # a proposal per conflict, compiled before it is shown
fobis merge-assist --apply            # hunk by hunk: accept, ours, theirs, both, edit, skip, quit
fobis merge-assist --apply --yes      # only the safe ones; the rest stays in conflict
fobis merge-assist src/flux.F90       # only these conflicted files
fobis merge-assist --context          # the model's input; no model
```

The hunks come from the index, not from the file: base, ours and theirs are merged again with
`git merge-file --diff3`, whatever your `merge.conflictStyle` and even after you edited the file. The operation is
read from `MERGE_HEAD`, `REBASE_HEAD`, `CHERRY_PICK_HEAD` or `REVERT_HEAD`, and the sides are named as they are:
during a rebase "ours" is the upstream and "theirs" your commit being replayed. Deterministic rules come first:

- **High confidence:** one side equals the base (take the other); both sides made the same change, or differ in
  whitespace only; both changed a `use ..., only:` list (a three-way union: a name one side removed stays removed);
  both moved a `tag=` pin in the fobos `[dependencies]` (the higher version, flagged for review).
- **A draft, medium confidence:** one side only appended or prepended lines, the other only edited the base lines
  (both changes). Drafts go to the model and are never accepted by `--yes`.

<<< @/examples/output/6-ai/08/deterministic.txt{console}

The model gets the base, ours, theirs, the lines around the conflict, the commit messages of each side since the
merge base (their intent), the procedures at the conflict and the draft. It answers a strategy (`ours`, `theirs`,
`both`, `custom`), the text for `custom`, a rationale, a confidence, risks and citations; FoBiS builds the text of
the other strategies itself, rejects a `custom` text with conflict markers, and keeps an uncited proposal at
confidence low. The file, every proposal applied, is compiled syntax-only with the mode's compiler, `-D`/`-I` flags
and module directory; a proposal that does not compile goes back with the errors, twice at most, then is shown with
confidence low:

<<< @/examples/output/6-ai/08/merge.measured.txt{console}

![fobis merge-assist on a conflict over a tolerance: the rules find no safe answer, the model's proposal does not compile](/gifs/16_llm_merge.gif)

*coder-7b on an NVIDIA A30 of a cluster node, reached through ssh; recorded in real time. The proposal declares the
parameter twice: FoBiS compiles it, retries twice with the errors, then shows it marked `does NOT compile` with
confidence low. Nothing is written.*

The rationale describes the right resolution, the chosen strategy keeps both lines. The right answer here is an
edit (`e` under `--apply`): keep `4.e-14_R8P` and merge the comments.

- **FoBiS never touches the git state:** no `git add`, no `--continue`. After `--apply` the files are still
  unmerged: review them with `git diff`, run `fobis test`, then `git add` them yourself.
- **Your own edits are kept:** `--apply` writes only the conflict blocks still in the file and accepted by you.
- **`--yes` accepts** the high-confidence rules and the model's proposals that compile, nothing else. `--apply`
  without a terminal needs it (else exit 1).
- **Build once before merging.** When the modules the file uses are not built yet, the compile check is impossible,
  not failed: the proposal is shown as `not compiled`.
- **Semantic conflicts are not seen hunk by hunk.** The report ends with the procedures changed by both sides: test
  them. Binary files and modify/delete conflicts are not handled.
- **No model available:** a warning, and the deterministic resolutions only.
- **`--format json`** prints the report as one JSON object and asks nothing, so `--apply` needs `--yes` (else
  exit 2).

**What history says.** Replayed on historical merges: on fpm (last 60 merges, 32 hunks) the 6 high-confidence
resolutions all equalled the committed ones. On an HPC solver (26 hunks, 15 of them drafts of one pattern: an
`!$omp` directive added after an `!$acc` one on one side, a variable added to the `!$acc` clause on the other), the
human also added the variable to the new `!$omp` clause. Sent to coder-7b on an A30 (7.5 minutes), 3 of the 26
proposals equalled the human resolution, no draft was improved, 2 of 11 unresolved hunks were solved, and the model
rated all 26 proposals `high`, right or wrong: its confidence carries no information. Trust the rules and the
compile check; review every proposal.

Tutorial: [merge conflicts](/tutorial/ai/08-merge).

## The impact of a change on dependent projects

`fobis ecosystem impact` finds, in every project depending on a library, the places using what changed in its
public interface (see [Ecosystems](./ecosystem)). `--deep` adds a cited summary for the release train:

```bash
fobis ecosystem impact PENF --deep                 # what breaks, what to do
fobis ecosystem impact PENF --deep-context         # the model's input; no model
fobis ecosystem impact PENF --format markdown --deep
```

The model gets one source per API change (before and after) and one per place a dependent uses a changed name, and
answers claims of two kinds: what breaks (project, file, line) and what to do (which dependent to update, in which
order, whether the change deserves a major version). It is asked only when something breaking changed. The summary
is added to text, markdown and json, and the exit status stays the command's: 1 when a dependent is affected.

## What the model sees

Every command prints the model's input, system prompt included, without running a model:

```bash
fobis build --explain-context                # also: fobis run --explain-context, fobis test --explain-context
fobis ask --show-context -p src "..."        # --json: the retrieved sections only
fobis testgen MODULE --context
fobis lint --deep-context                    # with --ask too
fobis review --deep-context
fobis merge-assist --context                 # the hunks the rules do not settle
fobis ecosystem impact PROJECT --deep-context
fobis commit --show-facts                    # the facts added to the commit prompt
```

The same inputs give the same context. Read it when an answer surprises you: a wrong answer from a context missing
the relevant code is a retrieval problem, not a model problem. To give an AI agent these facts directly, without the
local model, use the MCP server: [Setting up the AI](./ai-setup).

## What to trust

- **Facts:** the diagnoses of `--explain`, the findings, the scope candidates, the deterministic merge resolutions,
  the compile checks. They are reproducible and can fail a CI job.
- **Checked outputs:** a test that `testgen` accepted builds, runs and checks something; a merge proposal marked as
  compiling compiles. Neither is proven right.
- **Claims:** advisory. A citation proves that the source exists and was given to the model, not that it supports
  the claim: read the cited source when the claim matters. The model's own confidence (merge) and verdicts (lint)
  carried no information in the measurements above.
- **The model matters.** coder-7b is the smallest that is useful; coder-0.5b and coder-1.5b failed every `testgen`
  attempt, and 1.5b gave a wrong `--explain` fix and invented "about 10 seconds on a GPU" for a question no source
  answered. A larger model through another provider is a configuration line ([Setting up the AI](./ai-setup)).
- **Speed:** about 45 s per answer for coder-7b on 6 CPU cores; seconds on an NVIDIA A30 (3.4 s for the `ask`
  answer above, 20 s for an accepted test). A persistent server saves the start-up of every command.
- **Overrides:** `ask` and `commit` take `--provider` and `--model`; the other commands use the user configuration.
