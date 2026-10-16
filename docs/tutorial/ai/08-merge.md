---
title: 8. Merge conflicts
---

# 8. Merge conflicts

Two branches changed the same line of `test_exactness.F90`: `master` loosened the tolerance for optimised builds,
`midpoint` documented that it now covers the midpoint rule too (and added a check, which merges cleanly):

<<< @/examples/output/6-ai/08/merge.txt{console}

<<< @/examples/output/6-ai/08/conflict.txt{console}

`fobis merge-assist` first tries deterministic rules: one side unchanged, the same change on both sides,
whitespace only, the union of two `use, only` lists, a pin moved to the higher version. None applies to a value
changed on both sides:

<<< @/examples/output/6-ai/08/deterministic.txt{console}

With the model, the conflict is sent with both sides, the base, and the commit messages of each branch (the
intent). The proposal is compiled before it is shown, and a failure goes back to the model with the compiler's
errors, twice:

<<< @/examples/output/6-ai/08/merge.measured.txt{console}

The model's text describes the right resolution (keep `4.e-14` and merge the comments), but the resolution it
chose keeps both lines, and a second declaration of `tolerance` does not compile. FoBiS reports that, lowers the
proposal's confidence, and writes nothing. Only `--apply` writes resolutions, and without `--yes` it asks hunk
by hunk: accept, ours, theirs, both, edit, skip. Here the right answer is an edit:

```fortran
real(R8P), parameter :: tolerance = 4.e-14_R8P !< Rounding allowance: a few ulps of the results at -O3, also for the midpoint rule.
```

![fobis merge-assist: the rules find no safe answer, the model's proposal does not compile](/gifs/16_llm_merge.gif)

*coder-7b on an NVIDIA A30 of a cluster node, reached through ssh; recorded in real time.*

::: tip What you learned
`fobis merge-assist`, `--no-model`, `--apply`, `--yes`, compiled proposals. Reference:
[merge conflicts](/cookbook/ai#merge-conflicts).
:::

Next: [9. An agent under the gate](./09-agent).
