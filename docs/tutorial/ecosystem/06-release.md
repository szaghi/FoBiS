---
title: 6. The release train
---

# 6. The release train

Releasing a family by hand means: release the bottom library, wait for it, update its dependents' locks, release them,
and so on up the graph. `release` plans the whole train first:

<<< @/examples/output/3-ecosystem/06/plan.txt{console}

- Only projects with releasable commits are released (`mathx`'s docs commit is not), each with the version its
  Conventional Commits call for (`--bump NAME=major|minor|patch|vX.Y.Z` overrides one).
- Anything that would make a release fail blocks the whole train before it starts: uncommitted changes, a branch
  behind its upstream, a failing CI, a tag that exists already, no release script, no `git-cliff`. The `!` lines are
  warnings only.

Then it runs: each project's own `scripts/release.sh VERSION` (the one `fobis scaffold` installs, or yours), a check
that the tag reached the remote, and `fobis fetch --update` in the direct dependents, so the next ones release against
the new version.

<<< @/examples/output/3-ecosystem/06/release.txt{console}

(`--yes` answers every question, as a CI job would; `--no-wait` skips waiting for the GitHub release, which the demo,
not on GitHub, cannot have.) The pins are current again:

<<< @/examples/output/3-ecosystem/06/after.txt{console}

If a release fails, the train stops there and prints the `--from` command that resumes it.

::: tip What you learned
`fobis ecosystem release`, `--dry-run`, `--yes`, `--bump`, `--from`. The [ecosystem guide](/advanced/ecosystem)
covers the configuration and the safety rules in full.
:::

This is the end of the third track. The [fourth](../#tracks) comes back to `quad`, to look at its code.
