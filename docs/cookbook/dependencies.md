---
title: Dependencies
---

# Dependencies

A dependency is another Fortran project your sources `use`. The fobos declares it in `[dependencies]`, one line per
dependency: a git repository pinned to a tag, a branch, a commit or a version range, or a directory on this machine.
`fobis fetch` clones the repositories; `fobis build` then compiles them with your sources, or builds them as
libraries with their own fobos and links them.

How it works:

1. **Fetch.** `fobis fetch` clones each repository into `<deps_dir>/<name>/` (`.fobis_deps/` by default), checks out
   its pin, builds the `use=fobos` ones, and writes two files there: `.deps_config.ini`, read by the build, and
   `fobos.lock`, the commit each dependency resolved to.
2. **Build.** `fobis build` (and `fobis check`, `fobis doctests`) reads `.deps_config.ini`: a `use=sources`
   dependency (the default) joins the source scan and is compiled with your flags; a `use=fobos` one is rebuilt by
   its own fobos before your build, its module directory and library wired in. Path dependencies (`path=DIR`) are
   read from the fobos at every build and need no fetch.
3. **One level.** `fetch` reads your fobos only: the dependencies of a dependency are not fetched. Declare in your
   fobos everything your build compiles.

Tutorial: [dependencies](/tutorial/first-steps/05-dependencies), [a project that depends on
quad](/tutorial/growing/04-dependon). Reference: [`fetch`](/reference/fetch), [`tree`](/reference/tree),
[`install`](/reference/install).

## A dependency from GitHub, pinned

```ini
[dependencies]
penf = https://github.com/szaghi/PENF :: tag=v2.0.1
```

```bash
fobis fetch          # clone into .fobis_deps/penf, check out v2.0.1, write the lock
fobis build          # PENF's sources are compiled with yours
```

<<< @/examples/output/1-first-steps/05/fetch.txt{console}

<<< @/examples/output/1-first-steps/05/build.txt{console}

![fobis fetch clones the dependencies, fobis build compiles them](/gifs/07_fetch.gif)

*Recorded on a small demo project: `fobis fetch`, the generated `.deps_config.ini`, then `fobis build`.*

The specification is `name = SOURCE [:: option]...`; the name is the directory under `deps_dir`.

| Specification | Checks out |
|---|---|
| `URL` | the default branch |
| `URL :: branch=develop` | the branch's head |
| `URL :: tag=v2.0.1` | the tag |
| `URL :: rev=4cb9d32` | the commit |
| `URL :: semver=^2.0` | the newest tag satisfying the range (next recipe) |
| `user/repo` | `https://github.com/user/repo` |

- **Any git URL works as written:** `https://`, `ssh://`, `git@host:user/repo`, `file:///srv/git/lib` (a local
  repository). Only a value with neither `://` nor a leading `git@` is read as GitHub's `user/repo`.
- **Pin with `tag=` or `rev=`.** That is what makes every checkout (a colleague's, CI's) fetch the same code: the
  lock is not committed. A bare URL or a `branch=` follows the branch.
- **One pin per dependency:** two of `tag=`, `branch=`, `rev=` and `semver=` stop `fetch` with exit 2.
- **A dependency that fails fails the fetch:** a clone, an update, a checkout of the pin or a `use=fobos` build that
  fails is reported, the other dependencies are still fetched, and `fetch` ends with the list of failures and exit 1.
  A dependency that was not cloned keeps its previous lock entry, if any. A wrong specification exits 2.
- **A dependency already cloned is not cloned again:** `fetch` prints `already fetched` and checks out the pin, so a
  `tag=` changed in the fobos is applied by a plain `fobis fetch` when the tag existed at clone time. A tag made
  later needs `--update`.

## A version range

```ini
[dependencies]
penf   = https://github.com/szaghi/PENF :: semver=^2.0
stdlib = https://github.com/fortran-lang/stdlib :: semver=>=0.5,<1.0
```

`fetch` lists the remote's tags (`git ls-remote --tags`), checks out the newest one in the range and records it in
the lock as `resolved`. Later fetches in the same checkout use the locked tag without asking the remote; `--update`
resolves the range again.

| Range | Means |
|---|---|
| `^1.5` | `>=1.5.0, <2.0.0` |
| `~1.5.2` | `>=1.5.2, <1.6.0` |
| `>=1.0,<2.0` | both bounds (any of `>=`, `>`, `<=`, `<`, comma-separated) |
| `=1.5.0`, `1.5.0` | exactly that version |
| `*` | any version |

- **Tags are read as `[v]MAJOR[.MINOR[.PATCH]]`:** `v1.5` is `1.5.0`. Any other tag is ignored, pre-releases
  included: `v1.3.0-rc1` never satisfies a range.
- **No tag in range** stops `fetch` with exit 1 and lists the first 20 tags the remote has.
- **A fresh checkout resolves the range again,** and can get a newer tag than yours. Pin with `tag=` when every
  checkout must build the same code.

## Compile it with your sources, or build it as a library

```ini
[dependencies]
; compiled with your sources and your flags (use=sources is the default)
penf   = https://github.com/szaghi/PENF :: tag=v2.0.1
; built by its own fobos in its mode, its library linked
stdlib = https://github.com/fortran-lang/stdlib :: tag=v0.5.0 :: use=fobos :: mode=gnu
```

| | `use=sources` (default) | `use=fobos` |
|---|---|---|
| The dependency needs a fobos | no | yes |
| `fobis fetch` | clones | clones, then runs `fobis build [--mode MODE]` in it |
| `fobis build` | its directory joins your sources, unless a `src` path already covers it | rebuilds it first (up to date: nothing compiled), adds its `mod_dir` to the include path, links its library by full path |

- **`use=sources` takes your flags:** one compiler, one set of options for the whole program. It suits small,
  source-distributed libraries, and needs nothing from the dependency's fobos.
- **`use=fobos` takes its own:** the dependency's mode must build a library (`mklib`, `output`); without `mode=`
  its default mode is used. Its directory is excluded from your source scan, so nothing is compiled twice.
- **`fetch --no-build`** only defers the build: the next `fobis build` builds a `use=fobos` dependency anyway.
- **A `use=fobos` dependency builds with its own fobos, in its own directory:** if that fobos declares dependencies
  from git, they are looked for in the clone's own `.fobis_deps/`, which nothing fetches. Declare such a library's
  dependencies in your fobos and use it with `use=sources`, or fetch inside its clone.
- **`mode=` without `use=fobos` does nothing:** your mode compiles a `use=sources` dependency.

The same wiring without `[dependencies]`, for a project already on disk, is the mode key `dependon`: see
[Libraries and other build systems](./libraries).

## Another project on this machine

```ini
[dependencies]
; its sources compiled with yours
utils = path=../utils
; built by its own fobos, its library linked
core  = path=../core :: use=fobos :: mode=static
```

Nothing to clone, tag or publish. Every `build`, `check` and `doctests` reads path dependencies from the fobos, so an
edit in `../utils` is recompiled at the next `fobis build`, and `../core` is rebuilt by its own fobos first.

- **The directory is relative to the fobos that declares it** (absolute paths and `~` work too). A missing
  directory stops `fetch`, `build` and `check` with exit 1.
- **No pin:** the directory is used as it is. `tag=`, `branch=`, `rev=` or `semver=` stop with exit 2.
- **A `use=sources` directory is scanned without** its `.git`, `.fobis`, its own `deps_dir` and the `build_dir` of
  its fobos modes. Its own dependencies are not taken from it: declare them in your fobos (two copies of a module
  would clash).
- **`fobis fetch` is optional:** it checks the directories, builds the `use=fobos` ones (unless `--no-build`) and
  records their state in the lock. `--frozen` reports a path dependency that changed since as a warning, never an
  error: it is expected to change.

<<< @/examples/output/2-growing/04/touch.txt{console}

*`dependon` on a sibling project: an edit there is rebuilt first. A `path=` dependency with `use=fobos` does the same.*

## A monorepo

```text
repo/
├── libs/core/   fobos (mode lib), src/
├── libs/utils/  src/
└── apps/solver/ fobos, src/
```

```ini
; apps/solver/fobos
[dependencies]
utils = path=../../libs/utils
core  = path=../../libs/core :: use=fobos :: mode=lib
```

Build from `apps/solver/`: the dependency paths are relative to the fobos, a mode's `src` to the current directory.
In the lock, both entries record the repository's commit and whether their own directory has uncommitted changes.

## A testing framework for the tests only

```ini
[dependencies]
penf       = https://github.com/szaghi/PENF :: tag=v2.0.1
test-drive = https://github.com/fortran-lang/test-drive :: tag=v0.6.1 :: dev
```

```bash
fobis fetch            # fetched with the others
fobis test             # the test builds use it
fobis fetch --no-dev   # a production checkout: not fetched
```

- **Used by `fobis test`, `fobis doctests` and `fobis check` only.** Every other build leaves it out, even when its
  sources contain the dependency's directory (`src = ./`): it never ends up in a library, an install or a program.
- **`--no-dev` keeps its lock entry,** and a clone fetched earlier stays marked test-only, so no other build
  compiles it.
- **Projects using yours never fetch it:** `fobis tree` marks it `[test only]` and does not show a dependency's
  test-only dependencies.
- **A build of every program** (a mode without `target`) whose sources include test programs using it fails: give
  the mode a `target`, or keep the test directory out of its sources. More in [Testing](./testing).

## Update, or go back to the lock

```bash
fobis fetch --update     # git fetch in each clone, move to the newest commit its pin allows, rewrite the lock
fobis fetch --frozen     # check every dependency out at the commit of the lock; leave the lock as it is
fobis fetch --no-build   # clone or update only; use=fobos dependencies are built by the next fobis build
```

`--update` moves a `branch=` dependency to the remote branch's head (fast-forward), an unpinned one to its upstream
head, resolves `semver=` ranges again, and makes newly created tags available; a `tag=` or `rev=` pin stays where it
is. To move a pinned dependency, change the pin in the fobos: that is the change to commit.

`--frozen` refuses to run without a lock (exit 1), uses the locked tag of a `semver=` range without asking the
remote, and never rewrites the lock. A dependency the lock does not list is fetched as usual.

<<< @/examples/output/1-first-steps/05/frozen.txt{console}

- **`--frozen` is for a checkout that keeps its `deps_dir`:** a workstation, a cluster account, a CI job caching
  `.fobis_deps/`. A fresh checkout has no lock: run `fobis fetch`, and rely on the fobos's pins.
- **A plain `fetch` compares each clone with the lock** and warns, never fails, when its commit differs (a clone
  moved by hand, a pin changed in the fobos):
  `Warning: dependency 'penf' HEAD (...) does not match fobos.lock (...). Run 'fobis fetch --update' to refresh.`
  The lock is then rewritten with the new commit.

## The lock file

<<< @/examples/output/1-first-steps/05/lock.txt{console}

One section per dependency: `url`, `commit` (the clone's `HEAD`), `sha256` (of `git archive HEAD`: the committed
content), the pin as declared, `resolved` for a `semver=` range, `dev = true` for a test-only one. A path dependency
records `path` and, in a git checkout, the `commit` holding it and `dirty` (tracked changes or untracked sources
under the directory), else a `sha256` of its source files.

- **The lock lives in `deps_dir` and is not committed.** It records what this checkout fetched, so that `fetch` can
  tell when a clone moved and `--frozen` can put it back. Reproducibility across checkouts comes from the pins.
- **Do not edit it:** every `fetch` but `--frozen` rewrites it.

## Where the dependencies go

```ini
[dependencies]
deps_dir = vendor
penf     = https://github.com/szaghi/PENF :: tag=v2.0.1
```

`deps_dir` (default `.fobis_deps`) holds the clones, `.deps_config.ini` and `fobos.lock`. Keep it out of git; the
`.gitignore` of `fobis new` already does (`/.fobis_deps/`).

<<< @/examples/output/1-first-steps/05/deps.txt{console}

- **Set it in the fobos, not with `--deps-dir`.** `fobis fetch --deps-dir DIR` clones into DIR, but `build`,
  `check`, `doctests` and `tree` read the fobos's `deps_dir` only: with the option alone, the build does not see the
  dependencies.

## See the dependency tree

```bash
fobis tree             # the whole tree
fobis tree --depth 1   # direct dependencies only
fobis tree --no-dedupe # repeat a dependency met twice instead of marking it
fobis tree --json      # name, spec, version, fetched, has_fobos, duplicate, dev, path, dependencies
```

<<< @/examples/output/1-first-steps/05/tree.txt{console}

The root is `[project] name` and its version; each node is the dependency's name, its version (the clone's
`[project] version` or latest tag, else the pin) and its specification. A fetched dependency with a fobos is read for
its own `[dependencies]`.

| Mark | Means |
|---|---|
| `[not fetched — run fobis fetch]` | no directory under `deps_dir` |
| `[directory DIR not found]` | a path dependency whose directory is missing |
| `[no fobos — cannot read transitive deps]` | its dependencies are unknown |
| `(*) [already shown]` | met earlier in the tree; children not repeated |
| `[test only]` | a `:: dev` dependency of yours |

- **A dependency's dependencies are looked for in your `deps_dir`, by name:** they show `[not fetched]` unless your
  fobos declares them too, since `fetch` does not follow them.
- **The same view, as facts:** `fobis check` lists the path dependencies, and `fobis introspect --dependencies`
  prints every dependency with its use, directory, pin and locked commit as JSON.

## How the build finds the fetched dependencies

`.deps_config.ini`, written by every `fetch`, holds four keys of space-separated entries: `src` (the `use=sources`
clones), `dependon` (`<clone>/fobos[:MODE]` of the `use=fobos` ones) and their test-only twins `dev_src` and
`dev_dependon`. Path dependencies are not in it.

- **`src` entries** join the mode's sources, unless a source path already contains them (`src = ./` does).
- **`dependon` entries** join the mode's `dependon`, and their directories its `exclude_dirs`: the dependency is
  built once, by its fobos, never scanned as your source.
- **The `dev_` keys** are used by `fobis test`, `doctests` and `check`; any other build excludes their directories.
- **Fetch again after editing `[dependencies]`:** for repositories the build reads `.deps_config.ini`, not the fobos.

## Install a project from GitHub

```bash
fobis install szaghi/FLAP --tag v2.0.0 --prefix ~/.local   # clone, build, copy
fobis install https://gitlab.com/user/tool --mode release  # any git URL, a mode of its fobos
fobis install szaghi/FLAP --update --prefix ~/.local       # git fetch in the cached clone first
fobis install szaghi/FLAP --no-build                       # clone only
```

`fobis install REPO` clones into `~/.fobis/<repo>/` (`--deps-dir` elsewhere; reused by later runs), checks out
`--tag`, `--branch` or `--rev`, runs `fobis build --track-build [--mode MODE]` there, and copies what the build
tracked: programs to `<prefix>/bin/`, libraries to `<prefix>/lib/`, their module files to `<prefix>/include/`
(`--bin`, `--lib`, `--include` rename them; the prefix defaults to `./`). Without `REPO`, `fobis install` copies your
own tracked build: see [Libraries](./libraries).

![a tracked build installed to a prefix](/gifs/06_install.gif)

*The local form: `fobis build --tb`, then `fobis install --prefix ./local`. The GitHub form ends with the same copy.*

- **The project needs a fobos** whose mode (`--mode`, else its default) builds what you want installed;
  `--track-build` is passed by the command.
- **The local fobos is not read:** `--mode` names a mode of the repository's fobos, wherever you run the command.
- **An installed project is yours to manage:** nothing records it, and `fetch` is the tool for build-time
  dependencies of a project.
- **A failure exits 1:** a clone or build that fails, or a build that tracked nothing to install
  (`No installable artifacts found`), ends the command with the list of failures and exit 1.

## A cluster without internet

FoBiS itself: `make standalone` in a FoBiS checkout writes `dist/fobis.pyz`, one file holding FoBiS and its Python
dependencies (every GitHub release carries it too). It needs Python 3.10 or newer, nothing else.

```bash
# on a machine with network
fobis fetch
rsync -a --exclude build/ myproject/ cluster:myproject/   # with .fobis_deps/ and the sibling path dependencies
scp dist/fobis.pyz cluster:

# on the cluster
cd myproject
python3 ~/fobis.pyz build --mode release
python3 ~/fobis.pyz fetch --frozen       # optional: puts every clone back at its locked commit, offline
```

- **The build needs no network:** `.deps_config.ini` and the lock hold paths relative to the project, and a
  `use=fobos` dependency is rebuilt by the same `fobis.pyz` (no `fobis` on the PATH needed).
- **`fetch` without network** works for clones already present: plain `fetch` checks out the pins, `--frozen` the
  locked commits. `--update`, a new clone, and a `semver=` range without a lock need the remote.
- **Path dependencies** must be copied to the same place relative to the project.
- **Mirrors instead of copies:** keep bare clones on the cluster and let git rewrite the URLs, so the fobos stays
  unchanged:

  ```bash
  git config --global url."file:///shared/mirrors/".insteadOf https://github.com/
  ```

More on clusters in [HPC and clusters](./hpc).

## For CI and agents

```bash
fobis fetch --json
fobis tree --json
fobis introspect --dependencies
```

`fetch --json` runs the same fetch as `fobis fetch` (semver ranges, `--frozen`, `--no-dev`, the lock) and prints one
document: `status`, `deps_dir`, `dependencies`, `failures` (one line per dependency that could not be cloned, checked
out at its pin or built) and `errors` (the messages); its exit status is the plain fetch's.

- **Cache `.fobis_deps/`** between CI runs keyed on the fobos, and run `fobis fetch --frozen` on a cache hit. More in
  [Continuous integration](./ci).
