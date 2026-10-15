# Fetch Dependencies

The `fetch` command provides a declarative way to pull in GitHub-hosted Fortran projects as dependencies. It clones each repository, checks out the requested revision, and wires everything into the build automatically so that `fobis build` picks it all up.

## Quick start

1. Add a `[dependencies]` section to your fobos file:

```ini
[dependencies]
penf     = https://github.com/szaghi/PENF :: tag=v1.5.0
jsonfort = https://github.com/jacobwilliams/json-fortran :: branch=main :: use=fobos :: mode=gnu
```

2. Fetch dependencies:

```bash
fobis fetch
```

3. Build your project — dependencies are detected automatically:

```bash
fobis build
```

## Dependency specification syntax

```
name = URL [:: branch=X] [:: tag=X] [:: rev=X] [:: mode=X] [:: use=sources|fobos] [:: dev]
name = path=DIR [:: mode=X] [:: use=sources|fobos] [:: dev]
```

| Field | Description |
|---|---|
| `name` | Short identifier; also becomes the subdirectory name under `deps_dir` |
| `URL` | Git URL of the repository (`https://`, `ssh://`, `git@...`, `file://` for a local repository), or `user/repo` for GitHub |
| `path=DIR` | A local directory instead of a repository, relative to the fobos file's directory — see [local directories](#local-directories-path) |
| `branch=X` | Check out branch `X` |
| `tag=X` | Check out tag `X` |
| `rev=X` | Check out commit `X` |
| `mode=X` | fobos mode to use when building the dependency (only relevant for `use=fobos`) |
| `use=X` | Integration mode: `sources` (default) or `fobos` — see below |
| `dev` | A test-only dependency: used by `fobis test`, doctests and `check` only — see below |

Only one of `branch`, `tag`, or `rev` may be specified. Without any of these, the repository's default branch is used.

## Test-only dependencies (`:: dev`)

A testing framework, or fixtures shared by the tests, should not become part of the project. Mark such a
dependency `:: dev`:

```ini
[dependencies]
penf    = https://github.com/szaghi/PENF :: tag=v2.0.1
testkit = https://github.com/user/testkit :: tag=v1.0.0 :: dev
```

- `fobis fetch` fetches it like the others; `fobis fetch --no-dev` skips it (a production build), keeping its lock
  entry and leaving an earlier clone in place, still marked test-only.
- `fobis test` (its builds), `fobis doctests` and `fobis check` use it.
- Every other build leaves it out, even when its sources contain the dependency directory (`src = ./`): a library
  or program that uses one of its modules does not build, and it never ends up in a library, an install or a
  dependent project. A project using yours never fetches your test-only dependencies (`fobis tree` does not show
  them below the first level, and marks yours `[test only]`).
- A build of every program (a mode without `target`) whose sources include test programs using it needs it too:
  give the mode a `target`, or keep the test directory out of its sources.

## Local directories (`path=`)

A library developed next to its application, or the parts of a monorepo, are used where they are:

```ini
[dependencies]
; compiled with the project
utils = path=../utils
; built with its own fobos, linked as a library
core  = path=../core :: use=fobos
```

- The directory is relative to the fobos file's directory (absolute paths and `~` work too). It is used as it is,
  so a path dependency takes no `tag`, `branch`, `rev` or `semver`: `fetch` and `build` stop with exit 2 when one is
  given, and with exit 1 when the directory does not exist.
- **No fetch is needed.** Every `build` (and `check`, `doctests`) reads path dependencies from the fobos, so an edit
  of the fobos or of the directory takes effect at the next build: a changed source of a `use=sources` one is
  recompiled, a `use=fobos` one is rebuilt by its own fobos first, as `dependon` does.
- **`use=sources`** adds the directory to the source scan, without its `.git`, `.fobis`, its own fetched dependencies
  (`deps_dir` of its fobos, default `.fobis_deps`) and the `build_dir` of its fobos modes. Its own dependencies are
  not taken from it: declare in your fobos what it needs, as for a cloned dependency (two copies of a module would
  clash).
- **`fobis fetch`** checks the directory, builds a `use=fobos` one (unless `--no-build`) and records it in
  `fobos.lock`: the directory's commit and `dirty` state when it is in a git checkout (the state of the directory
  alone: tracked changes and untracked sources under it), a `sha256` of its source files otherwise. `--frozen` reports
  a path dependency that changed since the lock as a warning, never an error: such a dependency is expected to
  change.
- `:: dev` works as for a repository; `fobis tree`, `fobis check` and `fobis introspect --dependencies` show the
  path, the ecosystem dashboard shows `name at PATH` in its pins column, and `fobis fpm export` writes an fpm
  `path` dependency.

## Integration modes (`use=`)

Each dependency can be integrated in one of two mutually exclusive ways, controlled by the `use=` field.

### `use=sources` (default)

The dependency's source files are compiled **inline** with your project. FoBiS.py's recursive source scanner finds the Fortran files in the cloned directory and resolves `USE` statements automatically — no separate library build step is needed.

```ini
[dependencies]
penf = https://github.com/szaghi/PENF :: tag=v1.5.0
```

- **`fobis fetch`**: clone only, no pre-build
- **`fobis build`**: dep directory is added to the source scan (if not already covered by your existing `src` paths); no library is built or linked

This is the natural mode for small, source-distributed Fortran projects. No `fobos` file is required in the dependency.

### `use=fobos`

The dependency is built as a **separate library** using its own fobos file, and your project links against the result. This uses the `--dependon` mechanism internally.

```ini
[dependencies]
jsonfort = https://github.com/jacobwilliams/json-fortran :: branch=main :: use=fobos :: mode=gnu
```

- **`fobis fetch`**: clone + `fobis build` inside the dep directory
- **`fobis build`**: dep's fobos path is added to `--dependon`; the dep directory is added to `exclude_dirs` automatically to prevent source-scan overlap; the dep's `mod_dir` and built library are added to your project's include and link paths

The target repository **must** contain a `fobos` file.

### Choosing between the two modes

| | `use=sources` | `use=fobos` |
|---|---|---|
| Dep needs a `fobos` file | No | Yes |
| Dep pre-built during `fetch` | No | Yes |
| Compiled as part of your build | Yes (inline) | No (separate library) |
| Typical use | Small/header-like deps | Large deps or those requiring a dedicated build |

## The `deps_dir` fobos option

The directory where dependencies are cloned can be set directly in the fobos `[dependencies]` section, avoiding the need to pass `--deps-dir` on every invocation:

```ini
[dependencies]
deps_dir = vendor
penf     = https://github.com/szaghi/PENF :: tag=v1.5.0
```

The CLI `--deps-dir` flag takes precedence over the fobos value when both are given.

## Directory layout

After `fobis fetch`, the project directory contains:

```
.fobis_deps/
├── .deps_config.ini       ← auto-generated, read by fobis build
├── penf/                  ← use=sources: only cloned, not pre-built
│   ├── src/
│   └── ...
├── jsonfort/              ← use=fobos: cloned + built
│   ├── fobos
│   ├── src/
│   └── build/             ← built artefacts
```

`.fobis_deps/.deps_config.ini` records the two kinds of entries separately:

```ini
[deps]
dependon = .fobis_deps/jsonfort/fobos:gnu
src      = .fobis_deps/penf
```

`fobis build` reads this file: `dependon` entries are fed into the `--dependon` machinery (with the dep dir added to `exclude_dirs`); `src` entries are appended to the source search paths.

## `fetch` options

| Option | Default | Description |
|---|---|---|
| `--deps-dir DIR` | `.fobis_deps` | Where to clone dependencies (overrides `deps_dir` in fobos) |
| `--update` | `False` | Re-fetch and rebuild existing dependencies |
| `--no-build` | `False` | Clone only — skip building even for `use=fobos` deps |
| `--no-dev` | `False` | Skip the test-only (`:: dev`) dependencies |

## Typical workflows

```bash
# Initial setup
fobis fetch
fobis build

# Update all deps to latest
fobis fetch --update && fobis build

# Inspect before building
fobis fetch --no-build
ls .fobis_deps/

# Use a custom storage directory (or set deps_dir in fobos instead)
fobis fetch --deps-dir vendor/
```

## How auto-detection works

`fobis build` calls `_load_fetched_deps()` during initialisation. If `.deps_config.ini` exists:

- **`src` entries** are appended to `cliargs.src` when the dep directory is not already covered by an existing source path. The recursive scanner then finds and compiles the dep's Fortran files as part of your build.
- **`dependon` entries** are appended to `cliargs.dependon`, and the dep directory is added to `cliargs.exclude_dirs` to prevent the source scanner from also picking up those files. The `--dependon` machinery then rebuilds the dep if needed, adds its `mod_dir` to the include path, and links the built library.

## Error cases

| Situation | Behaviour |
|---|---|
| No `[dependencies]` section | Warning message, `fetch` exits cleanly |
| `use=fobos` dep without a `fobos` file | Error message identifying the dependency |
| git clone / fetch failure | Error message with git output |
| `path=DIR` that does not exist | Error naming the directory, exit 1 (`fetch`, `build`, `check`) |
| `path=DIR` with `tag`/`branch`/`rev`/`semver` | Error naming the dependency, exit 2 |
| Already cloned, no `--update` | Skip with "already fetched" message |

## Relation to `install`

`fetch` and `install` both use `git clone` + FoBiS to handle GitHub-hosted Fortran projects, but serve different purposes:

| | `fobis fetch` | `fobis install <repo>` |
|---|---|---|
| Purpose | Declarative multi-dep management | One-shot install of a single project |
| Configured via | `[dependencies]` in fobos | CLI arguments |
| Result | Wired into the build automatically | Artifacts copied to `--prefix` |

Use `fetch` when your project **depends on** other FoBiS libraries at build time. Use `install` when you want to install a FoBiS-based tool or library for your own use.

See the [GitHub Install](/advanced/install) advanced guide.

## Command reference

See [`fetch` command](/reference/fetch) for the full option reference.
