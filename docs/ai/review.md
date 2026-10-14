# Reviewing a change

`fobis review` reports the lint findings **on the lines you changed**, not on the whole code. It is the
command for a pre-commit hook and for pull requests: a legacy code base with hundreds of findings stays quiet,
and a new finding is visible the moment it is introduced, without a baseline.

```bash
fobis review                          # every uncommitted change (staged or not)
fobis review --staged                 # the staged change: pre-commit hook
fobis review --base origin/master     # the commits since the merge base: pull request
fobis review --format markdown        # a pull-request comment
fobis review --deep                   # plus an LLM risk summary, with citations
```

## What is reviewed

The whole project is linted, as by [`fobis lint`](/ai/lint) with the same fobos mode, rules, `[lint]` section
and `--compiler-feedback`, because cross-file rules need every file. Then only the findings whose lines touch an
added or modified line are kept. `--context N` also keeps findings up to `N` lines away.

**A changed directive counts its whole region as changed.** Removing a clause changes the meaning of every line
the directive governs: in

```fortran
!$omp parallel do private(flux) reduction(+:total)     ! the clauses are removed
do i = 2, n - 1
  flux = u(i + 1) - 2.0 * u(i) + u(i - 1)              ! OMP001: now a race
  unew(i) = u(i) + 0.1 * flux
  total = total + unew(i)                              ! OMP002: now an unprotected accumulation
end do
```

only line 1 changed, yet both findings are on the lines below. `fobis review` reports them, because the
OpenMP/OpenACC region of a changed directive is reviewed as a whole.

With `--staged` or `--base`, the reviewed version is the index or `HEAD`, while the linter reads the files on
disk: when a reviewed file also has unstaged (or uncommitted) changes, its line numbers can differ, and `fobis
review` warns.

The exit status is 1 when a finding of severity error or warning is on the changed lines (`--exit-zero` to
report only).

## Output formats

| Format | Use |
|--------|-----|
| `text` | The terminal (default) |
| `markdown` | A pull-request comment: a table of the findings and the rules involved |
| `github` | GitHub Actions annotations on the changed lines |
| `sarif` | Code-scanning upload |
| `json` | Scripts: the findings, `changed_lines`, and `risk` with `--deep` |

## Pre-commit hook

With [pre-commit](https://pre-commit.com), in `.pre-commit-config.yaml`:

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

Or as a plain git hook, `.git/hooks/pre-commit` (executable):

```bash
#!/bin/sh
exec fobis review --staged
```

The hook runs the rules only (no model): it takes as long as `fobis lint` on the project.

## Pull requests (GitHub Actions)

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

The first command annotates the changed lines and fails the job on a finding; the second writes the markdown
report to the job summary (or post it as a comment with your usual action).

## Risk summary: `--deep`

`--deep` asks the LLM for a risk summary of the change, written from facts:

- the **diff** of each changed Fortran file (what was removed matters as much as what was added);
- the changed code in context, changed lines marked;
- the **OpenMP/OpenACC regions** the change touches;
- for each **procedure header that changed**, the files that `use` its module;
- the findings on the changed lines and the documentation of their rules.

The model answers cited claims of two kinds, **risks** (what the change could break, and where) and **to
check** (what to verify before merging). As everywhere in FoBiS, a claim that cites nothing is dropped.
`--deep-context` prints the model's input and stops.

A real answer of coder-7b on an NVIDIA A30, for a change that removed `private(flux) reduction(+:total)` from a
parallel loop:

```text
Risk summary [llm]:
Risks:
  - A data race could occur in the parallel region of src/heat.f90:12-17 because the variable 'total' is shared and written by every thread. [1][2]
  - The variable 'flux' is shared and written by every thread in the parallel region of src/heat.f90:12-17, which could lead to a data race. [1][2]
  - The variable 'total' is accumulated by every thread in the parallel region of src/heat.f90:12-17 without a reduction clause, which could lead to incorrect results. [1][3]
Sources:
  [1] diff of src/heat.f90 (- removed, + added)  (diff:src/heat.f90)
  [2] rule OMP001 shared-scalar-written-in-parallel-region  (rule:OMP001)
  [3] rule OMP002 accumulation-without-reduction  (rule:OMP002)
```

The risks are right and cite the diff; the 7B model repeated one of them and wrote no "to check" item.
The summary adds to the text, markdown and json
formats; it never changes the exit status.

## Limits

- A finding caused by a change but reported elsewhere than in the changed lines or a changed directive's region
  (a caller of a procedure whose interface changed, a module variable now shared) is not reported: run `fobis
  lint` on the whole code from time to time, or widen with `--context`. The `--deep` summary lists the files
  using a module whose procedure headers changed.
- The review covers Fortran sources; other changed files are listed for `--deep` only.
