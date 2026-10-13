# The gate

Each check of FoBiS answers one question: does it build, are the changed lines clean, do the tests pass, are the
results still the references', did a refactoring change them, is it slower, are the numerical budgets met.
`fobis gate` asks them all and gives **one verdict**, with the first failing fact of each check — the call an
agent makes after every edit, and the job a CI runs on every pull request.

```bash
fobis gate                       # the working tree against HEAD
fobis gate --base origin/master  # everything since the merge base with origin/master, uncommitted edits included
fobis gate --stage build,test    # only some stages
fobis gate --json                # one JSON verdict
```

## Stages

| Stage | Runs | Fails when | Skipped when |
|-------|------|-----------|--------------|
| `build` | `fobis build` | the build fails (first diagnosis) | — |
| `review` | `fobis review` on the changed lines | an error or warning finding on a changed line | nothing changed; not a git repository |
| `test` | `fobis test` | a test fails (crash located, notes) | no test program in the test directory |
| `verify` | `fobis verify` | a case differs from its reference, or has none | no case declared |
| `diff-run` | `fobis diff-run BASE` | a case's results changed (worst point, changed procedures) | no case; nothing changed |
| `bench` | `fobis bench --compare BASE` | a benchmark is measurably slower (with the compiler-report regression) | no `[bench:]` declared; nothing changed |
| `assess` | `fobis assess CASE` per case with a budget | a budget is not met | no `[assess:]` budget |
| `matrix` | `fobis matrix` on the declared modes/shadows | a cell fails or two cells disagree | no `[gate] matrix_modes` |

Every stage is a nested `fobis ... --json` command: the gate adds no check of its own, it reduces each document to
**pass**, **fail**, **error** (the command gave no result) or **skipped** — with the reason, so "no tests" is never
mistaken for "tests pass". When the build fails, the stages that need it are skipped ("the build failed"); the
review still runs. An **advisory** stage is reported but does not fail the gate.

**The base.** Without `--base`, the change is the working tree against `HEAD`: review, diff-run and bench look at
the uncommitted edits (skipped when there are none). With `--base REF`, the change is everything since the merge base
of `HEAD` and `REF`, the uncommitted edits included (`fobis review --base REF --worktree`).

## Declaring the gate

```ini
[gate]
stages         = build review test verify diff-run bench   ; order and selection (default: all)
skip           = assess
advisory       = bench                                      ; reported, never failing
base           = origin/master
mode           = gnu-debug
matrix_modes   = gnu-debug nvf-debug
matrix_shadows = none checks
```

Command-line `--stage`, `--skip`, `--advisory`, `--base`, `--mode` override the section; `--fail-fast` stops at the
first blocking failure. Exit status 0 when the gate passes, 1 when a non-advisory stage fails or errs, 2 for a
declaration error or an unknown base.

## Real runs

**A change with three problems.** An `axpy` loop changed to start at 2 and to carry a recurrence, uncommitted, in a
project with one case (no reference yet) and one benchmark:

```text
gate: FAIL, 25.8 s
  build     pass [0.2 s]
  review    pass [0.2 s]
  test      skip: no test program in test/
  verify    FAIL [0.8 s]: axpy: no reference (fobis verify axpy --update, once right)
  diff-run  FAIL [1.5 s]: axpy: differs: total fail (1/1 out of exact, max rel 5.000000000112198e-07), worst at [0]: 199999.90000715363 vs 200000.00000715363
            changed: src/kern.f90 (kern::axpy)
  bench     FAIL [23.2 s]: axpy: slower than HEAD, speedup 0.465 [0.409, 0.499]
  assess    skip: no assessment budget declared ([assess:NAME] budget)
  matrix    skip: no matrix declared ([gate] matrix_modes)
```

The loop no longer updates `y(1)`: diff-run sees the total move by 0.1 and names the procedure; bench sees the
recurrence cost half the speed.

**A performance commit.** StringiFor's "make split, replace, unique, escape, join and read_* linear", gated against
its parent (`--base`, the commit's sources uncommitted on top):

```text
gate: FAIL (base bold (merge base 5c620de5b712)), 80.5 s
  build     pass [25.3 s]
  review    FAIL [0.7 s]: src/lib/stringifor_string_t.F90:2452: COR101 the action of this one-line if is on a continuation line
  test      skip: no test program in test/
  verify    FAIL (advisory) [13.4 s]: probe: no reference (fobis verify probe --update, once right)
            split: no reference (fobis verify split --update, once right)
  diff-run  pass [26.9 s]
  bench     pass [14.2 s]
  ...
```

Same results as before the commit (diff-run), not slower (bench), and one finding on a line the commit added: an
`if (...) &` whose action is on the continuation line (rule COR101).

## For agents

The MCP server exposes the command as the `gate` tool; its JSON (see
[JSON output](/advanced/json-output#fobis-gate-json)) gives `status` and, per stage, `status`, `fact`, `details`,
the commands run and the time. A failing stage's `fact` is where to look next: the diagnosis, the finding, the
crash location, the worst point of a quantity, the lost vectorisation.
