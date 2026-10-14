---
title: 1. An ecosystem
---

# 1. An ecosystem

Libraries rarely live alone: a portability layer feeds a string library, which feeds a parser, which feeds your
application, each in its own repository with its own tags and CI. When one changes, the others must follow, in the
right order. `fobis ecosystem` treats such a family of FoBiS projects as a whole.

This track uses a small family that the documentation can build for you, three projects with history, tags, fetched
dependencies and git remotes, all private to one directory:

```bash
bash docs/demo/ecosystem-demo/setup.sh ~/eco    # the script is in the FoBiS repository
source ~/eco/env.sh                             # its registry, and its github.com/demo URLs resolved locally
cd ~/eco
```

<<< @/examples/output/3-ecosystem/01/ls.txt{console}

`core` is a small library; `mathx` uses it; `app` uses both. Each declares its dependencies the usual way, in its
fobos (`fobis fetch` cloned them into `third_party/`):

<<< @/examples/output/3-ecosystem/01/deps.txt{console}

## Registering the projects

The ecosystem is a list of projects in your user configuration (`~/.config/fobis/config.ini`, here the demo's):
`root`, the directory that holds them, and `projects`. `discover` lists the FoBiS projects under the root not
registered yet; `add` registers them:

<<< @/examples/output/3-ecosystem/01/discover.txt{console}

<<< @/examples/output/3-ecosystem/01/add.txt{console}

## The graph

FoBiS reads every project's `[dependencies]` and orders them: a project comes after everything it uses.

<<< @/examples/output/3-ecosystem/01/graph.txt{console}

The release order is the order in which every command of the next chapters acts. A cycle between projects is reported
as an error.

::: tip What you learned
The registry (`[ecosystem] root` and `projects`), `discover`, `add`, `graph`. Reference:
[`ecosystem`](/reference/ecosystem).
:::

Next: [2. The dashboard](./02-dashboard).
