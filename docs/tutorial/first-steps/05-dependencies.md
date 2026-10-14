---
title: 5. Dependencies
---

# 5. Dependencies

`quad`'s program wants to print its best estimate with all the digits that matter, no more:
[PENF](https://github.com/szaghi/PENF)'s `str` does that. PENF is a FoBiS project on GitHub; the fobos declares it:

```ini
[dependencies]
penf = https://github.com/szaghi/PENF :: tag=v2.0.1
```

and names the project, which `fobis tree` and the ecosystem tools use:

```ini
[project]
name    = quad
version = 0.1.0
authors = Ada Fortran
```

The program now uses PENF:

<<< @/examples/tutorial/1-first-steps/05-dependencies/files/src/integrate.F90{6,17 fortran}

## Fetching

<<< @/examples/output/1-first-steps/05/fetch.txt{console}

`fobis fetch` cloned PENF into `.fobis_deps/` at the tag and recorded two files there:

<<< @/examples/output/1-first-steps/05/deps.txt{console}

`.deps_config.ini` tells `fobis build` where the fetched sources are: they are compiled with the project's, with
the project's flags (`use=sources`, the default). A dependency declared with `use=fobos` is instead built as a
library by its own fobos, and linked.

<<< @/examples/output/1-first-steps/05/build.txt{console}

FoBiS compiled the five PENF modules the program needs before the program, and `quad_rules`, changed by the doctests
of chapter 4, with `integrands`, which uses it. Files on the same line belong to the same level of the dependency tree.

<<< @/examples/output/1-first-steps/05/tree.txt{console}

## The lock file

<<< @/examples/output/1-first-steps/05/lock.txt{console}

The lock lives with the dependencies, in `.fobis_deps/`, and like them it is not committed: it is this machine's
record of the commit each dependency resolved to, and a checksum of its files. What makes another checkout fetch the
same code is the specification in the fobos (`tag=`, `rev=`). `fobis fetch --frozen` refuses to run without the lock
and checks every dependency against it:

<<< @/examples/output/1-first-steps/05/frozen.txt{console}

`fobis fetch --update` moves each dependency to the newest commit its specification allows and rewrites the lock.

## Specifications

| Specification | Resolves to |
|---|---|
| `URL` | the default branch |
| `URL :: branch=develop` | the branch's head |
| `URL :: tag=v2.0.1` | the tag |
| `URL :: rev=4cb9d32` | the commit |
| `URL :: semver=^2.0` | the newest tag that satisfies the constraint |
| `user/repo` | `https://github.com/user/repo` |

`:: mode=NAME` picks the dependency's fobos mode, `:: use=fobos` builds it as a library, and `:: dev` makes it
test-only: `fobis test` uses it, the builds of the program and of the library do not
([test-only dependencies](/advanced/fetch#test-only-dependencies-dev)).

::: tip What you learned
`[dependencies]`, `fobis fetch`, `.fobis_deps/`, the lock and `--frozen`, `fobis tree`. Reference:
[`fetch`](/reference/fetch), [`tree`](/reference/tree).
:::

This is the end of the first track: `quad` builds in two modes, as a library, with tests, doctests, coverage and a
dependency. [Growing a project](../growing/01-templates) takes it further.
