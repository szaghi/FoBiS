---
name: fobis
description: >
  Expert knowledge of FoBiS.py (Fortran Building System for poor men) — an automatic Fortran build tool that resolves module dependency hierarchies without manual makefiles. Use this skill whenever the user asks about: writing or editing a fobos file; running any fobis subcommand (build, clean, fetch, install, rule, doctests, scaffold, check, test, coverage, tree, introspect, run, cache, commit, ecosystem, lint, kb, mcp, llm); linting Fortran code (fobis lint: correctness, obsolescent features, OpenMP/OpenACC/MPI defects, compiler feedback, baselines, suppressions); the knowledge packs (fobis kb); the MCP server (fobis mcp); running local LLMs (fobis llm: runtime, models, serve, doctor); managing several interconnected FoBiS repositories as a whole (fobis ecosystem: registry, dashboard, cross-repo exec/fetch/check/scaffold, release train); Fortran project build configuration; diagnosing FoBiS build errors; adding GitHub dependencies to a Fortran project; the --json output flag; multi-mode builds; templates; variables and varsets; library builds (static/shared); MPI/OpenMP/coarray/OpenMP-offload builds; feature flags and conditional compilation; build profiles; the build cache; external-library auto-detection and pkg-config (.pc) generation; multi-target builds; convention-based source auto-discovery; the lock file and semver dependency constraints; the first-class test runner and coverage reports; LLM-assisted commit messages; the cflags-heritage feature; parallel compilation; or any question that mentions "fobos", "FoBiS", or building Fortran projects. When in doubt, trigger this skill — it is better to consult it unnecessarily than to miss it.
---

# FoBiS.py Expert Knowledge

FoBiS.py is a CLI tool that auto-builds modern Fortran projects by parsing source files and resolving inter-module dependency hierarchies. It eliminates manual makefile dependency tracking.

> **Currency:** This reflects FoBiS.py 3.8.x (16-subcommand Typer CLI). The canonical CLI binary is `fobis`; `FoBiS.py` remains a legacy alias. Flags use **double-dash long form** (`--mode`, `--ex`, `--ls`, `--lmodes`). Legacy single-dash multi-char forms (`-mode`, `-ex`) are auto-normalized but should not be written in new scripts/docs.

## Core Concept

FoBiS.py scans your source directories, parses every `.f90` (and related) file for `module`, `use`, and `include` statements, builds a dependency graph, and compiles in the correct order. The only file you need is `fobos` — the project configuration file (INI format, auto-loaded from the current directory).

---

## CLI Commands

20 subcommands, grouped by purpose. Every command except `commit`, `kb`, `mcp`, `llm` and the
`cache`/`scaffold`/`ecosystem` sub-apps accepts `--fobos`/`-f <path>` (non-default fobos file) and `--mode <name>` (select a build mode).

### Build & run

```bash
fobis build              # compile and link (the default workhorse)
fobis run [TARGET] [-- ARGS...]   # build if needed, then execute (passthrough args after --)
fobis test [-- ARGS...]  # discover, build, run Fortran test programs (passthrough)
fobis coverage           # generate coverage reports from instrumented runs
fobis check              # validate the dependency graph without building
```

- `build`: every compiler/dir/file/preproc option plus profiles, features, varsets, cache,
  multi-target, hooks, externals — see the fobos option table below. Supports `--json`.
- `run`: positional `TARGET` optional (defaults to the mode's output). `--no-build`, `--dry-run`,
  `--example NAME`. Args after `--` are forwarded to the executed binary.
- `test`: `--suite NAME`, `--filter GLOB`, `--timeout SEC` (default 60), `--no-build`, `--list`,
  `--coverage`. Args after `--` forwarded to test binaries.
- `coverage`: `--format html|xml|text|all` (repeatable, default html), `--output-dir`,
  `--source-dir`, `--exclude GLOB`, `--fail-under N`, `--tool gcovr|lcov`.
- `check`: `--strict` (warnings → errors, exit 1), `--varset`, `--src`.

### Project

```bash
fobis fetch              # clone + build GitHub deps from the [dependencies] section
fobis install [REPO]     # install built local files, or clone+build+install a GitHub repo
fobis introspect         # emit machine-readable project metadata (JSON/TOML)
fobis tree               # print the resolved inter-project dependency tree
fobis cache <list|clean|show>   # manage the build-artifact cache
```

- `fetch`: `--deps-dir`, `--update`, `--no-build`, `--frozen` (enforce lockfile), `--no-cache`.
  Supports `--json`.
- `install`: positional `REPO` (`user/repo` or full URL) optional. Local mode (no REPO) installs
  previously built artifacts to `--prefix/-p` (default `./`) under `--bin`/`--lib`/`--include`.
  GitHub mode: `--branch`, `--tag`, `--rev`, `--update`, `--no-build`, `--deps-dir` (default `~/.fobis/`).
- `introspect`: `--sources`, `--compiler`, `--dependencies`, `--targets`, `--include-dirs`,
  `--buildoptions`, `--projectinfo`, `--varsets`, `--all`, `--write` (to `.fobis-info/`),
  `--format json|toml`, `--varset`.
- `tree`: `--depth/-d N`, `--no-dedupe`.
- `cache list` (`--cache-dir`); `cache clean --older-than N` (`--cache-dir`); `cache show DEP_NAME`
  (positional required, `--cache-dir`).

### Utilities

```bash
fobis clean              # remove compiled objects/mods (use carefully)
fobis rule --ex <name>   # run a custom shell rule from fobos (and intrinsic rules)
fobis doctests           # build & run inline Fortran doctests
fobis scaffold <status|sync|init|list>   # manage project boilerplate from bundled templates
fobis commit             # generate a Conventional-Commits message via a local LLM
```

- `clean`: `--only-obj` and `--only-target` (mutually exclusive). Supports `--json`.
- `rule`: `--ex/--execute NAME`, `--ls/--list`, plus intrinsic rules: `--get KEY`,
  `--get-output-name`, `--ford project.md`, `--gcov-analyzer DIR [SUMMARY]`,
  `--is-ascii-kind-supported`, `--is-ucs4-kind-supported`, `--is-float128-kind-supported`.
- `doctests`: `--keep-volatile-doctests`, `--exclude-from-doctests`, `--doctests-preprocessor cpp|fpp`.
- `scaffold`: subcommands `status` (`--strict` for CI), `sync` (`--dry-run`, `--yes/-y`),
  `init` (`--yes/-y`), `list`. All take `--fobos/-f`; `status`/`sync` take `--files GLOB`.
  Manages four artifact categories — verbatim (SHA-256 synced), templated (`{{VAR}}`-rendered;
  reads the optional fobos `[scaffold]` section, e.g. `apt_packages`), init-only (created once,
  project-owned, e.g. `docs/guide/contributing.md`), and symlink (`CONTRIBUTING.md` → the
  canonical contributing page; never written through). Fobos `[scaffold] skip = <globs>` marks
  managed files the project owns (e.g. a customised `scripts/release.sh`): reported `SKIPPED`, not
  drift, never written. A confirmation that cannot be answered (no tty) means *no*; `--yes` is the
  unattended path (and makes `init` prompt for nothing).
- `commit`: `--provider/--backend/-b managed|ollama|openai`, `--url/-u`, `--model/-m`, `--api-key-env`,
  `--max-diff`, `--refine-passes`, `--apply` (runs `git commit`), `--config/-c`, `--show-config`,
  `--init-config`. **No `--fobos`/`--mode`.**

### Analysis & AI

```bash
fobis lint [PATHS]       # rule-based checks: correctness, obsolescent, OpenMP/OpenACC/MPI defects
fobis kb search "QUERY"  # search the knowledge packs (Fortran/OpenMP/OpenACC/MPI standards, HPC practice, compilers, MPI/HDF5, numerical assessment)
fobis mcp                # MCP server (stdio): 27 annotated tools (lint, review, kb, build/test with diagnoses, merge, ecosystem ...)
fobis llm <...>          # local LLM harness: runtime install, pull models, serve, ask, doctor
fobis review [--staged | --base REF]  # lint findings on the changed lines only (pre-commit, PR); --deep risk summary
fobis merge-assist [--apply [--yes]]  # proposals for merge/rebase/cherry-pick conflicts, compiled; never stages
fobis testgen MODULE [--skeleton] [--apply]  # test program for a module's public API, kept only if it builds+runs+checks
fobis case list|run [NAME] [--json]  # run fobos [case:NAME] programs, extract their quantities (+ provenance)
fobis provenance [--json]            # commit/dirty, dep pins, compiler+version+flags, modules, machine
fobis verify [NAME] [--update] [--repeat N]  # case quantities vs stored references, per-quantity tolerance
fobis build|test|run|verify --shadow checks  # the mode rebuilt with runtime checks (or sanitize, strict) in .fobis/shadow/
fobis matrix [--modes] [--shadows] [--verify] [--recheck]  # every mode x shadow built/tested; cross-cell disagreements
fobis assess CASE [--families precision,rounding,compiler,parallel,inputs,refinement] [--jobs N]  # error/uncertainty
fobis diff-run [REF] [CASE...] [--assess] [--keep]  # cases on a revision vs the working tree (scratch copies)
fobis bench [CASE...] [--compare REF [--feedback]] [--record] [--runs N]  # run time with a 95% interval of the median
fobis gate [--base REF] [--stage S] [--skip S] [--advisory S] [--fail-fast]  # one verdict: every check, first failing fact
fobis verify|test|case run|assess|bench|diff-run --runner slurm  # runs as Slurm jobs ([scheduler]), builds stay local
fobis profile CASE [--tool gprof|callgrind] [--top N]  # time/instructions mapped to procedures and source lines
fobis fpm import|export [--print] [--force]  # fpm.toml <-> fobos (notes for what does not translate)
fobis bindings [MODULE...] [-o DIR] [--print]  # bind(c) shims + C header + Python ctypes wrapper
fobis modernize [--select RULES] [--apply] [--unverified]  # lint fixes kept only if build, tests, cases agree
fobis query callers|callees|uses|writers|readers|defines|region|device|mpi|interface ARG  # code graph answers
fobis agents-md [-o CLAUDE.md] [--check] [--print]  # AGENTS.md block of facts (modes, commands, cases, kinds)
fobis ask "QUESTION"     # answer from the knowledge packs (+ project procedures with -p DIR), with citations
fobis build --explain    # on failure: explain from facts (missing module, unlinked object ...), then LLM
fobis run --explain      # runtime crash: located facts, debug mode to use, known compiler bugs, then LLM
fobis test --explain     # the same for every failed test (LLM for the first one)
```

- `lint`: honours `--fobos`/`--mode` (sources, exclusions, `-D` defines of the mode) and the fobos
  `[lint]` section (`select`, `ignore`, `baseline`). `--select/--ignore` ids or prefixes (`COR`, `OMP`,
  `ALL`; explicit selection enables opt-in rules), `--format text|json|sarif|github`, `--baseline FILE`,
  `--update-baseline`, `--compiler-feedback LOG` (nvfortran `-Minfo`, gfortran `-fopt-info` logs, produced
  by the user's own build), `--diff`/`--fix` (mechanical fixes), `--exit-zero`, `--list-rules`,
  `--explain ID`. Families: COR, OBS, MDN, PRT, STY, FOR, NUM, OMP, ACC, MPI, PRF, LNT. Suppress one
  finding with `! fobis: ignore[ID] reason` (a reason is required). Rule pages: `/lint-rules/`.
- `kb`: `list`, `search QUERY [-k N] [--pack P] [--json]`, `show ID [-C N]`, `notice PACK`,
  `build SOURCES --name N`, `add DIR`, `remove NAME` (`--project` for `.fobis/kb`). Shipped packs are
  CC-BY-4.0.
- `mcp`: `--root DIR`. Register in Claude Code with `claude mcp add fobis -- fobis mcp`. Tools (read-only): lint
  (+ `fix_diff`), review, list_rules, explain_rule, kb_search, kb_show, ask_context (retrieved sources, NO answer),
  introspect, check, tree, merge_conflicts, commit_facts, testgen_skeleton, ecosystem_status, ecosystem_impact,
  case_list, provenance, query, agents_md; writing: build, test, case_run, verify, matrix, assess, diff_run, bench, gate (`shadow` on build/test/case_run/verify),
  clean (destructive), fetch (network). Annotations (readOnly/destructive/idempotent/
  openWorld), JSON as text + `structuredContent` (2025-06-18), a failed build/test is a result (status error), not
  a tool error; lint/review trimmed to `max_findings` (200). Resources `fobis://rules/{id}`, template
  `fobis://kb/{id}` (URL-encoded id). By design no local-LLM answer is exposed: the client is the model.
- `case`: fobos `[case:NAME]`: `target` (built with the case's `mode`) or `command`, `args`, `inputs` (copied
  into a fresh `.fobis/runs/<case>/<variant>/`), `ranks` (`[verification] launcher`, `{ranks}`), `threads`,
  `timeout`, `env`, `quantities` (`name : regex stdout PAT [last]` | `column FILE N` | `json FILE $.k` | `hdf5
  FILE /ds` | `binary FILE real64 [n] record 2|stream` | `exit`, or `stdout` alone). Status ok/probe-error/
  failed/timeout/build-failed/error; exit 1 when a run is not ok, 2 on a bad declaration. Base of the coming
  `verify`/`assess`/`diff-run`/`bench` (PLAN-verification.md).
- `verify`: references `verification/references/<case>.json` written ONLY by `--update` (commit them); case key
  `tolerance = q: abs A rel R | ulp N | exact; *: ...` (default exact); report per quantity: out-of-tolerance count,
  max abs/rel, L2, worst point `(i,j)` (Fortran binary) or `[i][j]`, NaN appeared, provenance changes (also on
  pass: "results unaffected"). `--repeat N`: runs must agree exactly (non-determinism). Case builds force a full
  recompile when the compiler/version/flags changed or another build touched the objects (`rebuilt_because`).
- `--shadow NAME` (build, run, test, case run, verify, introspect): the mode's settings with checking flags,
  objects in `.fobis/shadow/<mode>-<shadow>/` (never the mode's build_dir). `checks` (-O0 -g, bounds/pointer
  checks, FP traps invalid/zero/overflow, snan init), `sanitize` (ASan; gfortran + UBSan; not nvfortran, not
  ifort), `strict` (f2018 conformance, warnings as errors), `none` (own flags, own dir). Optimisation/fast-math
  flags of the mode are dropped. Families gnu (+opencoarrays), intel (ifort, ifx), nvfortran (+pgi).
- `matrix`: cells = modes x shadows (default `none,checks`), each built from scratch in its shadow dir, in the env
  of fobos `[verification] setup = NAME: bash commands` (NAME = mode, compiler or family; e.g. `nvfortran: source
  /usr/share/lmod/lmod/init/bash; module load nvhpc/26`). Steps: build, `fobis test` (when tests exist), with
  `--verify` the cases (vs references + cross-cell disagreements beyond tolerance); `--recheck` reruns failures
  under `checks`. Compiler missing -> skipped; shadow lacking -> n/a. Exit 1 on a failed cell or disagreement.
- `assess`: ensembles of a case's variants, declared in `[assess:CASE]` (families, precision/rounding `NAME: flags`,
  modes, threads/ranks/repeats, inputs `NAME: namelist FILE VAR|keyvalue FILE KEY|regex FILE 'P(x)'|arg N|env V` +
  `rel EPS|uniform A B|normal MU SIGMA`, `refine = NAME: TARGET values V1 V2 V3 [inverse]` coarse to fine, samples,
  seed, `budget = q: digits|order|error >= v`). Reports digits vs promoted precision, significant digits across
  rounding/compiler variants (95% bound), non-determinism at repeated thread counts, elasticities / MC correlations,
  observed order + Richardson + GCI + asymptotic range. Variant objects in `.fobis/variant/`; inputs edited in run
  dirs only. Exit 1 on a failed budget.
- `diff-run`: REF (default HEAD) extracted with `git archive` (+ submodules at recorded commits), working tree
  copied, working deps copied into both; cases from the working fobos run on both; quantities compared with the
  case tolerance (verify comparator: worst index); changed files + procedures listed; `--assess` judges a
  difference against the worktree's own digits (within-uncertainty). Never writes the tree or repo metadata.
  Exit 1 when a case differs or fails.
- `modernize`: fixes MDN011/MDN021/OBS005/OBS008/OBS011 applied in a scratch copy, compared with an untouched copy
  (build when the base builds, tests passing before, cases equivalent); each rule alone when the set fails;
  `--apply` writes verified rules into unchanged files; build-only evidence needs `--unverified`.
- `bindings`: shims convert explicitly (int/real/logical(x, K)) into temporaries of the procedure's own types, C types
  from what kinds resolve to (selected_int_kind/selected_real_kind/iso_* names); assumed-shape arrays get extent
  args; private generic specifics are called through the generic. Not bound (reason reported): character, complex,
  derived types, optional/allocatable/pointer, assumed size/rank, quad precision, non-literal array results.
- `fpm import`: fpm.toml -> fobos (debug/release modes from FoBiS build profiles, lib mode when a module is named
  after the package, git deps, path deps into src, mpi/openmp metapackages -> mode keys). `fpm export`: library
  source-dir from where the modules are, [[test]]/[[executable]] from the programs, git deps, macros. No overwrite
  without --force.
- `profile`: gprof (case rebuilt with -pg as a variant; sampled self time + exact calls; MPI ranks -> per-process
  totals + imbalance max/mean; sub-sample runs measure no time, said so) or callgrind (valgrind; instructions per
  function AND source line: inlined procedures found through their lines; routines outside the sources (malloc,
  runtime) listed with the project procedures calling them). GPU profilers not yet.
- `--runner slurm`: `[scheduler]` (user config, then fobos): kind slurm, partition, account, qos, options (#SBATCH
  lines), launcher (default srun), setup (shell lines in the job), poll, login_nodes (patterns). Case ranks/threads/
  gpus/timeout -> --ntasks/--cpus-per-task/--gpus/--time. The job records its own exit status and time; provenance
  `scheduler` (job, state, node). On a login node, MPI/GPU cases are refused locally. Run dirs must be shared.
- `gate`: stages build, review, test, verify, diff-run, bench, assess, matrix (nested `fobis --json` commands), each
  pass/fail/error/skipped with the FIRST failing fact; skipped with the reason when not applicable (no tests, no
  cases, no change against HEAD, no `[bench:]`, no budget, no `[gate] matrix_modes`). Without `--base`: working tree
  vs HEAD; `--base REF`: merge base vs working tree (review `--base MB --worktree`). `[gate]` stages/skip/advisory/
  base/mode/matrix_modes/matrix_shadows. Build failure skips the stages that need it. Exit 1 on a blocking failure.
- `bench`: `[bench:CASE]` warmup/min_runs/max_runs/target (relative half-width of the median's 95% interval,
  distribution-free)/max_time/time (wall or a quantity)/work. Runs interleaved across sides; faster/slower ONLY when
  the intervals do not overlap (else "no measurable difference"). History `verification/bench/<case>.jsonl` only
  with `--record`, compared on the same CPU/GPU models/compiler version/mode. `--compare REF --feedback`: per
  procedure counts of vectorised / not vectorised loops, implicit device copies per variable, sequential device
  loops (gfortran -fopt-info, nvfortran -Minfo); regressions located. Notes: short runs (< 10 ms), busy machine,
  GPU wall timing, GeForce FP64. Exit 1 when measurably slower.
- `query`: static analysis of the mode's sources (lint engine, `-D` defines): calls resolved contained > generic
  (candidates, + intrinsic overloaded) > unique > ambiguous > unresolved; bindings by name (candidates);
  writers/readers with intents of actual arguments and use renames (`module::var`); region FILE:LINE; device VAR
  (named data clauses + implicit use in offload regions); mpi by kind; interface signature. Not resolved:
  argument types, dynamic types, aliasing, components.
- `agents-md`: block between `<!-- fobis:begin agents-md -->`/`<!-- fobis:end agents-md -->` (rest of the file
  kept; appended to a file without one): modes (compiler, builds, -O/debug/checks, parallel, defines), setup lines,
  commands, cases (tolerance, reference present, assess budgets), code facts of the mode's sources (kinds as written
  with origin/digits, units without implicit none, include files excluded, OpenMP/OpenACC/MPI, doctests). Only the
  fobos + git-tracked files (no machine state, deps dir excluded): `--check` (exit 1 stale/no-block/missing, diff)
  is CI-stable.
- **Machine output** (`--json` / `--format json`): build (on failure + `diagnostics` parsed + `diagnoses` from
  facts), clean, fetch, check, tree (each dep with ITS version), test (per test status passed/failed/build-failed/
  timeout/error + `crash`/`notes` or `diagnostics`/`diagnoses`), introspect, lint/review, merge-assist, testgen,
  `commit --show-facts --json`, `ask --show-context --json`, ecosystem dashboard/impact. With machine output all
  FoBiS messages and warnings go to stderr: stdout is the JSON document only.
- `llm`: `recommended`, `pull MODEL`, `list [--json]`, `rm MODEL`; `runtime install [--variant V]
  [--build bN --sha256 H|--trust]`, `runtime list`, `runtime remove NAME`; `serve start [--model M]|stop|
  status`; `ask PROMPT [--schema F] [--system S]`; `doctor [--no-sample]`. Nothing is downloaded implicitly.
- `ask`: `-p DIR` (repeatable), `--pack P`, `-k N`, `--show-context` (print the model's input, run no model),
  `--verbose` (show dropped uncited claims), `--json`, `--provider`, `--model`. Claims that cite no source
  are dropped; retrieval is lexical (rephrase with the standard's terms when nothing is found).
- `build --explain`: after a failed build, deterministic diagnoses with no model: missing module (defined
  where, excluded by `exclude`/`exclude_dirs`/outside `src`, disabled by a `#ifdef`, fetched dependency,
  library module needing `--mpi`/`--openmp`, dependency not fetched), undefined reference (demangled; the
  defining file and why it is not linked, incl. "file holds a module the program never uses"), objects of
  another compiler (stale `obj_dir`), multiple definition, internal compiler error. The first error left
  (syntax, type mismatch ...) goes to the LLM as cited `cause`/`fix` claims; `--explain-context` prints its
  input instead. Exit status stays 1.
- `review`: lints the whole project (mode, rules, `[lint]` as `lint`), reports only findings touching changed
  lines (default: uncommitted; `--staged`; `--base origin/master` = since the merge base); a changed OpenMP/OpenACC
  directive counts its whole region; `--context N`; formats text/markdown (PR comment)/json/sarif/github;
  `--deep` cited risks/to-check from the diff, touched regions, users of modules whose headers changed;
  `--deep-context`; exit 1 on error/warning findings unless `--exit-zero`. Pre-commit: `fobis review --staged`.
- `ecosystem impact PROJECT [--base REF] [--format text|markdown|json] [--deep]`: public API diff of PROJECT's
  Fortran modules (procedure signatures, generics, types, variables, constants; access lists; re-exports through
  facade modules) between REF (default latest tag) and the working tree, then the references to changed names in
  every (transitive) dependent's OWN files (git ls-files: no fetched deps, no submodules). Plain `use` without a
  reference = not affected. Exit 1 when a dependent is affected. Complements `ecosystem check` (builds).
- `merge-assist`: hunks from the index stages (`git merge-file --diff3`); rules (one side == base, same change or
  whitespace, `use only` three-way union, fobos `tag=` pins -> higher version) at high confidence; adjacent edits
  (one side appended, other edited) -> medium draft the LLM refines; LLM per remaining hunk (strategy
  ours/theirs/both/custom, citations, intent = commit messages of each side; rebase sides named correctly);
  syntax-only compile with the mode's compiler, <= 2 retries; `--apply` asks a/o/t/b/e/s/q and edits only the
  blocks still in the file; `--yes` = high-confidence rules + compiling proposals; NEVER git add/--continue.
  `scripts/merge_replay.py CLONE` measures the rules on historical merges.
- `testgen MODULE`: cases = public procedures, specifics of public generics (called through the generic), public
  type-bound procedures of public non-abstract types (`obj%binding`). Skeleton from facts (locals mirror the dummies:
  intent/optional/value dropped, non-constant shapes/lengths -> allocatable deferred, `character(*), allocatable`
  -> len=256, `class(t)` -> `type(t)`; `class(*)`/assumed-rank/procedure args skipped), built with `fobis build
  --target` in a SCRATCH COPY (working copy + fetched deps copied; nothing of the user's tree written); a case that
  does not compile is dropped with the compiler message. `--skeleton` = no model. The LLM completes it; build + run
  + inspect (uses the module, calls a public name, >= 1 check: `error stop`/non-zero stop/failure counter++);
  errors, failing run output or "checks nothing" sent back, `--retries` (3). `--apply` writes
  `<[test] test_dir>/test_<module>.f90`, never over an existing file. `--max` (8 with the model), `-p NAME`,
  `--context`, `--format json` (progress on stderr). The program is placed in the mode's sources in the copy: a
  `--target` outside the sources is silently not built.
- `commit`: the scope comes from facts (`--show-facts` prints them, no model; `--no-facts` disables): the
  scopes past commits used for the staged files (or their directory), restricted in the structured answer;
  only `!$acc`/`!$omp` lines changed -> `perf(acc|omp)`; Fortran lines classified code/directive/comment.
- `lint --deep` (+ `--deep-max N` default 10, `--deep-context`): LLM review grouped by OpenMP/OpenACC region
  (else procedure); verdict per finding confirmed/dismissed/uncertain with citations, plus advisory concerns
  `[llm]`; mechanical families (OBS, MDN, PRT, STY, LNT) not sent; uncited verdict -> uncertain; dismissed
  findings still printed and still count in the exit status. Narrow with paths + `--select OMP,ACC,MPI`.
  `lint FILE:LINE --ask "question"`: cited answer about the region around that line.
- `run --explain` / `test --explain`: stderr is echoed and recorded; the runtime message (gfortran, Intel
  `forrtl`, nvfortran `0:`), backtrace and exit signal are parsed. Facts: out-of-bounds (array, index, bound,
  statement, declaration, caller of a dummy), unassociated pointer, `error stop` traced to its statement by
  text, known compiler bugs (gfortran -O2+ EFAULT; nvfortran CUDA 719 reduction into `declare create`).
  **Optimised-build backtraces lie**: frames of an optimised/no-`-g` build are never used; FoBiS names the
  fobos debug mode to rerun with (`fobis run --mode <debug> --explain`). The LLM is asked only when the location
  is trusted (runtime message line, or debug-build frame), with the failing line and its caller.

### Cross-cutting facts

- **`--json`** exists on `build`, `clean`, `fetch`, and on `ecosystem dashboard`/`ecosystem graph`.
  (`introspect`/`coverage` use `--format` instead.)
- **Passthrough** (forward extra args after `--`): `run`, `test`, and `ecosystem exec`.
- **Global:** `--version`/`-v`.

---

## fobos File Format

INI-format, auto-loaded from the current directory.

### Single-mode (simplest)

```ini
[default]
compiler  = gnu
cflags    = -c -O2
src       = ./src/
build_dir = ./build/
obj_dir   = ./obj/
mod_dir   = ./mod/
target    = src/main.f90
output    = myapp
```

The section **must** be named `[default]`.

### Multi-mode

```ini
[modes]
modes = debug release

[debug]
compiler  = gnu
cflags    = -c -O0 -g -Wall
build_dir = ./build/debug/
src       = ./src/
target    = src/main.f90
output    = myapp

[release]
compiler  = gnu
cflags    = -c -O3 -march=native
build_dir = ./build/release/
src       = ./src/
target    = src/main.f90
output    = myapp
```

Select a mode: `fobis build --mode release`. List modes: `fobis build --lmodes`. The first listed
mode is used when `--mode` is omitted.

### Templates (DRY across modes)

```ini
[modes]
modes = debug release

[template-common]
compiler  = gnu
src       = ./src/
target    = src/main.f90
output    = myapp

[debug]
template  = template-common
cflags    = -c -O0 -g -Wall
build_dir = ./build/debug/

[release]
template  = template-common
cflags    = -c -O3
build_dir = ./build/release/
```

- Mode options override template options.
- Multiple templates: `template = template-gnu template-mpi` (left wins).
- Templates can chain; circular references are an error.

### Variables (`$`) and varsets

Any `$NAME = value` in any section (except `[varset:*]`) joins a **global** pool and is substituted
into the active mode's values. No recursion. A `[vars]` section is just a conventional home — it is
not special-cased; the `$`-prefix rule is what matters.

```ini
[vars]
$SRC    = ./src/
$HDF5   = /opt/hdf5

[debug]
src    = $SRC
cflags = -c -I$HDF5/include
```

**Varsets** are *named, selectable* bundles. Unlike plain `$vars`, a `[varset:NAME]` block is applied
only when chosen — via `--varset name1,name2` (last write wins) or a `[varsets] default = ...`
fallback. Introspect with `fobis introspect --varsets`.

```ini
[varset:local]
$HDF5 = /usr/local/hdf5
[varset:cluster]
$HDF5 = /apps/hdf5/1.14
```
`fobis build --varset cluster`

### Rules (custom tasks)

```ini
[rule-makedoc]
help  = Build documentation
quiet = True
rule  = ford doc/ford.md

[rule-maketar]
help    = Create archive
rule_rm = rm -f project.tar
rule_mk = tar cf project.tar src/ fobos
```

Run: `fobis rule --ex makedoc`. List: `fobis rule --ls`. Use unique keys starting with `rule`
(e.g. `rule`, `rule_rm`, `rule1`) for multiple commands in one rule.

---

## Key fobos Options Reference

These are *mode* keys (valid in `[default]` or any `[mode-X]`). A mode recognizes any key whose name
matches a `build`-command option (underscored form).

| Option | Description |
|---|---|
| `compiler` | `gnu`, `intel`, `intel_nextgen`, `g95`, `opencoarrays-gnu`, `pgi`, `ibm`, `nag`, `nvfortran`, `amd`, `lfortran`, `custom` |
| `fc` | Fortran compiler executable (for `compiler = custom`) |
| `modsw` | Module-path compiler switch (for `compiler = custom`, e.g. `-J`, `-module`) |
| `cflags` / `lflags` | Compile / link flags (fobos + CLI are concatenated) |
| `preproc` | Preprocessor macro flags (e.g. `-DDEBUG`) |
| `src` | Source root directory/directories (space-separated) |
| `build_dir` / `obj_dir` / `mod_dir` | Output / object / `.mod` directories |
| `lib_dir` / `include` | Library / include search directories |
| `target` / `output` | Build target source file / output name |
| `exclude` / `exclude_dirs` | Files / directories to exclude from the build |
| `libs` / `vlibs` | Local library files (full paths) / volatile (md5-tracked, rebuild on change) |
| `ext_libs` / `ext_vlibs` | External libs by name (`-l`) / volatile by name |
| `dependon` | Interdependent fobos projects (`path/fobos[:mode]`) |
| `mklib` | Build a library: `static` or `shared` |
| `ar` / `arflags` / `ranlib` | Archiver / flags (`-rcs`) / ranlib (empty string = skip) |
| `mpi` / `openmp` / `openmp_offload` / `coarray` | Enable MPI wrapper / OpenMP / OpenMP offload / coarrays |
| `coverage` / `profile` | Coverage instrumentation / profiling instrumentation |
| `jobs` | Parallel compile jobs |
| `cflags_heritage` | Persist cflags; force full rebuild when they change |
| `track_build` | Record built artifacts for `install` |
| `build_profile` | Named flag preset: `debug`, `release`, `asan`, `coverage` |
| `features` / `no_default_features` | Activate feature flags / suppress `[features] default` |
| `varset` | Apply named `[varset:NAME]` bindings |
| `externals` | Space-separated external library names to auto-resolve (from `[externals]`) |
| `pkgconfig`, `pkgconfig_name`, `pkgconfig_desc`, `pkgconfig_url`, `pkgconfig_req`, `pkgconfig_req_priv` | Generate a `.pc` file |
| `target_filter` / `examples` | Multi-target build controls |
| `pre_build` / `post_build` | Rule names to run before / after the build |
| `no_auto_discover` | Disable convention-based source-dir discovery |
| `no_cache` / `cache_dir` | Disable the build cache / override its directory |

---

## Feature Areas

### Build profiles

Built-in compiler-flag presets, selected with `build_profile = NAME` (fobos) or `--build-profile NAME`
(CLI). Profiles: `debug`, `release`, `asan`, `coverage`. Tuned per compiler (gnu, intel, intel_nextgen,
nvfortran, nag, amd, lfortran); unknown compiler falls back to the gnu preset with a warning. Profile
flags are prepended so your explicit `cflags` win. `fobis build --list-profiles` prints the full table.

### Feature flags (conditional compilation)

```ini
[features]
default = prod                 ; reserved key: the default feature set
hdf5    = -DUSE_HDF5            ; leaf feature → flags
prod    = -DNDEBUG @hdf5        ; @hdf5 composes another feature (recursive, cycle-safe)

[feature:gpu]                  ; Tier-2 block with constraints
flags     = -DUSE_GPU
requires  = openmp_offload     ; auto-pulls prerequisites
conflicts = debug              ; hard error if both active

[feature-group:precision]      ; mutual exclusivity
members = single double
default = double               ; with default → exactly-one; without → at-most-one
```

Resolution order: `[features] default` (unless `--no-default-features`) → mode `features = ...` →
CLI `--features 'prod,-coverage'` (a `-name` token deactivates). Well-known *implicit* features need
no `[features]` section and just flip the matching bool: `openmp`/`omp`, `mpi`, `coarray`, `coverage`,
`profile`, `openmp_offload`/`omp_offload`. Active set is reported in `introspect`.

### External libraries & pkg-config

Declare in `[externals]` (`name = auto | /prefix`); activate per mode with `externals = name1 name2`.
`auto` probes via pkg-config / wrapper scripts for `mpi`, `hdf5`, `netcdf`, `blas`, `openblas`,
`lapack`, `fftw`/`fftw3`; a prefix probes `<prefix>/include` and `<prefix>/lib`. Resolved flags are
appended to `cflags`/`lflags`. **There is no `--pkg-config`/`--with-mpi-auto` CLI flag** — it is
fobos-only.

```ini
[externals]
mpi  = auto
hdf5 = /opt/hdf5-1.14

[default]
cflags    = -c
externals = mpi hdf5
```

To *publish* a `.pc` file for your own library, set `pkgconfig = true` (+ optional `pkgconfig_name`,
`pkgconfig_desc`, `pkgconfig_url`, `pkgconfig_req`, `pkgconfig_req_priv`; defaults from `[project]`).

### Multi-target builds

```ini
[target.solver]
source = src/solver.f90
output = solver

[example.demo]
source = examples/demo.f90
output = demo
```

`[target.NAME]` and `[example.NAME]` define independently-built artifacts. A mode-level `target` and
`[target.*]` are mutually exclusive. CLI: `--target-filter solver,foo` restricts which targets build;
`--examples` also builds `[example.*]`. (`fobos` help writes the section as `[[target.*]]`; configparser
strips the outer brackets, so both forms produce `target.NAME`.)

### Auto-discovery

When `src` is unset (fobos and CLI) and `--no-auto-discover` is off, FoBiS scans `src/`, `source/`,
`app/` for Fortran sources and uses the directories it finds as scan roots.

### Build cache

`BuildCache` content-addresses built `use=fobos` dependency artifacts; key = SHA-256 of
`source_commit | compiler | cflags_hash | fobis_version`. Default dir `$FOBIS_CACHE_DIR` or
`~/.fobis/cache`. Manage with `fobis cache list|clean --older-than N|show DEP`. Disable per build with
`--no-cache`; relocate with `--cache-dir`.

### Includes (`[include]`)

```ini
[include]
paths = base.fobos ?optional.fobos
```

Pulls sibling fobos files (relative to the including file; `${ENV}`/`~` expanded). A leading `?` marks
an include optional (missing → skipped); otherwise a missing file aborts. Merge is **parent-wins**,
except list-typed keys (`[modes] modes`, `[features] default`, `[varsets] default`) which are
token-merged. Cycle-detected, depth-capped.

---

## Fetch Dependencies & Lock File

The `fetch` command pulls GitHub-hosted Fortran libraries declared in `[dependencies]`.

```ini
[dependencies]
deps_dir = .fobis_deps     ; optional clone dir (default .fobis_deps)

penf     = https://github.com/szaghi/PENF :: tag=v1.5.0
stdlib   = fortran-lang/stdlib :: semver=^0.5 :: use=fobos :: mode=gnu   ; user/repo shorthand
jsonfort = https://github.com/jacobwilliams/json-fortran :: branch=main :: use=fobos
```

Spec: `name = URL [:: branch=X | tag=X | rev=X | semver=EXPR] [:: mode=X] [:: use=sources|fobos]`.
`semver` is **mutually exclusive** with branch/tag/rev and resolves the highest matching git tag
(Cargo-style `^`, `~`, `=`, `>=`/`<=`/`>`/`<`, `*`, comma-AND).

| `use=` | fetch behaviour | build behaviour |
|---|---|---|
| `sources` (default) | clone only | dep dir added to source scan inline |
| `fobos` | clone + `fobis build` in dep | dep fobos added to `dependon`; dep dir excluded from scan |

Workflow:

```bash
fobis fetch              # initial clone; pre-build use=fobos deps
fobis fetch --update     # re-pull and re-build
fobis fetch --no-build   # clone only
fobis fetch --frozen     # enforce exact fobos.lock state; abort on drift or missing lock
fobis build              # auto-reads .fobis_deps/.deps_config.ini — no extra flags
```

---

## Test Runner & Coverage

`fobis test` discovers, builds, and runs Fortran test programs; `fobis coverage` turns instrumented
runs into HTML/XML/text reports. Both read optional fobos sections:

```ini
[test]
test_dir = tests          ; directory scanned for test programs (default test)
suite    = unit           ; only run tests tagged ! fobis: suite=unit
timeout  = 120            ; seconds before a test is killed (default 60)
compiler = gnu            ; override compiler for test builds
cflags   = -c -O0 -g

[coverage]
format     = html         ; html xml text (list; default html)
output_dir = coverage     ; report directory (default coverage)
fail_under = 75           ; exit 1 if line coverage < N%
exclude    = tests/*      ; glob(s) to exclude
```

`fobis test --coverage` runs the suite then generates the report. `fobis test --list` shows discovered
tests; `--suite`, `--filter`, `--timeout`, `--no-build` refine the run.

---

## LLM Commit Messages and the Local LLM

`fobis commit` drafts a Conventional-Commits message from your **staged** diff. The model answers a JSON
object constrained by a schema and FoBiS builds the `type(scope)!: description` header itself (free-text
fallback when a server rejects the schema).

Providers (`[llm] provider`, or `--provider`):
- `managed` (default): FoBiS installs a pinned llama.cpp `llama-server` and runs it on loopback with a
  per-process API key, around each command (or keeps it with `fobis llm serve start`). Setup once:
  `fobis llm runtime install && fobis llm pull coder-7b`; check with `fobis llm doctor`. Models: aliases
  from `fobis llm recommended` (Apache-2.0, pinned commits) or `hf:<org>/<repo>[@<rev>]/<file>.gguf` or a
  GGUF path. Use 7B or larger: 0.5B/1.5B models copy the prompt instead of reading the diff.
- `ollama` (`http://localhost:11434`) and `openai` (any OpenAI-compatible endpoint; `api_key_env` names the
  environment variable holding a hosted service's key).

A `[llm]` section that sets `model`/`url` without `provider` keeps meaning Ollama (configs from before the
managed runtime). Config: `~/.config/fobis/config.ini` (`$XDG_CONFIG_HOME` honoured), `[llm]` keys
`provider`, `model`, `url`, `api_key_env`, `runtime` (`pinned`|`PATH`|path), `runtime_variant`, `n_ctx`,
`n_gpu_layers`, `threads`, `startup_timeout`, `max_diff_chars` (12000), `refine_passes` (0). The LLM directory
is `$FOBIS_LLM_DIR` or `~/.fobis/llm` (models, runtime, logs; relocatable: copy it to an offline cluster).

```bash
fobis commit --init-config            # write a commented config template
fobis commit --show-config            # print effective config
fobis commit --refine-passes 2        # critique-and-rewrite iterations
fobis commit --apply                  # run `git commit` with the generated message
fobis llm ask "question"              # quick question to the configured model
```

---

## Ecosystem: Interconnected Projects

`fobis ecosystem` manages a set of FoBiS repositories that depend on each other (e.g. PENF → BeFoR64
→ StringiFor) as a whole. The registry is an explicit list in the **user config**
`~/.config/fobis/config.ini` (`$XDG_CONFIG_HOME` honoured) — not in any fobos:

```ini
[ecosystem]
root     = ~/fortran
projects = PENF FACE BeFoR64 StringiFor FLAP   ; names under root, or paths
theme    = github                              ; HTML dashboard palette
mode     = auto                                ; auto | light | dark
```

Edges come from each project's own fobos `[dependencies]` (a dep is an ecosystem dep when its key or
URL repo name matches a registered project). Projects are walked in **release order** (topological
levels, dependencies first; cycles reported, never looped).

| Subcommand | Does |
|---|---|
| `discover [--root DIR]` | list unregistered FoBiS git repos under root; prints the `add` command (read-only) |
| `add NAME\|PATH...` / `remove NAME...` | edit the registry (all-or-nothing; only the `projects` key is rewritten, comments kept) |
| `graph [--json]` | release order + dependency tree |
| `dashboard [--format terminal\|html] [--theme T] [--mode M] [--no-fetch] [--no-ci] [--json]` | per project: branch, dirty, ahead/behind, VERSION vs tag, unreleased/releasable commits + suggested bump, CI at HEAD (via `gh`), scaffold drift, dependency pins (lock vs dep's remote head). Runs `git fetch` first unless `--no-fetch` |
| `exec [--only] [--from] [--fail-fast] -- CMD` | run CMD (bash -c) in every project; `fobis` inside resolves to this FoBiS |
| `fetch` | `fobis fetch --update` in every project with deps |
| `check PROJECT [--keep] [--fail-fast]` | stage each transitive dependent in a tempdir with PROJECT's **local working copy** (uncommitted changes included) and run its check commands from scratch; repos untouched |
| `scaffold status\|sync [--apply [--yes]]` | scaffold across projects; sync is a dry run unless `--apply` |
| `release [--dry-run] [--bump NAME=minor\|vX.Y.Z] [--from X] [--yes] [--no-wait]` | release train: plan → pre-flight blockers (dirty, behind, CI failing, no release.sh, git-cliff missing...) → confirm → per project `scripts/release.sh vX.Y.Z` (its own prompt), verify tag local+remote (declined → `aborted`), wait GitHub release, `fetch --update` dependents; stop at first failure with a `--from` resume hint |

**Release rule:** files decide *whether* (a commit is releasable if it touches a path outside
`docs/* .github/* *.md scripts/*`), Conventional-Commit types decide *how much* (`!`/BREAKING →
major, `feat` → minor, else patch), counting releasable commits only.

**Per-project fobos keys:**

```ini
[ecosystem]
check           = fobis build --mode tests-gnu   ; `check` commands, one per line
                  ./scripts/run_tests.sh         ; default: rule makecoverage if defined, else fobis build
release_exclude = docs/* .github/* *.md scripts/*

[scaffold]
skip = scripts/release.sh                        ; project-owned managed files
```

Pins: `current`, `stale` (run `fobis ecosystem fetch`), `ahead`, `diverged`, `unlocked` (never
fetched), `unknown`. Nothing commits or pushes except `release`, and only after confirmation; an
unanswerable prompt counts as *no*.

---

## JSON Output (scripting / CI)

Add `--json` to **`build`, `clean`, or `fetch`** for structured stdout. Exit codes are unchanged
(0 ok / 1 fail); JSON is always printed, even on failure.

```bash
fobis build --mode release --json
```

```json
{ "status": "ok", "target": "all", "objects_compiled": 3, "errors": [] }
```

```bash
result=$(fobis build --mode release --json)
[ "$(echo "$result" | jq -r '.status')" != "ok" ] && { echo "$result" | jq -r '.errors[]'; exit 1; }
```

For richer machine-readable project metadata (sources, compiler, targets, varsets), use
`fobis introspect --all --format json` instead.

---

## Library Builds

### Static library

```ini
[default]
compiler  = gnu
cflags    = -c -O3
src       = ./src/
obj_dir   = ./obj/
mod_dir   = ./mod/
mklib     = static
output    = libmylib.a
```

### Shared library

```ini
[default]
compiler  = gnu
cflags    = -c -fPIC -O3
src       = ./src/
mklib     = shared
output    = libmylib.so
```

Static-library tooling is configurable: `ar`, `arflags` (default `-rcs`), `ranlib` (set to empty to
skip — e.g. with `llvm-ar`, which updates the symbol table itself).

---

## Interdependent Projects (`dependon`)

```ini
[default]
# project B's fobos
dependon = ../projectA/fobos
src      = ./src/
```

FoBiS rebuilds project A if needed, then adds its `mod_dir` and built library to B's build. Spec form:
`path/fobos[:mode]`.

---

## Diagnosing Common Errors

### "Module 'xyz' not found"

Start with `fobis build --explain`: it locates the module's definition and says which of the causes below
applies.

1. **Missing source path** — the file defining `module xyz` is not in any `src` directory. Add it to `src`.
2. **Wrong `mod_dir`** — `.mod` written one place, compiler looking elsewhere. Keep `mod_dir` consistent.
3. **Dependency not fetched** — run `fobis fetch` if the module comes from a GitHub dep.
4. **Name-case / filename mismatch** — most compilers lowercase the `.mod` filename; verify on disk.
5. **Unresolvable graph** — run `fobis tree` to see the resolved dependency tree, or `fobis check`
   (`--strict`) to validate the graph without building.
6. **Wrong `dependon` path** — must point at the dep's *fobos file*, not its directory.

### Build produces no output / does nothing
- Sources may be up-to-date — `fobis build --force-compile` forces a full rebuild.
- Confirm `target` points to a file with a `program` statement, and `src` actually has `.f90` files.
- Check auto-discovery: with no `src`, FoBiS only scans `src/`, `source/`, `app/` (disable via
  `--no-auto-discover`).

### Flags not taking effect after change
Set `cflags_heritage = True` to auto-detect cflag changes and trigger a full rebuild; otherwise only
changed sources recompile.

### "The mode X is not defined into the fobos file"
`--mode` must exactly match a name in `[modes] modes = ...`. Run `fobis build --lmodes`.

### Library build not linking
- Static: `mklib = static` (output ends `.a`). Shared: `mklib = shared` + `-fPIC` in `cflags`.
- System libraries: prefer the `[externals]` section (auto-resolves flags) over hand-written `-L`/`-l`.

---

## Parsed File Extensions

- Modern Fortran: `.f90 .F90 .f95 .F95 .f03 .F03 .f08 .F08 .f2k .F2K`
- Legacy: `.f .F .for .FOR .fpp .FPP .fortran .f77 .F77`
- Include: `.inc .INC .h .H`

Add custom include extensions: `fobis build --inc .cmn`.

---

## Special Sections Summary

| Section | Purpose |
|---|---|
| `[default]` | Single-mode build configuration |
| `[modes]` | `modes = a b c` — lists named modes (first = default) |
| `[mode-name]` | One section per named mode |
| `[template-*]` (any name) | Template for mode inheritance (`template = ...`) |
| `[vars]` (any name) | Conventional home for `$NAME = value` globals |
| `[varset:NAME]` / `[varsets]` | Named `$variable` bundles / `default = ...` selection |
| `[features]` / `[feature:NAME]` / `[feature-group:NAME]` | Feature flags, per-feature constraints, mutual-exclusion groups |
| `[include]` | `paths = ...` — pull in sibling fobos files |
| `[externals]` | External library map (`name = auto \| /prefix`) |
| `[target.NAME]` / `[example.NAME]` | Multi-target / example build sections |
| `[test]` / `[coverage]` | `fobis test` / `fobis coverage` defaults |
| `[rule-NAME]` | Custom shell rule for `fobis rule --ex NAME` |
| `[dependencies]` | GitHub-hosted build dependencies (used by `fetch`) |
| `[project]` | Metadata: `name`, `authors`, `version`, `summary`, `repository`, `website`, `email`, `year` |
| `[scaffold]` | Optional `fobis scaffold` knobs: `apt_packages = …` (extra CI system packages), `skip = <globs>` (project-owned managed files, never synced) |
| `[ecosystem]` | How `fobis ecosystem` treats the project: `check` (commands for `ecosystem check`), `release_exclude` (globs whose changes call for no release) |

---

## Further Reading

Full documentation at **https://szaghi.github.io/FoBiS/**:

- [fobos reference](https://szaghi.github.io/FoBiS/fobos/) · [Complete example](https://szaghi.github.io/FoBiS/fobos/complete-example)
- [Command reference](https://szaghi.github.io/FoBiS/reference/build) (all 16 subcommands)
- [Ecosystem guide](https://szaghi.github.io/FoBiS/advanced/ecosystem) · [ecosystem reference](https://szaghi.github.io/FoBiS/reference/ecosystem)
- [Feature flags](https://szaghi.github.io/FoBiS/advanced/features) · [Build profiles](https://szaghi.github.io/FoBiS/advanced/build-profiles) · [Varsets](https://szaghi.github.io/FoBiS/advanced/varsets)
- [External libraries](https://szaghi.github.io/FoBiS/advanced/externals) · [Build cache](https://szaghi.github.io/FoBiS/advanced/cache) · [Auto-discovery](https://szaghi.github.io/FoBiS/advanced/auto-discovery)
- [Fetch dependencies](https://szaghi.github.io/FoBiS/advanced/fetch) · [Lock file & semver](https://szaghi.github.io/FoBiS/advanced/lock-file) · [Interdependent builds](https://szaghi.github.io/FoBiS/advanced/interdependent)
- [Test runner](https://szaghi.github.io/FoBiS/advanced/testing) · [Coverage](https://szaghi.github.io/FoBiS/reference/coverage) · [JSON output](https://szaghi.github.io/FoBiS/advanced/json-output)
- [Source code](https://github.com/szaghi/FoBiS)
