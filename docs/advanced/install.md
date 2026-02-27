# GitHub Install

The `install` command can clone, build, and install a GitHub-hosted Fortran project in a single step — no manual `git clone`, no fobos wiring required.

## Quick start

```bash
# Install szaghi/FLAP to the current directory
fobis install szaghi/FLAP

# Or with a full URL
fobis install https://github.com/szaghi/FLAP
```

That's it. FoBiS clones the repository, builds it, and copies the resulting executables and libraries to `./bin/` and `./lib/`.

## Installation prefix

By default artifacts are installed relative to the current directory. Use `--prefix` to change the destination:

```bash
# Install to ~/.local/ (user-wide)
fobis install szaghi/FLAP --prefix ~/.local/

# Install to a system directory
fobis install szaghi/FLAP --prefix /usr/local/

# Custom sub-directories
fobis install szaghi/FLAP --prefix /opt/fortran/ --bin bin/ --lib lib/ --include include/
```

| Option | Default | Purpose |
|---|---|---|
| `--prefix` | `./` | Root installation directory |
| `--bin` | `bin/` | Executables sub-directory |
| `--lib` | `lib/` | Libraries sub-directory |
| `--include` | `include/` | Module files sub-directory |

## Pinning a version

Use `--branch`, `--tag`, or `--rev` to pin the installed version:

```bash
# Pin to a release tag
fobis install szaghi/FLAP --tag v20210301 --prefix ~/.local/

# Track a specific branch
fobis install szaghi/FLAP --branch main --prefix ~/.local/

# Pin to an exact commit
fobis install szaghi/FLAP --rev a1b2c3d --prefix ~/.local/
```

## Selecting a fobos build mode

If the target project's `fobos` file defines multiple build modes, pass `-mode` to choose one:

```bash
fobis install szaghi/FLAP --tag v20210301 -mode gnu --prefix ~/.local/
```

## Keeping up to date

Use `--update` to re-fetch and rebuild an already-cloned repository:

```bash
fobis install szaghi/FLAP --update --prefix ~/.local/
```

## Clone without building

Use `--no-build` to clone only, without building or installing:

```bash
fobis install szaghi/FLAP --no-build
```

The cloned source tree ends up in `~/.fobis/<repo-name>/` (or `--deps-dir` if provided).

## Repository cache location

By default, cloned repositories are stored in `~/.fobis/<repo-name>/`. Override with `--deps-dir`:

```bash
fobis install szaghi/FLAP --deps-dir /tmp/fobis-cache/
```

The cache directory is reused on subsequent runs. `--update` triggers a `git fetch` + checkout rather than re-cloning.

## How it works

Under the hood, `fobis install <repo>` calls:

1. `git clone <url> ~/.fobis/<name>/` — or skips if already present.
2. `git checkout <branch|tag|rev>` — if a revision was specified.
3. `fobis build --track_build [-mode X]` inside the cloned directory.
4. Scans all `.track_build` files for artifact paths.
5. Copies executables to `<prefix>/<bin>/`, libraries to `<prefix>/<lib>/`, and `.mod` files to `<prefix>/<include>/`.

The target repository **must** contain a `fobos` file. The `.track_build` mechanism is what records which files were produced and whether they are programs or libraries.

## Comparison with `fetch`

| Feature | `fobis install <repo>` | `fobis fetch` |
|---|---|---|
| Purpose | One-off install of a single project | Declarative multi-dep management for a project |
| Configuration | CLI flags | `[dependencies]` section in fobos |
| Install destination | `--prefix` (default `./`) | Stays in `.fobis_deps/`; wired via `-dependon` |
| Multiple repos | One at a time | All at once |
| Best for | Installing tools/libraries for your own use | Adding build-time deps to a Fortran project |

Use `fetch` when you are developing a Fortran project that depends on other FoBiS libraries. Use `install` when you simply want to install a standalone FoBiS-based tool or library onto your system.

## Error cases

| Situation | Behaviour |
|---|---|
| `repo` has no `fobos` file | Error message, stops before building |
| `git clone` fails (bad URL, no network) | Error with git output |
| Build fails | Error with fobis output |
| No artifacts produced | Warning: "No installable artifacts found" |

## Command reference

See the [`install` command](/reference/install) for the full option reference.
