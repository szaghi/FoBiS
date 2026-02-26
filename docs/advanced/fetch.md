# Fetch Dependencies

The `fetch` command provides a declarative way to pull in GitHub-hosted Fortran projects as dependencies. It clones each repository, checks out the requested revision, builds it, and wires everything into the `-dependon` mechanism so that `FoBiS.py build` picks it all up automatically.

## Quick start

1. Add a `[dependencies]` section to your fobos file:

```ini
[dependencies]
stdlib   = https://github.com/fortran-lang/stdlib :: tag=v0.5.0 :: mode=gnu
jsonfort = https://github.com/jacobwilliams/json-fortran :: branch=main
utils    = https://github.com/user/fortran-utils :: rev=a1b2c3d
```

2. Fetch and build:

```bash
FoBiS.py fetch
```

3. Build your project — dependencies are detected automatically:

```bash
FoBiS.py build
```

## Dependency specification syntax

```
name = URL [:: branch=X] [:: tag=X] [:: rev=X] [:: mode=X]
```

| Field | Description |
|---|---|
| `name` | Short identifier; also becomes the subdirectory name under `.fobis_deps/` |
| `URL` | HTTPS Git URL of the repository |
| `branch=X` | Check out branch `X` |
| `tag=X` | Check out tag `X` |
| `rev=X` | Check out commit `X` |
| `mode=X` | fobos mode to use when building the dependency |

Only one of `branch`, `tag`, or `rev` may be specified. Without any of these, the repository's default branch (usually `main` or `master`) is used.

The target repository **must** contain a `fobos` file.

## Directory layout

After `FoBiS.py fetch`, the project directory contains:

```
.fobis_deps/
├── .deps_config.ini       ← auto-generated, read by FoBiS.py build
├── stdlib/
│   ├── fobos
│   ├── src/
│   └── build/             ← built artefacts from the dependency
├── jsonfort/
│   ├── fobos
│   └── ...
```

`.fobis_deps/.deps_config.ini` is a simple INI file:

```ini
[deps]
dependon = .fobis_deps/stdlib/fobos:gnu .fobis_deps/jsonfort/fobos:default
```

`FoBiS.py build` reads this file and extends its `-dependon` list before resolving the dependency graph.

## `fetch` options

| Option | Default | Description |
|---|---|---|
| `--deps-dir DIR` | `.fobis_deps` | Where to clone dependencies |
| `--update` | `False` | Re-fetch and rebuild existing dependencies |
| `--no-build` | `False` | Clone only, skip building |

## Typical workflows

```bash
# Initial setup: fetch and build all deps
FoBiS.py fetch

# Build your project (deps auto-detected)
FoBiS.py build

# Update all deps to latest
FoBiS.py fetch --update && FoBiS.py build

# Inspect before building
FoBiS.py fetch --no-build
ls .fobis_deps/

# Use a custom storage directory
FoBiS.py fetch --deps-dir vendor/
```

## How auto-detection works

`FoBiS.py build` calls `_load_fetched_deps()` during initialisation. If `.fobis_deps/.deps_config.ini` exists, the paths listed in its `dependon` key are appended to `cliargs.dependon`. The existing `-dependon` machinery then handles everything: rebuilds each sub-project if needed, adds its `mod_dir` to the include path, and links the built library.

This design means zero changes to the core build engine — `fetch` is a thin layer on top of `-dependon`.

## Error cases

| Situation | Behaviour |
|---|---|
| No `[dependencies]` section | Warning message, `fetch` exits cleanly |
| Repo without a `fobos` file | Error message identifying the dependency |
| git clone / fetch failure | Error message with git output |
| Already cloned, no `--update` | Skip with "already fetched" message |

## Command reference

See [`fetch` command](/reference/fetch) for the full option reference.
