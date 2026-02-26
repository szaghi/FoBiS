# `fetch` command

Fetch and build GitHub-hosted Fortran dependencies listed in the fobos `[dependencies]` section.

```bash
FoBiS.py fetch [options]
```

After fetching, run `FoBiS.py build` as usual — it automatically picks up the fetched dependencies.

## Options

| Option | Default | Description |
|---|---|---|
| `--deps-dir DIR` | `.fobis_deps` | Directory where dependencies are cloned |
| `--update` | `False` | Re-fetch (git pull / checkout) and rebuild existing dependencies |
| `--no-build` | `False` | Clone only — skip building the dependencies |

## fobos options

| Option | Description |
|---|---|
| `-f`, `--fobos` | Specify a fobos file with a different name or path |
| `-fci`, `--fobos_case_insensitive` | Case-insensitive fobos option parsing |
| `-mode` | Select a fobos mode |
| `-lmodes` | List available modes and exit |
| `--print_fobos_template` | Print a fobos template |

## Fancy options

| Option | Description |
|---|---|
| `-colors` | Coloured terminal output |
| `-l`, `--log` | Write a log file |
| `-q`, `--quiet` | Less verbose output |
| `-verbose` | Maximum verbosity |

## fobos `[dependencies]` section

Declare dependencies in any fobos file using the `[dependencies]` section:

```ini
[dependencies]
stdlib   = https://github.com/fortran-lang/stdlib :: tag=v0.5.0 :: mode=gnu
jsonfort = https://github.com/jacobwilliams/json-fortran :: branch=main
utils    = https://github.com/user/fortran-utils :: rev=a1b2c3d
simple   = https://github.com/user/repo
```

Each entry has the form:

```
name = URL [:: branch=X] [:: tag=X] [:: rev=X] [:: mode=X]
```

| Part | Description |
|---|---|
| `name` | Short identifier — used as the subdirectory name under `--deps-dir` |
| `URL` | Full HTTPS URL of the Git repository |
| `branch=X` | Checkout a specific branch |
| `tag=X` | Checkout a specific tag |
| `rev=X` | Checkout a specific commit SHA |
| `mode=X` | fobos mode to use when building the dependency |

Only one of `branch`, `tag`, or `rev` may be specified. If none is given, the default branch is used.

The target repository **must** contain a `fobos` file.

## Workflow

```bash
# 1. Add [dependencies] to your fobos file (see above)

# 2. Fetch and build all dependencies
FoBiS.py fetch

# 3. Build your project — dependencies are auto-detected
FoBiS.py build

# 4. Update dependencies to their latest version
FoBiS.py fetch --update

# 5. Clone only (inspect before building)
FoBiS.py fetch --no-build
FoBiS.py fetch --no-build --update   # re-fetch without rebuilding
```

## How it works

1. For each entry in `[dependencies]`, `fetch` clones the repository into `<deps-dir>/<name>/`.
2. If `branch`, `tag`, or `rev` is specified, the corresponding revision is checked out.
3. Each dependency is built by invoking `FoBiS.py build` inside its directory (using the specified `mode` if provided).
4. A config file `.fobis_deps/.deps_config.ini` is written with the paths of all fetched dependencies.
5. When you run `FoBiS.py build`, it reads `.deps_config.ini` and adds the dependency fobos files to `-dependon` automatically — no manual wiring required.

## Examples

```bash
# Fetch all dependencies defined in the fobos file
FoBiS.py fetch

# Fetch into a custom directory
FoBiS.py fetch --deps-dir vendor/

# Re-fetch and rebuild
FoBiS.py fetch --update

# Clone only, do not build
FoBiS.py fetch --no-build

# Use a custom fobos file
FoBiS.py fetch -f my.fobos
```

See the [Fetch Dependencies](/advanced/fetch) advanced guide for the full workflow.
