# `fetch` command

Fetch GitHub-hosted Fortran dependencies listed in the fobos `[dependencies]` section and wire them into the build automatically.

```bash
FoBiS.py fetch [options]
```

After fetching, run `FoBiS.py build` as usual — it automatically picks up the fetched dependencies.

## Options

| Option | Default | Description |
|---|---|---|
| `--deps-dir DIR` | `.fobis_deps` | Directory where dependencies are cloned (overrides `deps_dir` in fobos `[dependencies]`) |
| `--update` | `False` | Re-fetch (git pull / checkout) and rebuild existing dependencies |
| `--no-build` | `False` | Clone only — skip building even for `use=fobos` dependencies |

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

Declare dependencies in your fobos file using the `[dependencies]` section:

```ini
[dependencies]
deps_dir = .fobis_deps                          # optional — same as --deps-dir
penf     = https://github.com/szaghi/PENF :: tag=v1.5.0
stdlib   = https://github.com/fortran-lang/stdlib :: tag=v0.5.0 :: use=fobos :: mode=gnu
jsonfort = https://github.com/jacobwilliams/json-fortran :: branch=main :: use=fobos
utils    = https://github.com/certik/fortran-utils :: rev=a1b2c3d
simple   = https://github.com/user/repo
```

Each dependency entry has the form:

```
name = URL [:: branch=X] [:: tag=X] [:: rev=X] [:: mode=X] [:: use=sources|fobos]
```

| Part | Description |
|---|---|
| `name` | Short identifier — used as the subdirectory name under `deps_dir` |
| `URL` | Full HTTPS URL of the Git repository |
| `branch=X` | Checkout a specific branch |
| `tag=X` | Checkout a specific tag |
| `rev=X` | Checkout a specific commit SHA |
| `mode=X` | fobos mode to use when building the dependency (only for `use=fobos`) |
| `use=X` | Integration mode: `sources` (default) or `fobos` |

Only one of `branch`, `tag`, or `rev` may be specified. If none is given, the default branch is used.

### `deps_dir` key

Setting `deps_dir` in the `[dependencies]` section is equivalent to passing `--deps-dir` on the command line. The CLI flag takes precedence when both are provided.

### `use=` integration modes

| `use=` | `fobis fetch` behaviour | `fobis build` behaviour |
|--------|------------------------|------------------------|
| `sources` (default) | Clone only, no pre-build | Dep directory added to source scan; sources compiled inline with your project |
| `fobos` | Clone + `FoBiS.py build` inside dep | Dep fobos path added to `-dependon`; dep dir excluded from source scan; dep library linked |

For `use=fobos` the target repository **must** contain a `fobos` file.
For `use=sources` no `fobos` file is required.

## How it works

1. For each entry in `[dependencies]`, `fetch` clones the repository into `<deps-dir>/<name>/`.
2. If `branch`, `tag`, or `rev` is specified, the corresponding revision is checked out.
3. For `use=fobos` dependencies (and when `--no-build` is not set), `FoBiS.py build` is invoked inside the dependency directory using the specified `mode`.
4. A config file `<deps-dir>/.deps_config.ini` is written:
   - `use=sources` deps → listed under the `src` key
   - `use=fobos` deps → listed under the `dependon` key
5. When you run `FoBiS.py build`, it reads `.deps_config.ini`:
   - `src` entries are appended to the source search paths (skipped if already covered)
   - `dependon` entries are added to `-dependon`, and the dep directory is added to `exclude_dirs` to prevent double-compilation

## Workflow

```bash
# 1. Add [dependencies] to your fobos file (see above)

# 2. Fetch all dependencies
FoBiS.py fetch

# 3. Build your project — dependencies are auto-detected
FoBiS.py build

# 4. Update dependencies to their latest version
FoBiS.py fetch --update

# 5. Clone only (inspect before building)
FoBiS.py fetch --no-build
FoBiS.py fetch --no-build --update   # re-fetch without rebuilding
```

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

See the [Fetch Dependencies](/advanced/fetch) advanced guide for the full workflow and integration mode details.
