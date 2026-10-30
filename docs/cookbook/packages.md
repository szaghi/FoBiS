---
title: Packages and indexes
---

# Packages and indexes

A package is a Fortran project anyone can use by name: its source lives at a URL (a git repository on any host, or a
directory of release archives on any web server), and package indexes list it. There is no central server. An index
is a small file that a person, a lab, a vendor or a committee publishes wherever it likes, and FoBiS reads several of
them side by side. Indexes help you find a package; they never decide what your build uses.

How it works:

1. **An index lists sources, not versions.** An entry holds the package's source URL (its identity), a description,
   keywords and the modules it provides. Versions come from the source itself: a git repository's semantic-version
   tags, or a release manifest. Tagging a release is publishing it.
2. **A name is resolved once.** `fobis add NAME` looks the name up in your indexes and writes the source URL into
   the fobos `[dependencies]`. `fetch` and `build` never read an index: if every index disappears, the project still
   builds. A name found in two indexes is refused, with the `INDEX:NAME` choices.
3. **Content is identified by hashes.** The lock records each git dependency's tree hash and each release archive's
   sha256. A tag that moves is reported, and a release whose archive changes is refused.
4. **Packages are built with your compiler.** `fobis pkg install` builds from source and files the result under a
   toolchain key (compiler family, version, and a digest of the compiler's path, MPI and flags), because module
   files work only with the compiler that wrote them.

Tutorial: [quad as a package](/tutorial/growing/08-packages). Reference: [`index`](/reference/index-command),
[`search`](/reference/search), [`info`](/reference/info), [`add`](/reference/add), [`publish`](/reference/publish),
[`pkg`](/reference/pkg), [`audit`](/reference/audit).

## Find a package

Register an index, then search it by words or by the module you need. [fortran-index](https://github.com/szaghi/fortran-index)
is a public index of FoBiS and fpm packages, with a browsable [catalogue of packages and
modules](https://szaghi.github.io/fortran-index/packages/):

```bash
fobis index add szaghi https://github.com/szaghi/fortran-index
```

The outputs below come from the tutorial's own index:

```bash
fobis index add mine ~/my-index
fobis search --module quad_rules
fobis info quad
```

<<< @/examples/output/2-growing/08/index-add.txt{console}

<<< @/examples/output/2-growing/08/search.txt{console}

`fobis info` reads the source, not the index: the versions are the source's tags, the modules those of its newest
version.

<<< @/examples/output/2-growing/08/info.txt{console}

- **Indexes come in priority order.** The project fobos's `[indexes]` are searched first, then those of your user
  configuration. Indexes that an index `follows` are searched too, two levels deep by default (`--depth`).
- **Remote indexes are cached** in `~/.fobis/indexes` (`FOBIS_INDEX_DIR` moves it); `fobis index update` or
  `--refresh` fetches them again. `fobis index list` shows each index with its scope (project or user) and when it
  was fetched; `fobis index remove NAME` forgets one.
- **`search` matches names, descriptions and keywords**; `--module` matches the modules of each package's newest
  version, as the index lists them, and `--build fpm` (or `fobis`, `cmake`, `make`) keeps the packages built with
  that build system.
- **A followed index is named by its own `name`** (`mylab:kinds`), with a short suffix when two followed indexes
  share a name: `fobis search` prints the qualified names to use.
- **Private indexes:** a git index is read with your git credentials (an SSH URL, a credential helper), like any
  clone. A static HTTP index must be public.
- **`fobis index add` reads the index once** to check it; `--no-check` registers it without reading it (offline).

## Add a dependency by name

```bash
fobis add quad
fobis add vendor:json --use fobos
fobis add --module stringifor_string_t
fobis add https://github.com/szaghi/PENF --tag v2.0.1
```

<<< @/examples/output/2-growing/08/add.txt{console}

<<< @/examples/output/2-growing/08/dependencies.txt{ini}

- **The range starts at the newest version** (`semver=^0.1.0`); `--semver`, `--tag`, `--rev` or `--branch` choose
  otherwise. A source with no version tag is added unpinned, with a warning.
- **A URL needs no index at all:** `fobis add URL` reads the source's tags and writes the same kind of entry.
- **Options of the entry:** `--as NAME` names the dependency in the fobos (default: the package's name, lower-case),
  `--dev` makes it [test-only](./dependencies), `--use fobos` builds it as a library from its own fobos (`--mode`
  chooses its mode), and `--force` replaces an entry of the same name.
- **What the index knows is copied:** its `mirrors` become `:: mirror=URL[,URL]`, and its recipe is copied into the
  project (see [CMake, make and other packages](#cmake-make-and-other-packages)).
- **The fobos is edited line by line:** its comments and layout are kept, and a comment line records the index the
  name came from.
- **In a FoBiS project** `add` writes into the fobos, and the package added can be built with FoBiS, fpm, CMake or
  make: see [how a dependency is built](#how-a-dependency-is-built). In an fpm project it writes into `fpm.toml`: see
  [fpm projects](#fpm-projects).

## Update or remove a dependency

```bash
fobis fetch --update
fobis add quad --semver "~0.2" --force
fobis remove quad
```

- **`fetch --update` moves within the range** written in the fobos (`semver=^0.1.0`: the newest 0.x.y), and records
  what it chose in `.fobis_deps/fobos.lock`. A `tag=` or `rev=` pin never moves.
- **To change the range, add the package again** with `--force`: the entry is replaced, the rest of the fobos kept.
- **`fobis remove NAME`** takes the entry out of the fobos, with its `add` comment and the recipe `add` copied for it.
  The next `fetch` drops it from the build; its clone stays in `.fobis_deps/NAME` until you delete it.
- **`fetch --frozen`** checks every dependency out at its locked commit, for a checkout that keeps `.fobis_deps/`
  (see [dependencies](./dependencies)).

## fpm projects

In a project with an `fpm.toml` and no fobos, `add` and `remove` edit `fpm.toml` (`--fpm` chooses it when the
project has both). The index finds the package; fpm fetches and builds it:

```bash
fobis search --build fpm json
fobis add M_CLI2
fpm build
fobis remove M_CLI2
```

```toml
[dependencies]
# added by fobis add from index szaghi
M_CLI2 = { git = "https://github.com/urbanjost/M_CLI2", tag = "1.0.0" }
```

- **The newest tag is pinned exactly:** fpm takes a `tag`, `rev` or `branch`, not a range, so `--semver` is refused.
  To move to a newer version, add the package again with `--force`. `--dev` writes into `[dev-dependencies]`.
- **The name is the package's own:** fpm requires the dependency's key to be the `name` in the package's `fpm.toml`,
  so `add` reads it there (urbanjost's `M_change` repository is `M_match`) and refuses `--as`.
- **The package must have an fpm.toml at that version:** fpm builds nothing else. A package with only a fobos, a
  CMake or make build, or published as release archives is refused, with the build systems it has.
- **fpm does the rest:** the package's own dependencies, its build and its lock are fpm's; `transitive`, `fetch`,
  `fobos.lock` and the module-collision check are FoBiS's and do not apply. An index entry's `mirrors` cannot be
  written (fpm has none).
- **Comments and layout of `fpm.toml` are kept:** an entry is one line. An entry you wrote as a
  `[dependencies.NAME]` table, or over several lines, is left to you.

## Publish your package in an index

An index is a file named `index.toml`. Keep it in a git repository, serve it as a static file, or keep it in a
directory. `fobis publish --index` adds or refreshes the entry of the current project:

```bash
fobis publish --index ~/my-index/index.toml --source https://github.com/me/quad
```

<<< @/examples/output/2-growing/08/index.txt{console}

To publish a whole family of projects, list them in a seed index (each entry needs only its `source`), or take the
projects of your [ecosystem](./ecosystem); `index build` fills the descriptions, licences and modules from each
source:

```bash
fobis index build seeds.toml -o index.toml
fobis index build --from-ecosystem --name me -o index.toml
fobis index check index.toml --online
```

- **The file format** is described in [Index format](/reference/index-format). `publish --index` and `index build`
  rewrite the whole file, sorted by name: comments of a hand-written index are lost.
- **`--from-ecosystem` publishes only public repositories.** It writes the HTTPS form of each origin and reads every
  source without your credentials: a private repository is left out, with a warning.
- **Hand-written fields win** when an index is built again (a description, the `provides` list), and an index can
  `follow` other indexes: `follows = ["https://example.org/fortran/index.toml"]`.
- **The provided modules are read from the sources**: for an fpm package its library directory (`[library]
  source-dir`, `src/` by default), for the others the whole tree without tests, examples and vendored copies
  (`third_party/`, `vendor/`, ...). A package that bundles another one's sources in its library really defines those
  modules too: the two cannot be linked into one program, and `fetch` says so.

## An index for a lab, a company or a project

Anyone can publish an index, and a project can name the indexes it relies on:

```ini
[indexes]
# a git repository holding index.toml
lab = https://git.example.org/fortran/index
# a static file
vendor = https://example.org/fortran/index.toml
# a directory, relative to this fobos
local = ./third-party-index
```

The same section in the user configuration (`~/.config/fobis/config.ini`) lists your own; `fobis index add` and
`remove` edit it. Ambiguous names are never resolved silently: with `json` in two of them, `fobis add json` fails
and asks for `lab:json` or `vendor:json`.

## Releases on any static host

`fobis publish --archive DIR` writes the tarball of the latest tag and its entry in `fortran-releases.toml`:

<<< @/examples/output/2-growing/08/archive.txt{console}

<<< @/examples/output/2-growing/08/manifest.txt{console}

Upload `DIR` to any web server, object store or shared directory; its URL is then a source like a git repository:

<<< @/examples/output/2-growing/08/static.txt{console}

```ini
[dependencies]
kinds = https://example.org/fortran/kinds/ :: semver=^1.0
```

- **A published release never changes.** `publish --archive` refuses to rewrite a version, and `fetch` refuses an
  archive whose sha256 differs from the one it locked.
- **An older release:** `--version TAG` publishes that tag instead of the latest one; `--name` sets the package name
  when the fobos `[project]` has none.
- **The manifest is found** at the URL itself, at `URL/fortran-releases.toml` or at
  `URL/.well-known/fortran-releases.toml`.
- **A stable URL on your own domain:** an HTML page holding
  `<meta name="fortran-source" content="git https://host/group/repo">` sends FoBiS to the real source, so the code can
  move between hosts while the URL stays.

## Dependencies of dependencies

By default `fetch` reads your fobos only. With `transitive = true` it also reads the `[dependencies]` of each
dependency and fetches them:

<<< @/examples/tutorial/2-growing/08-packages/survey/fobos{ini}

<<< @/examples/output/2-growing/08/fetch.txt{console}

<<< @/examples/output/2-growing/08/lock.txt{console}

- **Each range is a minimum** (Minimal Version Selection): every package gets the highest of the minimum versions
  required anywhere, so the answer depends on the fobos files only, never on what was published since. A range that
  excludes the chosen version is an error naming both requirers.
- **An exact pin of your project wins** (`tag=`, `branch=`, `rev=`): a dependency's requirement it violates is a
  warning.
- **Test-only and path dependencies of a dependency are not followed**, nor the dependencies of a release-manifest
  source. The dependencies of an fpm package are fetched by fpm (see
  [how a dependency is built](#how-a-dependency-is-built)).
- **Two dependencies defining the same module** are reported by every `fetch` before anything compiles: they could
  not be linked into one program.

When a module is missing, `fobis check` and `fobis build --explain` name the package of your indexes that provides
it, with the `fobis add INDEX:NAME` command that adds it (read from the cached indexes: no network).

## How a dependency is built

`fetch` builds each dependency with its own build system, using the compiler of your project's default mode, and
`build` links what it installed:

| The dependency has | It is built by |
|---|---|
| a `recipe=` (yours, or copied from an index by `add`) | the recipe |
| a fobos | FoBiS, as part of your project (`use=sources`) or as a library (`use=fobos`) |
| an `fpm.toml` and no fobos | fpm itself: `fpm build --profile release --compiler <your compiler>` |
| a `CMakeLists.txt` or a `Makefile` only | CMake or make (see [below](#cmake-make-and-other-packages)) |

An fpm package is installed into `.fobis_deps/.prefix/NAME`: its library archive and module files. Your build compiles
none of its sources and none of its programs.

- **fpm is required** for a dependency that has no fobos: without fpm on PATH, `fetch` fails and says so. FoBiS
  never compiles an fpm package itself.
- **Its own dependencies come with it:** fpm fetches what the package's `fpm.toml` requires and puts their objects
  in the package's archive. FoBiS does not see them: `fobos.lock` and `--frozen` pin the package, not what fpm
  fetched for it.
- **The same module twice is an error:** when your fobos also fetches a package that an fpm dependency brings with
  it, `fetch` names both and fails before anything compiles. Keep one of them.
- **Only the compiler is passed to fpm**, with the release profile and `-fPIC`: the module files are your compiler's.
  Your mode's other flags are not, so a flag changing the binary interface (`-fdefault-real-8`) does not reach an
  fpm dependency.
- **Examples and programs are not built:** fpm builds the library from a copy of the package whose manifest drops
  them, so a demo that does not compile cannot stop the library.

## Install a package for your compiler

```bash
fobis pkg install quad
fobis pkg install json-fortran --version ^9 --compiler intel_nextgen
fobis pkg list
fobis pkg upgrade
fobis pkg uninstall quad
```

<<< @/examples/output/2-growing/08/pkg.measured.txt{console}

Every library gets a pkg-config file, so a FoBiS, CMake or make project links it the same way:

<<< @/examples/output/2-growing/08/pkg-config.measured.txt{console}

```cmake
find_package(PkgConfig REQUIRED)
pkg_check_modules(QUAD REQUIRED IMPORTED_TARGET quad)
target_link_libraries(survey PkgConfig::QUAD)
```

From a make or CMake project of your own, `fobis pkg path` gives the directories to use:

```bash
export PKG_CONFIG_PATH=$(fobis pkg path quad --pkgconfig)
gfortran main.f90 $(pkg-config --cflags --libs quad)
```

- **Choosing what is built:** `--version` takes a range (`^9`) or an exact tag; `--compiler`, `--fc PATH` (a
  compiler binary), `--mpi` (the MPI wrapper), `--cflags` and `--lflags` set the toolchain; `--mode` picks the mode
  of a FoBiS package's fobos. `--force` rebuilds an installed package, `--verbose` shows the build's own output.
- **Several toolchains:** a package installed for two keys is chosen with `--key` by `pkg path` and `pkg uninstall`;
  `fobis pkg list` shows every key.
- **The pkg-config name is the library's**, not always the package's: `ls $(fobis pkg path NAME --pkgconfig)` lists
  the `.pc` files (stdlib installs one per component and `fortran_stdlib.pc` for all of them).
- **The store is `~/.fobis/pkgs/<key>/<name>/<version>/`** (`FOBIS_PKGS_DIR` moves it). Installing with other flags
  (`--cflags`, `--mpi`, another compiler) gives another key: both stay installed.
- **Applications are linked into `~/.local/bin`** (`--bin-dir`), never over a file that is not one of their links.
  Tests and examples are never installed.
- **`uninstall` removes exactly what the install wrote**, recorded in `receipts.json`. `upgrade` stays within the
  range you asked for and on the same toolchain.
- **FoBiS packages** are built in the mode of their fobos that uses your compiler family (a static library first),
  after `fobis fetch` of their own dependencies. **fpm packages** are built by fpm, which must be on PATH: the
  library first, then the applications with `fpm install` (an application that does not compile is a warning, the
  library stays installed).
- **Shared libraries:** the generated `.pc` files carry no run path (as usual for pkg-config). Link `--static`, or set
  `LD_LIBRARY_PATH` to the library directory.
- `fobis install REPO` is unchanged: it installs into a prefix and keeps no record.

## CMake, make and other packages

A package without a fobos or an fpm.toml is built from a recipe. The recipe is shipped by the package
(`fortran-recipe.toml` at its root) or named by an index entry (`recipe = "recipes/NAME.toml"`):

```toml
schema     = 1
backend    = "cmake"
cmake-args = ["-DENABLE_TESTS=OFF"]
depends    = ["https://github.com/szaghi/PENF :: semver=^2"]
```

`backend = "make"` takes `make-args`; `backend = "recipe"` takes `steps`, shell lines with the placeholders `{fc}`,
`{cc}`, `{fflags}`, `{lflags}`, `{prefix}`, `{jobs}`, `{src}` and `{build}`. Without any recipe, a `CMakeLists.txt`
or `Makefile` is used as found.

- **Your compiler is always passed** (`-DCMAKE_Fortran_COMPILER`, `FC=`): the module files must be its own.
- **`fobis add` copies an index's recipe into the project** (`recipes/NAME.toml`, `:: recipe=recipes/NAME.toml` in
  the spec), so that building never depends on the index.
- **In a FoBiS project**, `fetch` builds such a dependency with the compiler of the default mode into
  `.fobis_deps/.prefix/NAME`, and `build` adds its module directories and libraries.
- **Module files:** CMake installs none by default, and many Makefiles have no install rule. FoBiS then collects the
  libraries, module files and programs the build produced.
- **Install layouts vary.** Libraries, module files and `.pc` files are found wherever they were installed, and a
  package's `.pc` whose directories do not exist (json-fortran 9.3.1 installs one) is replaced by one FoBiS writes.
- **External libraries** (MPI, HDF5, BLAS) are never built: a recipe lists them in `externals`, and the package's own
  build finds them.

## Offline, or on a cluster

What needs a network, and what does not:

| Command | Network |
|---|---|
| `search`, `--module` hints of `check` and `build --explain` | no, once the indexes are cached |
| `info`, `add` | yes: they read the source's tags |
| `fetch` | yes, unless every dependency is already fetched |
| `build` | never: it reads `.fobis_deps/` |
| `pkg install` | yes: it reads and builds the source |

For a machine with no network at all, keep everything on a shared filesystem: an index in a directory
(`fobis index add lab /shared/fortran/index`), releases published with `publish --archive` into another directory,
and FoBiS itself as the single file `fobis.pyz` attached to each GitHub release (`python3 fobis.pyz build`). Those
directories are sources like any URL: `add`, `fetch` and `pkg install` read them without a network.

## Scripts and agents

`search`, `info`, `add`, `remove`, `index list`, `index check`, `pkg install`, `pkg list` and `audit` print JSON with
`--json`, and only JSON on stdout. An AI agent connected to [`fobis mcp`](./ai-setup) has three read-only tools for
packages: `package_search`, `package_info` and `index_check`.

## Trust: locks, mirrors, advisories, archives

```ini
[dependencies]
penf = https://github.com/szaghi/PENF :: tag=v2.0.1 :: mirror=https://gitlab.com/me/PENF :: archive=swh
```

```bash
fobis audit
fobis audit --witness
```

<<< @/examples/output/2-growing/08/audit.txt{console}

- **Mirrors** (`mirror=URL[,URL]`) are cloned in order when the source fails. A mirror needs no trust: the lock's
  tree hash checks what it serves.
- **Advisories have no central database.** A package publishes `fortran-advisories.toml` on its default branch, and
  `fobis audit` reports those affecting the versions your lock records (exit 1):

  ```toml
  # an example, for a fictitious package
  schema = 1
  [[advisory]]
  id       = "KINDS-2026-001"
  affected = "<1.1.0"
  severity = "high"
  summary  = "wrong kind selected for 128-bit reals"
  url      = "https://example.org/kinds/issues/1"
  ```

- **Witnesses:** `fobis audit --witness` compares the commit each locked tag names at the source, at every mirror and
  in the lock. A disagreement means the tag was moved somewhere.
- **Software Heritage** (`archive=swh`): when the source and its mirrors are gone, `fetch` downloads the tag from
  Software Heritage. The copy is accepted only when its tree equals the one in the lock (Software Heritage names
  directories like git trees). It holds only what its last visit of the repository saw.
- **Advisories, witnesses and archives need a network**, and the advisory channel is only as good as the package's
  maintainers: this is the cost of having no central service.
