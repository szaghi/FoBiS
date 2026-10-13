# Verifying results

`fobis verify` runs the [cases](/advanced/cases) of the project and compares their quantities with **references**:
results you accepted earlier. It answers the question a refactoring, a compiler upgrade or an agent's edit raises:
*do the numbers still come out the same, and if not, by how much, where, and what changed?*

```bash
fobis verify --update        # accept the current results as the references
fobis verify                 # compare with them
fobis verify sod --repeat 3  # also check that three runs agree with each other
fobis verify --json          # for scripts, CI and agents
```

## References

`fobis verify --update` runs the cases and writes each one's quantities, with the [provenance](/advanced/cases#provenance)
of the run, to `verification/references/<case>.json` (`[verification] references_dir` changes it). Commit them
with the project: they are the results you vouch for. FoBiS never writes a reference without `--update`, refuses
to record a run that missed a quantity, and refuses a run whose repetitions differ (`--repeat`). A reference made
from uncommitted code is flagged as such.

## Tolerances

By default a quantity must be reproduced exactly. Declare a tolerance per quantity in the case:

```ini
[case:sod]
...
tolerance = mass: rel 1e-12; rho: abs 1e-10 rel 1e-8; iters: exact
            *: ulp 4
```

| Spec | Equal when |
|------|-----------|
| `exact` | identical (NaN equals NaN) |
| `abs A rel R` | `|value - reference| <= A + R * |reference|` |
| `ulp N` | within N units in the last place of the reference |

`*` applies to the quantities without their own entry. The report always gives the errors observed, also when
they are within tolerance, so a tolerance is chosen knowing what it allows.

## The report

A small program changed to compute in single precision, then verified (real output, abridged):

```text
harmonic: FAIL
  total: 1/1 out of tolerance (exact): max abs 9.93411e-09, max rel 4.76837e-09, L2 9.93411e-09
    got 2.083333343267441, reference 2.083333333333333
  x: 1/4 out of tolerance (exact): max abs 9.93411e-09, max rel 2.98023e-08, L2 9.93411e-09
    worst at (3): 0.3333333432674408 vs reference 0.3333333333333333
```

That was a computation done in single precision: only `x(3)`, the value not exact in binary, moved. For each
quantity: how many values are out of tolerance, the largest absolute and relative errors, the L2 norm of the
difference, and the worst point with its index: Fortran order and 1-based, `(i,j)`, for arrays read from Fortran
binary files; row-major and 0-based, `[i][j]`, for HDF5 and JSON. NaN or infinities that appeared are listed with
their position.

What changed in the provenance since the reference is reported too. Next to a failure it is the first suspect;
next to a pass it says the results did not depend on it. Switching compilers with `module load`, real output:

```text
harmonic: PASS
  changed since the reference (results unaffected):
    compiler.version: 'GNU Fortran (Ubuntu 16-20260315-...) 16.0.1 ...' -> 'GNU Fortran (GCC) 15.2.0'
    environment.modules: [] -> ['gcc/15.2.0']
```

A run that does not complete (build failure, crash, timeout) is reported with the build's diagnoses or the end of
its error output.

## Builds you can trust

FoBiS recompiles what changed since the last build, judged by timestamps, and every `fobis build` also recompiles
everything when the compiler behind the mode's command changed (path or `--version`: a `module load` of another
GCC; see [the build reference](/reference/build#compiler-changes)). The cases' builds are stricter: the objects
are recompiled from scratch also when there is no record of how they were built, when the flags changed, or when
another build touched the object directory since. The reason is recorded in
the provenance (`rebuilt_because`).

## Non-determinism

`--repeat N` runs each case N times and compares the runs with each other, exactly. A difference means the program
is not reproducible: an unseeded random number, a reduction whose order changes with threads or ranks,
uninitialised memory, a race. The case is reported `NONDETERMINISTIC` with the quantities that changed, and
`--update` refuses to record it.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Every case passes (or was updated) |
| 1 | A case fails, has no reference, is non-deterministic, or did not run |
| 2 | A case or tolerance is declared incorrectly, or an unknown case is named |

## For agents

`fobis verify --json` gives, per case, its status (`pass`, `fail`, `no-reference`, `nondeterministic`,
`run-failed`, `updated`), every quantity's comparison (status, tolerance, counts, `max_abs`, `max_rel`, `l2`,
`linf`, `worst` with index, value and reference, `nonfinite`), the provenance changes and the run's summary. The
[MCP server](/ai/mcp) exposes it as the `verify` tool (it never writes references).
