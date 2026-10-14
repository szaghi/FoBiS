# The verification model

A test asks "does this check pass?". The verification commands ask "did the **numbers** change, by how much, and
why?". They share one model: a case, the quantities it produces, and a comparison against something else. The
[verified numerics track](/tutorial/numerics/01-cases) builds it step by step on a real program.

## A case and its quantities

A `[case:NAME]` section of the fobos names a program (a `target` built by FoBiS, or a `command`), the mode it is
built in, its arguments and input files, and, optionally, ranks, threads, GPUs and a time limit. Each run happens
in a fresh directory under `.fobis/runs/`, so runs never see each other's files.

The **quantities** are what the program computes, read after the run by probes: a regular expression on the
output, a column of a text file, a JSON key, an HDF5 dataset, a Fortran unformatted record. A quantity is a number
or an array; an array read from a Fortran file keeps its index order, so a difference is reported at `(2,3)`, the
way the program indexes it.

Every run also records its **provenance**: the git commit and whether the tree had uncommitted changes, the
pinned dependencies, the compiler, its version and flags, the loaded modules, the machine (the compute node's,
under Slurm). When two runs disagree, the provenance says what else changed between them.

## One comparison per question

The commands differ only in what the quantities are compared with:

| Question | Compared with | Command |
|---|---|---|
| Are the results still the ones I accepted? | a reference file, written only by `--update` | [`verify`](/tutorial/numerics/02-verify) |
| Does a defect show in some builds only? | other modes, and the same mode built with checks, sanitizers or strict standard flags (shadow modes) | [`matrix`](/tutorial/numerics/03-shadows) |
| How many digits can I trust? | the same case perturbed: precision, rounding, compiler, threads and ranks, inputs, grid refinement | [`assess`](/tutorial/numerics/04-assess) |
| Is this refactoring harmless? | another revision of the code, built and run side by side | [`diff-run`](/tutorial/numerics/05-diff-run) |
| Is it faster? | another revision, or the recorded history, with confidence intervals | [`bench`](/tutorial/numerics/06-bench) |
| Where does the time go? | nothing: the profile, mapped to procedures and source lines | [`profile`](/tutorial/numerics/08-profile) |

[`gate`](/tutorial/numerics/07-gate) runs the ones that apply to the project, plus build, review and tests, and
reports the first failing fact of each.

## Equality is declared, never assumed

Two values are equal when the case's **tolerance** says so: `exact` by default, else an absolute, a relative or
an ulp bound, per quantity. NaN equals NaN; a NaN that appears or vanishes is reported as such. A tolerance is a
claim about the program, so it is written in the fobos, next to the case, and reviewed like code.

`diff-run --assess` offers a second criterion: a difference is *within uncertainty* when it is smaller than the
digits the [assessment](/tutorial/numerics/04-assess) says the case has.

## What the model does not do

- It writes nothing you did not ask for: references only with `--update` (refused when a quantity was not read,
  or when repeated runs differ), benchmark history only with `--record`.
- It does not know the right answer. A reference is the answer you accepted; `assess` measures how much the
  answers spread, not how far they are from the truth (except grid refinement, which estimates the discretisation
  error from the observed order).
- It does not replace tests: a test checks a property, a case watches numbers.

## Where the runs happen

Every command runs locally by default. With `--runner slurm` the runs become batch jobs (built locally, run on a
compute node, the node's facts in the provenance); on a login node named in the `[scheduler]` configuration, a
case asking for ranks or GPUs is refused instead of being run there. See [on a cluster](/tutorial/numerics/09-cluster).

## Further reading

- [Cases and provenance](/advanced/cases), [verifying results](/advanced/verify),
  [assessing numerical error](/advanced/assess)
- [Verification recipes](/cookbook/verification)
- The method of each `assess` family, with its references: `fobis kb show numerics:assessment#rounding-family` (and
  `precision-family`, `compiler-family`, `parallel-family`, `inputs-family`, `refinement-family`)
