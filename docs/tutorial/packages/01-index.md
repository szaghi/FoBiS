---
title: 1. An index of your own
---

# 1. An index of your own

This track follows a lab that writes Fortran libraries and wants its people, and anyone else, to use them by name.
There is no package server to set up: each library is a git repository whose tags are its versions, and an index
is a small file listing where the libraries are. [Chapter 8 of the second track](/tutorial/growing/08-packages)
showed the idea on one project; this track goes through every part of it.

The lab has three libraries, each a git repository with a version tag: `kinds` (real kinds), `vectors` (small vectors,
using `kinds`) and `timer`. A vendor publishes another library also called `kinds`. In the sessions they live in
`~/remotes`, published by a small script; on a real host they would be URLs like `https://git.example.org/lab/kinds`.

## Seeds, then an index

The lab lists only where its libraries are, in a seed file. `kinds` gets keywords written by hand:

<<< @/examples/output/7-packages/01/seeds.txt{console}

`fobis index build` reads each source and fills the rest:

<<< @/examples/output/7-packages/01/build.txt{console}

<<< @/examples/output/7-packages/01/index.txt{console}

Descriptions and licences come from each library's fobos `[project]`, `provides` lists the modules of its newest
version, and `builds` its build systems. No version is written: the versions are the repositories' tags, read when
the libraries are used, so tagging a release is publishing it. Fields written by hand in the seeds (the keywords)
win when the index is built again.

## Check it

`fobis index check` validates an index, and `--online` also reads every source:

<<< @/examples/output/7-packages/01/check.txt{console}

It refuses a key it does not know, so a typo is caught where the index is written:

<<< @/examples/output/7-packages/01/typo.txt{console}

The commands that only read an index (`search`, `info`, `add`) ignore keys they do not know, with a note: a key
added by a newer FoBiS never breaks an older one.

## Use the index, and another one

An index is registered by name. A directory, a git repository or a static `index.toml` on a web server all work:

<<< @/examples/output/7-packages/01/add.txt{console}

The vendor's index lists its own `kinds`, and follows the lab's, so whoever uses the vendor's index finds the lab's
libraries too:

<<< @/examples/output/7-packages/01/vendor.txt{console}

<<< @/examples/output/7-packages/01/add-vendor.txt{console}

<<< @/examples/output/7-packages/01/list.txt{console}

Every package of every index, qualified by the index's name:

<<< @/examples/output/7-packages/01/search.txt{console}

The lab's index is registered directly and followed by the vendor's: it is read once. `kinds` is in both indexes,
from two different sources; the next chapter shows what that means when adding it.

::: tip What you learned
Seed indexes, `fobis index build`, `fobis index check` (`--online`), `index add`, `index list`, `follows`, qualified
names `INDEX:NAME`. Reference: [Index format](/reference/index-format), [`index`](/reference/index-command).
:::
