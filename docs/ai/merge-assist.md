# Resolving merge conflicts

`fobis merge-assist` proposes a resolution for each conflict of a merge, rebase or cherry-pick: deterministic
rules first, then the LLM for the rest, and every proposal is **compiled** before you see it. You decide hunk by
hunk; FoBiS never changes the git state.

```bash
git merge feature                     # stops on conflicts
fobis merge-assist                    # report: the three versions and a proposal per conflict
fobis merge-assist --apply            # ask hunk by hunk and write the accepted resolutions
fobis merge-assist --apply --yes      # accept only the safe ones, leave the rest in conflict
fobis merge-assist --no-model         # deterministic rules only
fobis merge-assist --context          # print what the model would receive, run no model
```

## Safety

- FoBiS **never** runs `git add`, `git merge --continue`, `git rebase --continue` or any other git command that
  changes the index or the history. After `--apply` the files are still unmerged: review them with `git diff`,
  run your tests, then `git add` them yourself.
- `--apply` writes only the conflict blocks still present in the file and accepted by you: a conflict you already
  resolved by hand is left exactly as you wrote it.
- `--apply --yes` accepts only the high-confidence rules below and the model's proposals that compile; anything
  else stays in conflict.

## Which side is which

The operation is detected from `MERGE_HEAD`, `REBASE_HEAD` or `CHERRY_PICK_HEAD`, and the sides are named as
they really are. During a **rebase**, git's "ours" is the upstream branch and "theirs" is your commit being
replayed: `merge-assist` says so, both to you and to the model.

## How a conflict is resolved

1. **The hunks come from the index**, not from the file: base, ours and theirs are merged again with
   `git merge-file --diff3`. This works whatever your `merge.conflictStyle`, and even after you edited the file.
2. **Deterministic rules**, no model:

   | Rule | Confidence |
   |------|------------|
   | One side equals the base: take the other side | high |
   | Both sides made the same change, or differ only in whitespace | high |
   | Both sides changed `use ..., only:` lines: three-way union (a module or name one side removed stays removed) | high |
   | Both sides moved a fobos `[dependencies]` `tag=` pin: the higher version | high, flagged for review |
   | One side only appended (or prepended) lines, the other only edited the base lines: both changes | medium: a draft |

3. **The model**, for the other hunks and to refine drafts. It receives the base, ours and theirs, the lines
   around the conflict, the **commit messages of each side** since the merge base (their intent), the procedures
   at the conflict, and the draft when there is one. It answers a strategy (`ours`, `theirs`, `both`, `custom`),
   the merged text for `custom`, a rationale, a confidence, risks and citations. For `ours`, `theirs` and
   `both`, FoBiS builds the text itself; a `custom` text with conflict markers is rejected; a proposal that
   cites nothing is kept at confidence low, and so is a proposal that still does not compile after the retries.
4. **Compilation.** The file, with every proposal applied, is compiled syntax-only with the fobos mode's compiler
   (gfortran `-fsyntax-only`, ifx `-syntax-only`, nvfortran and LFortran into a scratch object), with the mode's
   `-D`/`-I` flags and its module directory. A model proposal that does not compile goes back to the model with
   the compiler's errors, at most twice. If the modules the file uses are not built yet, the check is
   impossible, not failed: build the project once (`fobis build`) before merging for full verification.

## What the history of real projects says

The rules were replayed on historical merges (`scripts/merge_replay.py`, on clones):

| Repository | Conflicted merges | Hunks | High-confidence rules | Equal to the committed resolution | Drafts |
|------------|-------------------|-------|-----------------------|-----------------------------------|--------|
| fpm (last 60 merges) | 11 | 32 | 6 | 6 | 1 |
| an HPC solver (39 merges) | 7 | 26 | 0 | — | 15 |

The high-confidence rules never disagreed with the human resolution. In the HPC code, 15 of the 26 hunks were
the same pattern: one branch added an `!$omp` directive after an `!$acc` directive, the other added a variable
to the `!$acc` clause. The draft keeps both changes; the human also added the variable to the new `!$omp`
clause. That last step is a judgement, which is why drafts go to the model and are never accepted by `--yes`.

**The model on the same history.** `scripts/merge_replay.py --model` also sends every draft and every hunk the
rules leave unresolved to the configured model, as `merge-assist` does, and compares its proposal with the
committed resolution. With coder-7b (the default managed model) on the HPC solver above, on an NVIDIA A30 (26
hunks, 7.5 minutes):

| Hunks asked | Equal to the committed resolution | Drafts improved | Drafts made worse | Unresolved hunks solved | Unusable answers |
|-------------|-----------------------------------|-----------------|-------------------|-------------------------|------------------|
| 26 (15 drafts, 11 unresolved) | 3 | 0 of 14 | 0 | 2 of 11 | 0 |

None of the 14 drafts became equal to the human resolution (which also adds the clause variable to the new
`!$omp` directive), and the model rated all 26 of its proposals `high` confidence, right or wrong: its confidence
carries no information. Exact equality is a strict
measure (a human may also reformat or touch nearby lines), but the result agrees with the `lint --deep`
evaluation: with a 7B model, review every proposal; the deterministic rules and the compile check are what can be
trusted.

## Limits

- Semantic conflicts that compile but are wrong (the two sides changing the same invariant in different places)
  cannot be detected one hunk at a time. `merge-assist` ends by listing the procedures changed by both sides:
  test them (`fobis test`).
- Binary files and conflicts without text (modify/delete of a whole file) are not handled.
- A `fobos.lock` conflict should be resolved by regenerating the lock (`fobis fetch`), not by merging it.
