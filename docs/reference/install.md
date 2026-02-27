# `install` command

Install previously built FoBiS artifacts, or clone, build, and install a GitHub-hosted Fortran project in one step.

```bash
fobis install [repo] [options]
```

The `install` command has two modes:

- **Local install** (no `repo` argument): copies artifacts that were built with `--track_build` to a prefix directory.
- **GitHub install** (`repo` argument given): clones a GitHub-hosted FoBiS project, builds it, and installs the artifacts — all in a single command.

## GitHub install options

These options are only relevant when a `repo` is provided.

| Option | Default | Description |
|---|---|---|
| `repo` | *(none)* | GitHub repository — `user/repo` shorthand or full HTTPS/SSH URL |
| `--branch BRANCH` | `None` | Check out a specific branch |
| `--tag TAG` | `None` | Check out a specific tag |
| `--rev REV` | `None` | Check out a specific commit SHA |
| `--update` | `False` | Re-fetch the repository before building |
| `--no-build` | `False` | Clone only — skip building and installing |
| `--deps-dir DIR` | `~/.fobis/` | Directory used to clone the repository |

## Directory / install prefix options

| Option | Default | Description |
|---|---|---|
| `-p`, `--prefix` | `./` | Root installation prefix |
| `--bin` | `bin/` | Sub-directory under prefix for executables |
| `--lib` | `lib/` | Sub-directory under prefix for libraries |
| `--include` | `include/` | Sub-directory under prefix for module files |

## fobos options (local install)

| Option | Description |
|---|---|
| `-f`, `--fobos` | Specify a fobos file |
| `-fci`, `--fobos_case_insensitive` | Case-insensitive fobos parsing |
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

## Examples

### GitHub install (one-shot)

```bash
# Install szaghi/FLAP from GitHub to the current directory
fobis install szaghi/FLAP

# Install to a custom prefix
fobis install szaghi/FLAP --prefix /usr/local/

# Pin to a specific tag and mode
fobis install szaghi/FLAP --tag v20210301 --prefix ~/.local/ -mode gnu

# Clone only — inspect before building
fobis install szaghi/FLAP --no-build

# Use a full URL instead of the shorthand
fobis install https://github.com/szaghi/FLAP --prefix /opt/fortran/
```

### Local install (from build artefacts)

```bash
# Build with artifact tracking enabled
fobis build --track_build

# Install tracked artifacts to the default prefix (./)
fobis install

# Install to a custom prefix
fobis install --prefix /usr/local/
```

## How GitHub install works

1. The `user/repo` shorthand is resolved to `https://github.com/user/repo`; full URLs are used as-is.
2. The repository is cloned into `<deps-dir>/<repo-name>/` (default: `~/.fobis/<repo-name>/`).
3. If `--branch`, `--tag`, or `--rev` is given, that revision is checked out.
4. The dependency is built with `fobis build --track_build` (optionally with `-mode`).
5. The generated `.track_build` files are scanned for artifact paths.
6. Executables are copied to `<prefix>/<bin>/`, libraries to `<prefix>/<lib>/`, and module files to `<prefix>/<include>/`.

The target repository **must** contain a `fobos` file.

## How local install works

The local mode reads `.track_build` files produced by a previous `fobis build --track_build` run and copies the recorded artifacts to the prefix. Use `-tb` / `--track_build` on the `build` command to enable this.

See the [GitHub Install](/advanced/install) advanced guide for a full workflow walkthrough.
