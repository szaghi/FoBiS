# The one-line installer

Every project managed by `fobis scaffold` ships the same installer, `scripts/install.sh`, attached to each GitHub
release. A user installs a release with one line, choosing among the build systems the project offers:

```bash
curl -fsSL https://github.com/<owner>/<repo>/releases/latest/download/install.sh | bash -s -- [options]
```

The script is rendered from the project's `fobos` (the repository, and the `[installer]` section below) by
`fobis scaffold sync`: never edit it, change the `fobos` and sync. The release side (the tarball carrying the
dependencies, the install test of every release) is fortran-toolchains' `release.yml` and `install.yml`.

## For the users of a project

```bash
# the latest release, the build system chosen for you, into ~/.local
curl -fsSL https://github.com/szaghi/FiNeR/releases/latest/download/install.sh | bash
# a given release, built with CMake by ifx, into /opt/finer
curl -fsSL https://github.com/szaghi/FiNeR/releases/latest/download/install.sh | bash -s -- \
  --tag v2.3.1 --build cmake --intel --prefix /opt/finer
```

| Option | Meaning |
|---|---|
| `--build fobis\|fpm\|cmake\|make` | the build system, among those the release ships |
| `--fc FC`, `--gnu`, `--intel`, `--nvidia` | the Fortran compiler: by name or path; gfortran, ifx, nvfortran (default: `$FC`, else gfortran) |
| `--prefix DIR` | where to install (default `~/.local`) |
| `--tag TAG` | the release (default: the latest) |
| `--source DIR` | build a local tree instead of downloading a release |
| `--deps` | install the system packages the project declares (the command is shown first; `sudo` on Linux) |
| `--dry-run` | download, detect and check, print what would be done, build nothing |
| `--uninstall` | remove what the installer installed (one compiler's install with `--fc`/`--gnu`/...; all otherwise) |
| `--keep`, `--verbose` | keep the build directory; show the build output (otherwise it goes to a log, shown when a stage fails) |
| `--version` | the installer's interface version (`install.sh 2`) |

**Which build system.** The script looks at what the release ships: a `fobos` (FoBiS), an `fpm.toml` (fpm), a
`CMakeLists.txt` (CMake), a `makefile` (make).

- One only: it is used, and `--build` naming another is an error that names it.
- Several: `--build` chooses; without it, a menu on the terminal (it works under `curl | bash`); without a terminal (a
  CI job), the first of **fobis, fpm, cmake, make** that the release ships.

**What you need.** A Fortran compiler and the chosen build system, nothing else: FoBiS, when chosen (or required by
the project's own steps) and missing, is installed in a private virtual environment under the prefix (Python 3.11 or
later). The release tarball carries the project's dependencies, so CMake and make build offline; fpm fetches its own
from the `fpm.toml`. `curl` downloads the release: the latest one is found by its redirect, without the GitHub API.

**Where it goes.** A Fortran module file works only with the compiler that wrote it, so the installer keeps one
install per compiler, `<compiler>-<version>` (for example `gnu-16.2.0`):

```
<prefix>/lib/<name>/gnu-16.2.0/        the libraries
<prefix>/include/<name>/gnu-16.2.0/    the module files
<prefix>/lib/pkgconfig/<name>-gnu-16.2.0.pc, and <name>.pc (a copy of the last one installed)
<prefix>/share/<name>/gnu-16.2.0/manifest
```

Two build systems keep a layout of their own: fpm 0.13 puts the module files in `<prefix>/include` (it ignores
`--includedir` for them), and a makefile's own `install` target decides everything. The pkg-config file lists the
directories where the build actually put the libraries and the modules, so it is right in every case:

```bash
export PKG_CONFIG_PATH=$HOME/.local/lib/pkgconfig
gfortran my_program.f90 $(pkg-config --cflags --libs finer) -o my_program
```

When a build installs several static libraries (CMake installs each bundled dependency as a library of its own), they
are listed in link order, each before the ones it needs (ordered by their symbols, `nm` and `tsort`). A CMake build
also installs the project's own CMake package, if it exports one: `find_package(<Name>)` with
`CMAKE_PREFIX_PATH=<prefix>`.

**Removing it.** `--uninstall --prefix DIR` removes every file the manifest lists, and the directories left empty;
with a compiler option, only that compiler's install.

## For the project: the `[installer]` section

Nothing is needed when the defaults fit. They are: the repository from `[project] repository` (or the git remote),
the release tarball named as the release workflow names it (the repository's name), the FoBiS build in the modes
`static-gnu`, `static-intel` and `static-nvf`, and a pkg-config file. A project states what differs:

```ini
[installer]
mode_gnu    = finer-static-gnu
mode_intel  = finer-static-intel
mode_nvidia = finer-static-nvf
```

| Key | Default | Meaning |
|---|---|---|
| `repository` | `[project] repository` | `owner/name` on GitHub |
| `name` | the repository's name | the release tarball's name, `<name>-<tag>.tar.gz`, and the install's directory and pkg-config name |
| `mode_gnu`, `mode_intel`, `mode_nvidia` | `static-gnu`, `static-intel`, `static-nvf` | the fobos mode the FoBiS build uses with gfortran, ifx, nvfortran |
| `pre` | none | a fobos rule run before the build, whatever the build system |
| `check` | none | a fobos rule run after the install, with `PREFIX` and `PKG_CONFIG_PATH` set |
| `apt`, `brew` | none | the system packages `--deps` installs, on Debian/Ubuntu and on macOS |
| `pkgconfig` | `true` | write the pkg-config file (`false` when the build installs its own `<name>.pc`, which is kept anyway) |
| `make_lib`, `make_mod` | none | for a makefile without an `install` target: where the libraries and the module files are after `make` |
| `headers` | none | the files (globs, relative to the sources) your users include, such as a header of macros: every build that does not install them (FoBiS, fpm and make install module files only) gets them next to its module files, on the pkg-config `-I` path |

A `pre` or `check` rule is a fobos rule, run by FoBiS: declaring one makes FoBiS needed by every build system of the
project (the installer then bootstraps it). An unknown key, a rule the fobos does not define, or a `pkgconfig` other
than `true`/`false` stops `fobis scaffold` with an error.

A project with a native layer and a smoke test declares them instead of writing an installer of its own (an
illustration modelled on figure; its own keys will be set when it moves to the shared installer): `[rule-native]`
builds the C/C++ layer and SDL with CMake, `[rule-smoke]` compiles a test program with pkg-config and runs it
headless. A fobos value keeps an inline `;` comment, so the comments go on lines of their own.

```ini
[installer]
pre   = native
check = smoke
apt   = libx11-dev libxext-dev libwayland-dev libxkbcommon-dev libdecor-0-dev libdbus-1-dev
brew  = pkg-config
```

## The installation page of a project

The scaffold does not write a project's installation page (most projects have one already). A section to paste, with
the project's repository:

````markdown
## One-line install

```bash
curl -fsSL https://github.com/<owner>/<repo>/releases/latest/download/install.sh | bash
```

It installs the latest release into `~/.local` with the build system you choose among those the project ships
(`--build fobis|fpm|cmake|make`), the compiler you name (`--fc`, `--gnu`, `--intel`, `--nvidia`), and makes it usable
through pkg-config (`pkg-config --cflags --libs <name>`). `--help` lists every option; `--uninstall` removes it.
````
