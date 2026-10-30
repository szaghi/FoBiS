---
title: 7. An fpm project
---

# 7. An fpm project

A colleague writes a report generator with fpm. The lab's index serves them too: `fobis add`, run in a project with
an `fpm.toml` and no fobos, writes into `fpm.toml`, and fpm fetches and builds the package.

<<< @/examples/tutorial/7-packages/07-fpm/report/fpm.toml{toml}

<<< @/examples/tutorial/7-packages/07-fpm/report/app/main.f90{fortran}

## What fpm can use

fpm builds only packages that have an `fpm.toml`. The index says which ones do:

<<< @/examples/output/7-packages/07/search.txt{console}

## Add, build, remove

<<< @/examples/output/7-packages/07/add.txt{console}

<<< @/examples/output/7-packages/07/manifest.txt{console}

<<< @/examples/output/7-packages/07/run.txt{console}

A package without an `fpm.toml` at that version is refused, with the build systems it has:

<<< @/examples/output/7-packages/07/fobis-only.txt{console}

<<< @/examples/output/7-packages/07/cmake-only.txt{console}

<<< @/examples/output/7-packages/07/remove.txt{console}

- **The newest tag is pinned exactly:** fpm takes a `tag`, a `rev` or a `branch`, not a range. `fobis add NAME
  --force` moves to a newer one, `--tag` chooses another, `--dev` writes into `[dev-dependencies]`.
- **The name is the package's own:** fpm requires the dependency's key to be the `name` of the package's
  `fpm.toml`, so `add` reads it there and refuses `--as`.
- **fpm does the rest:** the package's own dependencies, its build and its lock are fpm's. `transitive`, `fetch`,
  `fobos.lock`, mirrors and `audit` are FoBiS's and do not apply.
- **A project with both a fobos and an `fpm.toml`** gets its fobos edited; `--fpm` chooses `fpm.toml`.

*This chapter needs fpm; its outputs are recorded where fpm is installed.*

::: tip What you learned
`fobis search --build fpm`, `fobis add` and `remove` in an fpm project, why a package needs an `fpm.toml` for fpm.
Reference: [fpm projects](/cookbook/packages#fpm-projects).
:::

This is the end of the packages track. The [tutorials](../) list the other tracks; the
[cookbook](/cookbook/packages) has a recipe for every package task.
