---
title: 3. Versions
---

# 3. Versions

The lab improves `kinds`: version 1.1.0 adds a single-precision kind and changes nothing else, version 2.0.0 renames
the kinds after their digits. The versions are only git tags:

<<< @/examples/output/7-packages/03/versions.txt{console}

## Move within the range

`solver` asked for `kinds = ... :: semver=^1.0.0`: any 1.x.y from 1.0.0 on, never 2.0.0, which may break it.
`fetch --update` moves to the newest version within the range:

<<< @/examples/output/7-packages/03/update.txt{console}

The lock records what was checked out, with the commit and the tree hash of its content:

<<< @/examples/output/7-packages/03/locked.txt{console}

## Cross the range, deliberately

A new range is written by adding the package again, with `--force`:

<<< @/examples/output/7-packages/03/major.txt{console}

After `fetch --update`, 2.0.0 is checked out, and `vectors`, still written for the old names, no longer compiles:

<<< @/examples/output/7-packages/03/broken.txt{console}

That is what a new major version means. `solver` goes back to the 1.x range:

<<< @/examples/output/7-packages/03/back.txt{console}

## What the dependencies require

`vectors` 0.2.0 requires `kinds` 1.1.0 or newer in 1.x. `solver` moves to `vectors` 0.2.0 and lets `fetch` read
what its dependencies require, with `transitive = true`:

<<< @/examples/output/7-packages/03/transitive.txt{ini}

<<< @/examples/output/7-packages/03/resolved.txt{console}

<<< @/examples/output/7-packages/03/required.txt{console}

`solver` asks for `kinds` 1.0.0 or newer, `vectors` for 1.1.0 or newer: `fetch` takes the highest of these minimums,
1.1.0, the lowest version that satisfies both, not the newest one. This is minimal version selection: the answer
depends only on the fobos files, so it is the same tomorrow, whatever `kinds` publishes meanwhile.

<<< @/examples/output/7-packages/03/run.txt{console}

A range no version can satisfy is an error that names both sides:

<<< @/examples/output/7-packages/03/conflict.txt{console}

::: tip What you learned
Version tags, `semver=^X.Y.Z` ranges, `fetch --update`, `fobis add --semver --force`, the lock, major versions,
`transitive = true` and minimal version selection. Reference:
[versions and ranges](/cookbook/dependencies#a-version-range),
[dependencies of dependencies](/cookbook/packages#dependencies-of-dependencies).
:::

Next: [install for your compiler](./04-install).
