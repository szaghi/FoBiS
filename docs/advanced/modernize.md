# Verified modernisation

Modernising legacy Fortran is safe only when its results do not move. `fobis modernize` applies the mechanical
fixes of the linter in a scratch copy and keeps them only when the evidence says they changed nothing; the same
loop — edit, then let FoBiS's checks decide — covers the edits an agent makes.

```bash
fobis modernize                      # find, apply in a scratch copy, verify, report
fobis modernize --apply              # ... and write the verified fixes into the working tree
fobis modernize --select OBS011      # only some rules
fobis modernize --json               # for scripts and agents
```

## The fixes

| Rule | Rewrite |
|------|---------|
| `MDN011` | `(/ ... /)` -> `[ ... ]` |
| `MDN021` | `.eq.` `.ne.` `.lt.` `.le.` `.gt.` `.ge.` -> `==` `/=` `<` `<=` `>` `>=` |
| `OBS005` | specific intrinsics -> generic (`dsqrt` -> `sqrt`, `alog` -> `log`, `dmax1` -> `max`, `float`/`sngl` -> `real`, `idint`/`ifix` -> `int`, `idnint` -> `nint`, `dint` -> `aint`, `dnint` -> `anint` ...); not `amax0`, `amin0`, `max1`, `min1` (they convert the result's type) |
| `OBS008` | `character*n`, `character*(*)` -> `character(len=n)`, `character(len=*)` |
| `OBS011` | `do 10 i = ...` / `10 continue` -> `do i = ...` / `end do`, only when that loop alone ends on a `continue` and nothing (`go to`, arithmetic `if`, `err=`/`end=`/`eor=`, `assign`, alternate return) refers to the label; `end do` at the column of its `do` |

The rewrites keep the case of the code (`DSQRT` -> `SQRT`, `CONTINUE` -> `END DO`) and work in fixed form.

## The verification

1. The working tree (tracked and untracked files) and the fetched dependencies are copied twice into a scratch
   directory: an untouched copy and a fixed one. Nothing is written to your tree until the end, and only with
   `--apply`.
2. The fixed copy must **build** (when the untouched copy builds: a build failing in both is not evidence either
   way), the **tests** that pass on the untouched copy must still pass, and every declared **case** must give
   equivalent quantities ([diff-run](/advanced/diff-run)'s comparator, the case's tolerance — exact by default).
   A case already failing on the untouched copy is not used, and the report says so.
3. When the whole set fails, each rule is checked alone: the rules that pass are still verified.
4. `--apply` writes the verified rules' fixes, file by file, only into files unchanged since the analysis.

**Evidence.** The report says what showed the fixes harmless: `tests`, `cases`, `tests+cases`, or `build` alone.
A build alone does not show unchanged behaviour: applying then needs `--unverified`. Nothing at all (no build, no
tests, no cases) fails the check.

Exit status 0 when every rule is verified (or there is nothing to fix), 1 when a rule is not, 2 for a declaration
error.

## Real run: FFTPACK in FORTRAN 77

The original FFTPACK (fortran-lang/fftpack at the revision before its conversion to free form: 59 source files in
`src`, fixed form, and 13 test programs), its fobos written by [`fobis fpm import`](/advanced/fpm), and one case declared: the 133 error
norms printed by the original test `tstfft`, compared exactly.

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

`--apply` rewrote 46 files, and the 13 tests pass on the rewritten tree; the 133 numbers of `tstfft` were
compared exactly between the two copies by the check itself.

**What the verification caught.** The first version of the `OBS011` fix placed `end do` at the indentation of the
line — for a DO that carries a label itself (`  103 DO 104 I=1,N`) that is column 3, so in fixed form the `d` fell on
column 6, the continuation column: `dzfftf.f` stopped compiling. The check failed on the tests, the other rules were
verified alone, and the fix was corrected (`end do` at the column of the `do` keyword). It also found that a case
whose program prints several numbers on one line read nothing with `quantities = stdout` and compared as vacuously
equal: the `stdout` probe now reports that as an error.

## Workflows

**FORTRAN 77 to modern Fortran.** Declare cases on the outputs that matter (`[case:NAME]`, exact tolerance) and
record references (`fobis verify --update`); then `fobis modernize --apply` for the mechanical part; then the edits
that need judgement (implicit typing, COMMON to modules, arithmetic IF to IF blocks) by hand or by an agent, each
checked with `fobis diff-run` (equivalent?) and `fobis gate`. Where a result may move legitimately (reordered
floating-point sums), `fobis diff-run --assess` judges the difference against the code's own spread
([assessment](/advanced/assess)).

**Porting to GPU.** Directives proposed by an agent; `fobis lint --compiler-feedback` with the compiler's report
(implicit copies, sequential loops); `fobis diff-run` against the CPU revision (equal results, within the
tolerance declared for reordered reductions); `fobis bench --compare REF --feedback` for the measured speedup and
the loops the compiler did not parallelise; `fobis matrix` to keep the other compilers building.
