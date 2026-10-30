---
title: 5. Trust without a central server
---

# 5. Trust without a central server

A central package registry gives three guarantees: the package is still there tomorrow, its versions never change,
and known security problems are announced. Without a registry, the same guarantees come from content hashes in the
lock, mirrors, advisories published by each package, and several copies that can be compared.

## A mirror

The lab mirrors `kinds` and says so in its index. `add` copies the mirror into the fobos with the source:

<<< @/examples/output/7-packages/05/entry.txt{console}

<<< @/examples/output/7-packages/05/add.txt{console}

The source goes down, and a fresh clone is needed. The versions are listed from the mirror, and the clone comes from
it:

<<< @/examples/output/7-packages/05/mirror.txt{console}

A mirror needs little trust: the lock recorded the tree hash of each version's content, and a tag that names other
content is reported when it is fetched (a release archive whose sha256 changed is refused). The clone keeps the source as its origin: once the source is back, updates come from it.

## Advisories

`kinds` publishes advisories about its own versions in a file on its default branch, `fortran-advisories.toml`:

<<< @/examples/tutorial/7-packages/05-trust/fortran-advisories.toml{toml}

`fobis audit` reads the advisories of every dependency for the version the lock records:

<<< @/examples/output/7-packages/05/advisories.txt{console}

The lab publishes the fix as 1.1.1. `fetch --update` does not take it:

<<< @/examples/output/7-packages/05/still.txt{console}

With `transitive = true` the versions are chosen by minimal version selection: 1.1.0 is still the lowest version
every range accepts. The project states what it needs, by raising its minimum:

<<< @/examples/output/7-packages/05/raise.txt{console}

## Witnesses

A tag can be moved after the fact, on the source or on a mirror, to point at other content. `--witness` compares,
for every locked tag, the commit the source and each mirror name with the commit in the lock:

<<< @/examples/output/7-packages/05/witness.txt{console}

The mirror has not received 1.1.1 yet: it gives no testimony, which is not a disagreement. Once it is synchronised,
the copies agree:

<<< @/examples/output/7-packages/05/synced.txt{console}

Someone moves the tag on the mirror:

<<< @/examples/output/7-packages/05/moved.txt{console}

Several independent copies agreeing replace a central checksum database: no single server has to be trusted, and a
change on one of them is seen by everyone who audits.

When the source and every mirror are gone, `:: archive=swh` lets `fetch` take the version from Software Heritage,
accepted only when its tree is the one in the lock (see the [cookbook](/cookbook/packages#trust-locks-mirrors-advisories-archives)).

::: tip What you learned
`mirrors` in an index and `:: mirror=` in a fobos, the tree hashes of the lock, `fortran-advisories.toml`,
`fobis audit`, raising a minimum under minimal version selection, `fobis audit --witness`. Reference:
[`audit`](/reference/audit).
:::
