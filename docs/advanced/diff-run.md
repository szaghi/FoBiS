# Differential execution

A refactoring, a modernisation, a performance rewrite — or an agent's edit — should leave the results alone.
`fobis diff-run` checks that by running the program, not by reading the code: it builds and runs the declared
[cases](/advanced/cases) on a revision and on the working tree, and compares every quantity.

```bash
fobis diff-run                 # HEAD vs the working tree, every case
fobis diff-run v2.0.0 sod      # a tag, one case
fobis diff-run main --assess   # judge a difference against the code's own numerical spread
fobis diff-run --json          # for scripts, CI and agents
```

## How it works

- The revision is extracted with `git archive`, its submodules at the commits it records; the working tree is
  copied (tracked and untracked files, ignored ones excluded). The fetched dependencies of the working copy are
  copied into both. Everything is built and run in these scratch copies, removed at the end (`--keep` keeps them):
  your tree, your build directories and your repository's metadata are never written.
- The cases are those of the working tree's fobos; each side builds them with its own fobos (a mode the revision
  does not have is reported as a build failure of the revision).
- Each quantity is compared with the [`verify`](/advanced/verify) comparator and the case's tolerance: count of
  values out of tolerance, largest absolute and relative difference, the worst point with its index, NaN or
  infinities that appeared or vanished.
- The report lists the files that changed between the two and, for Fortran sources, the procedures whose code
  changed — the first place to look when a quantity differs.
- `--assess` runs, for a case that differs, the [assessment](/advanced/assess) families of the case on the working
  tree (except `inputs` and `refinement`; `rounding` by default) and judges each difference against the digits
  they share: a relative difference below `10^-digits` is what the code produces anyway under a change of flags,
  and the case is **within uncertainty** instead of **differs**.

## Real runs

**A refactoring proven equivalent.** StringiFor's commit "perf(string_t): make split, replace, unique, escape,
join and read_* linear" rewrote six procedures for speed. A probe program turning their results into numbers
(token count, a checksum of the tokens, lengths and indices after replace, unique and join), run on the commit and
on its parent (real output, abridged):

```text
diff-run: 3554cf7d5a0f vs the working tree, 18 file(s) changed
  M src/lib/stringifor_string_t.F90: stringifor_string_t::count_substring, stringifor_string_t::scount, stringifor_string_t::capitalize, stringifor_string_t::escape, stringifor_string_t::join_strings, stringifor_string_t::join_characters
  ...
note: both sides use the working copy's fetched dependencies (src/third_party)

probe: EQUIVALENT
  tokens: equal (1 value(s), exact)
  split_checksum: equal (1 value(s), exact)
  replaced_len: equal (1 value(s), exact)
  replaced_index: equal (1 value(s), exact)
  unique_len: equal (1 value(s), exact)
  joined_len: equal (1 value(s), exact)

1 of 1 case(s) equivalent.
```

PENF's commit guarding the quad-precision bit-string routines behind `_R16P` ("no behavior change for any
compiler") is equivalent too, on its own doctests for `bstr` and `bcton` of `R16P` and `I8P`.

**A change of behaviour, located.** PENF's breaking commit "make real str exact" says that the string of a real
did not read back to the same number. Diff-run of a probe printing `str` of a few reals and the bits of `1.0`
(abridged):

```text
probe: DIFFERS
  pi: 1/1 out of tolerance (exact): max abs 3.10862e-15, max rel 9.89506e-16, L2 3.10862e-15
    got 3.141592653589793, ba629e796163 3.14159265358979
  tenth: equal (1 value(s), exact)
  third: 1/1 out of tolerance (exact): max abs 3.33067e-16, max rel 9.99201e-16, L2 3.33067e-16
    got 0.3333333333333333, ba629e796163 0.333333333333333
  big: 1/1 out of tolerance (exact): max abs 0, max rel 0, L2 0
    non-finite: [0]: 1.7976931348623157e+308 (reference inf)
  bits: 1/1 out of tolerance (exact): max abs 1.11111e+13, max rel inf, L2 1.11111e+13
    got 11111111110000.0, ba629e796163 0.0
  changed since ba629e796163:
    compiler.preproc: '-D_ASCII_SUPPORTED -D_UCS4_SUPPORTED -D_R16P' -> '-D_ASCII_SUPPORTED -D_UCS4_SUPPORTED -DPENF_R16P'
```

Each claim of the commit message, measured: `pi` and `1/3` gained their 17th digit, `0.1` did not change,
`str(huge)` no longer reads back as infinity, the bit string is now most significant bit first, and the renamed
preprocessor macro shows in the provenance.

**An injected change.** One added to the integer that PENF's `bstr_R8P` writes as bits:

```text
diff-run: HEAD (20ffc4326792) vs the working tree, 2 file(s) changed
  M fobos
  M src/lib/penf_stringify.F90: penf_stringify::bstr_r8p

probe: DIFFERS
  pi: equal (1 value(s), exact)
  ...
  chunks: 1/5 out of tolerance (exact): max abs 1, max rel inf, L2 1
    worst at [4]: 1.0 vs HEAD 0.0
```

The procedure that changed and the value that moved, side by side.

## Notes

- A probe program written to compare two revisions must exist on both sides: commit it (on a branch) first, or
  compare cases whose programs both revisions have.
- Both sides use the working copy's fetched dependencies: a revision that pins other versions is built against
  the current ones (said in the report's notes).
- The cost is two builds per case (and, with `--assess`, the assessment's builds).
- The MCP server exposes the command as the `diff_run` tool.
