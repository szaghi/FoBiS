---
title: 3. Acting on every project
---

# 3. Acting on every project

`exec` runs a command in every project, in release order, and sums up:

<<< @/examples/output/3-ecosystem/03/exec.txt{console}

`--only core,mathx` restricts it, `--from mathx` resumes after a failure, `--fail-fast` stops at the first one. Any
command works, FoBiS's included:

<<< @/examples/output/3-ecosystem/03/build.txt{console}

## Following the dependencies

`fetch` runs `fobis fetch --update` in every project with dependencies, in release order, so a project is updated
after what it uses:

<<< @/examples/output/3-ecosystem/03/fetch.txt{console}

::: tip What you learned
`fobis ecosystem exec -- COMMAND` with `--only`, `--from`, `--fail-fast`; `fobis ecosystem fetch`.
:::

Next: [4. Before releasing](./04-check).
