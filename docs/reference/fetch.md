# `fetch` command

Fetch GitHub-hosted Fortran dependencies listed in the fobos `[dependencies]` section and wire them into the build automatically.

```bash
fobis fetch [options]
```

After fetching, run `fobis build` as usual — it automatically picks up the fetched dependencies.

## Options

| Option | Default | Description |
|---|---|---|
| `--deps-dir DIR` | `.fobis_deps` | Directory where dependencies are cloned (overrides `deps_dir` in fobos `[dependencies]`) |
| `--update` | `False` | Re-fetch (git pull / checkout) and rebuild existing dependencies |
| `--no-build` | `False` | Clone only — skip building even for `use=fobos` dependencies |
| `--no-dev` | `False` | Skip the test-only (`:: dev`) dependencies (see [test-only dependencies](/advanced/fetch#test-only-dependencies-dev)) |
| `--frozen` | `False` | Abort if `<deps_dir>/fobos.lock` is missing; check every dep out at its locked commit and keep the lock unchanged (see [Lock File](/advanced/lock-file)) |
| `--no-cache` | `False` | Disable build cache when pre-building `use=fobos` deps |

## fobos options

| Option | Description |
|---|---|
| `-f`, `--fobos` | Specify a fobos file with a different name or path |
| `--fci`, `--fobos-case-insensitive` | Case-insensitive fobos option parsing |
| `--mode` | Select a fobos mode — tab-completable from the active fobos file |
| `--lmodes` | List available modes and exit |

## Fancy options

| Option | Description |
|---|---|
| `--colors` | Coloured terminal output |
| `-l`, `--log` | Write a log file |
| `-q`, `--quiet` | Less verbose output |
| `--verbose` | Maximum verbosity |
| `-j`, `--jobs` | Number of parallel compile jobs (default: 1) |
| `-m`, `--makefile` | Export a GNU Makefile instead of building |
| `--json` | Emit structured JSON to stdout (see [JSON output](/advanced/json-output)) |

## fobos `[dependencies]` section

Declare dependencies in your fobos file using the `[dependencies]` section:

```ini
[dependencies]
# optional — same as --deps-dir
deps_dir = .fobis_deps
penf     = https://github.com/szaghi/PENF :: tag=v1.5.0
stdlib   = https://github.com/fortran-lang/stdlib :: tag=v0.5.0 :: use=fobos :: mode=gnu
jsonfort = https://github.com/jacobwilliams/json-fortran :: branch=main :: use=fobos
utils    = https://github.com/certik/fortran-utils :: rev=a1b2c3d
simple   = https://github.com/user/repo
```

Each dependency entry has the form:

```
name = URL [:: branch=X | tag=X | rev=X | semver=X] [:: mode=X] [:: use=sources|fobos] [:: dev]
name = path=DIR [:: mode=X] [:: use=sources|fobos] [:: dev]
```

`path=DIR` is a local directory, relative to the fobos file's directory: nothing is cloned, every build reads it
from the fobos, `fetch` builds a `use=fobos` one and locks its commit and dirty state (or a checksum outside git)
([local directories](/advanced/fetch#local-directories-path)).

`:: dev` marks a test-only dependency: used by `fobis test`, doctests and `check`, left out of every other build
([test-only dependencies](/advanced/fetch#test-only-dependencies-dev)).

| Part | Description |
|---|---|
| `name` | Short identifier — used as the subdirectory name under `deps_dir` |
| `URL` | Full HTTPS URL of the Git repository; `user/repo` shorthand resolves to GitHub |
| `branch=X` | Checkout a specific branch |
| `tag=X` | Checkout a specific tag |
| `rev=X` | Checkout a specific commit SHA |
| `semver=X` | Resolve the highest remote tag satisfying the version constraint (see below) |
| `mode=X` | fobos mode to use when building the dependency (only for `use=fobos`) |
| `use=X` | Integration mode: `sources` (default) or `fobos` |

Only one of `branch`, `tag`, `rev`, or `semver` may be specified — they are mutually exclusive. If none is given, the default branch is used.

### Semver version constraints

Instead of pinning to an exact tag, declare a version constraint with `semver=`:

```ini
[dependencies]
PENF   = https://github.com/szaghi/PENF :: semver=^1.5
stdlib = https://github.com/fortran-lang/stdlib :: semver=>=0.5,<1.0
```

| Constraint | Meaning |
|---|---|
| `^1.5` | `>=1.5.0, <2.0.0` (compatible release) |
| `^1.5.2` | `>=1.5.2, <2.0.0` |
| `~1.5.2` | `>=1.5.2, <1.6.0` (patch-level) |
| `>=1.0,<2.0` | explicit range |
| `=1.5.0` | exact version |
| `*` | any version |

`fobis fetch` queries the remote tags, resolves the highest satisfying tag, clones at that tag, and writes the resolved version to the lock, `<deps_dir>/fobos.lock`. On later non-`--update` runs in the same checkout the locked tag is used directly.

See [Lock File & Semver](/advanced/lock-file) for the full workflow.

### `deps_dir` key

Setting `deps_dir` in the `[dependencies]` section is equivalent to passing `--deps-dir` on the command line. The CLI flag takes precedence when both are provided.

### `use=` integration modes

| `use=` | `fobis fetch` behaviour | `fobis build` behaviour |
|--------|------------------------|------------------------|
| `sources` (default) | Clone only, no pre-build | Dep directory added to source scan; sources compiled inline with your project |
| `fobos` | Clone + `fobis build` inside dep | Dep fobos path added to `--dependon`; dep dir excluded from source scan; dep library linked |

For `use=fobos` the target repository **must** contain a `fobos` file.
For `use=sources` no `fobos` file is required.

## How it works

1. For each entry in `[dependencies]`, `fetch` clones the repository into `<deps-dir>/<name>/`.
2. If `branch`, `tag`, or `rev` is specified, the corresponding revision is checked out.
3. For `use=fobos` dependencies (and when `--no-build` is not set), `fobis build` is invoked inside the dependency directory using the specified `mode`.
4. A config file `<deps-dir>/.deps_config.ini` is written:
   - `use=sources` deps → listed under the `src` key
   - `use=fobos` deps → listed under the `dependon` key
5. When you run `fobis build`, it reads `.deps_config.ini`:
   - `src` entries are appended to the source search paths (skipped if already covered)
   - `dependon` entries are added to `--dependon`, and the dep directory is added to `--exclude-dirs` to prevent double-compilation

![Fetch dependencies demo](/gifs/07_fetch.gif)

## Workflow

```bash
# 1. Add [dependencies] to your fobos file (see above)

# 2. Fetch all dependencies
fobis fetch

# 3. Build your project — dependencies are auto-detected
fobis build

# 4. Update dependencies to their latest version
fobis fetch --update

# 5. Clone only (inspect before building)
fobis fetch --no-build
fobis fetch --no-build --update   # re-fetch without rebuilding
```

## Examples

```bash
# Fetch all dependencies defined in the fobos file
fobis fetch

# Fetch into a custom directory
fobis fetch --deps-dir vendor/

# Re-fetch and rebuild
fobis fetch --update

# Clone only, do not build
fobis fetch --no-build

# Use a custom fobos file
fobis fetch -f my.fobos
```

See the [Fetch Dependencies](/advanced/fetch) advanced guide for the full workflow and integration mode details.

<!-- cli:begin -->
<!-- generated by docs/scripts/gen_cli_reference.py from the command line: do not edit -->

## All options

| Option | Value | Default | Description |
|---|---|---|---|
| `--fobos`, `-f` | TEXT |  | Specify a "fobos" file named differently from "fobos" |
| `--fci` |  |  | Assume fobos inputs as case insensitive |
| `--mode` | TEXT |  | Select a mode defined into a fobos file |
| `--lmodes` |  |  | List the modes defined into a fobos file |
| `--deps-dir` | TEXT |  | Directory for storing fetched dependencies [default: .fobis_deps or fobos [dependencies] setting] |
| `--update` |  |  | Update already-fetched dependencies (git fetch + re-checkout) |
| `--no-build` |  |  | Only fetch dependencies, do not build them |
| `--no-dev` |  |  | Skip the test-only dependencies (:: dev), e.g. for a production build |
| `--frozen` |  |  | Check every dependency out at the commit of &lt;deps_dir&gt;/fobos.lock; abort if the lock is absent |
| `--no-cache` |  |  | Disable build artifact cache for fetched dependencies |
| `--force-compile` |  |  | Force to (re-)compile all |
| `--colors` |  |  | Activate colors in shell prints |
| `--log`, `-l` |  |  | Activate log file creation |
| `--graph` |  |  | Generate a dependencies graph via graphviz |
| `--quiet`, `-q` |  |  | Less verbose output |
| `--verbose` |  |  | Extremely verbose output for debugging |
| `--jobs`, `-j` | INTEGER | `1` | Number of concurrent compilation jobs [default: 1] |
| `--makefile`, `-m` | TEXT |  | Generate a GNU Makefile for building the project |
| `--json` |  |  | Emit structured JSON to stdout instead of human-readable output (useful for scripting / agents) |

<!-- cli:end -->
