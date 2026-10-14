---
title: 5. Shared boilerplate
---

# 5. Shared boilerplate

Every project of a family carries the same files besides its code: CI workflows, release and test scripts, the
documentation's configuration, the licence. `fobis scaffold` keeps them identical to FoBiS's templates (with each
project's name and URLs filled in), and the ecosystem checks them all:

<<< @/examples/output/3-ecosystem/05/status.txt{console}

A file a project must own (here each demo project's `release.sh`) is listed in the fobos `[scaffold] skip` and
never touched. A local edit to a managed file is drift:

<<< @/examples/output/3-ecosystem/05/drift.txt{console}

In the project, the file by file view:

<<< @/examples/output/3-ecosystem/05/project.txt{console}

`sync` shows each difference and asks before writing (`--yes` does not ask, `--dry-run` only shows):

<<< @/examples/output/3-ecosystem/05/sync.txt{console}

::: tip What you learned
`fobis scaffold status` and `sync`, `[scaffold] skip`, `fobis ecosystem scaffold status`. Reference:
[scaffold](/advanced/scaffold).
:::

Next: [6. The release train](./06-release).
