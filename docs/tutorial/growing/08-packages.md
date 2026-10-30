---
title: 8. quad as a package
---

# 8. quad as a package

In [chapter 4](./04-dependon) another project used `quad` through a path to its fobos. That works on one machine.
To let anyone use `quad` by name, it becomes a package: a git repository with a version tag, listed in a package
index. No server is involved: an index is a small file you publish wherever you like, and FoBiS reads several of them
side by side.

## Publish quad in your own index

`quad` gets a git repository and its first tag, `v0.1.0`, and a copy stands in for its public remote
(`~/remotes/quad.git`). `fobis publish --index` adds the project to an index file, here a directory of yours:

<<< @/examples/output/2-growing/08/publish.txt{console}

<<< @/examples/output/2-growing/08/index.txt{console}

The entry holds the source URL and the modules `quad` provides, read from its sources. It holds no version: the
versions are the repository's tags, so tagging a release is publishing it.

## Find a package

`fobis index add` registers the index in your user configuration (a project fobos can name indexes too, in an
`[indexes]` section). Then the indexes are searched, by name, words or module:

<<< @/examples/output/2-growing/08/index-add.txt{console}

<<< @/examples/output/2-growing/08/search.txt{console}

`fobis info` reads the source itself: its versions, its build system and the modules of its newest version:

<<< @/examples/output/2-growing/08/info.txt{console}

## Use it by name

A new project, `survey`, compares the two rules of `quad` on the sine:

::: code-group

<<< @/examples/tutorial/2-growing/08-packages/survey/src/survey.F90{fortran} [survey/src/survey.F90]

<<< @/examples/tutorial/2-growing/08-packages/survey/fobos{ini} [survey/fobos]

:::

`fobis add quad` resolves the name through the indexes once, and writes the source URL into the fobos with a range
starting at the newest version:

<<< @/examples/output/2-growing/08/add.txt{console}

<<< @/examples/output/2-growing/08/dependencies.txt{ini}

From now on the fobos names the source, not the index: `fetch` and `build` never read an index, so the project keeps
building if the index disappears. A name found in two indexes is refused, with the `INDEX:NAME` choices.

`quad` itself depends on PENF. `transitive = true` makes `fetch` read the fobos of each dependency and fetch its
dependencies too, choosing for each package the highest minimum version required anywhere (Minimal Version
Selection: the same answer tomorrow, whatever is published meanwhile):

<<< @/examples/output/2-growing/08/fetch.txt{console}

<<< @/examples/output/2-growing/08/build.txt{console}

The lock records what each dependency resolved to and who required it:

<<< @/examples/output/2-growing/08/lock.txt{console}

## A release without git

Some users download releases instead of cloning. `fobis publish --archive` writes the tarball of the latest tag and
its entry in `fortran-releases.toml`, a manifest any static web server, object store or shared directory can serve:

<<< @/examples/output/2-growing/08/archive.txt{console}

<<< @/examples/output/2-growing/08/manifest.txt{console}

That directory is a source like a git repository: `fobis info`, `add` and `fetch` read its manifest, and `fetch`
checks every archive against its sha256:

<<< @/examples/output/2-growing/08/static.txt{console}

## Install it for your compiler

A library is only usable with the compiler that built its module files. `fobis pkg install` builds a package from
source with your compiler and files it under a toolchain key (compiler family, version, and a digest of its path and
flags), with a pkg-config file, so any build system can link it:

<<< @/examples/output/2-growing/08/pkg.measured.txt{console}

<<< @/examples/output/2-growing/08/pkg-config.measured.txt{console}

*Both outputs depend on the machine (the key names the compiler and its path).*

Finally, `fobis audit` reads the advisories each dependency publishes about its own versions (none here):

<<< @/examples/output/2-growing/08/audit.txt{console}

## A public index

Your index can list your packages and follow others. [fortran-index](https://github.com/szaghi/fortran-index) lists
public FoBiS and fpm projects ([catalogue](https://szaghi.github.io/fortran-index/packages/)): register it with
`fobis index add szaghi https://github.com/szaghi/fortran-index`, or follow it from yours with
`follows = ["https://github.com/szaghi/fortran-index"]`.

::: tip What you learned
`fobis publish`, `fobis index`, `fobis search`, `fobis info`, `fobis add`, `transitive = true`, `fobis pkg install`,
`fobis audit`. Reference: [Packages and indexes](/cookbook/packages).
:::

Next: [one fobos, many machines](./09-machines).
