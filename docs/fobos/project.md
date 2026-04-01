# Project metadata

The optional `[project]` section lets you embed project metadata directly in the fobos file. FoBiS.py reads this section to provide version information and project details — independently of any build mode.

## Syntax

```ini
[project]
name       = My Fortran Project
summary    = A brief description of what the project does
version    = 1.2.3
repository = https://github.com/user/my-fortran-project
website    = https://user.github.io/my-fortran-project
email      = maintainer@example.com
year       = 2020
authors    = Stefano Zaghi
             Jane Doe
             John Smith
```

All options are optional. The section itself is optional.

## Options

| Option | Type | Description |
|---|---|---|
| `name` | string | Human-readable name of the project |
| `summary` | string | One-line description of what the project does |
| `version` | string or file path | Project version (see [Version resolution](#version-resolution)) |
| `repository` | string | URL of the remote git repository (GitHub, GitLab, Codeberg, …) |
| `website` | string | URL of the project website or documentation site |
| `email` | string | Email address of the project maintainer |
| `year` | string | Copyright/founding year (e.g. `2020`); defaults to the current calendar year when absent |
| `authors` | list of strings | One author per line (continuation lines indented with whitespace) |

## Year

The `year` option records the project's copyright or founding year. It is used by `fobis scaffold` when rendering templated boilerplate files that include `{{YEAR}}` (e.g. `fpm.toml`, `docs/.vitepress/config.mts`).

When `year` is absent, scaffold falls back to the current calendar year at the time the command is run. Set it explicitly to fix the copyright year across all generated files regardless of when scaffold is invoked:

```ini
[project]
year = 2020
```

## Authors

Authors are written one per line using standard INI continuation syntax — each subsequent line must be indented:

```ini
[project]
authors = Stefano Zaghi
          Jane Doe
          John Smith
```

## Version resolution

The `version` option is resolved by `get_version()` following these steps:

1. **Literal value** — if the value does not match a file path, it is used as-is.
2. **File path** — if the value is a path relative to the git repository root that points to an existing file, the version string is read from that file. Useful when the version is maintained in a dedicated file (e.g. `VERSION` or `src/version.f90`).
3. **`v` prefix normalisation** — the resolved fobos version is always returned with a `v` prefix (added automatically if absent).
4. **Git tag fallback** — if `version` is not set in fobos, the most recent git tag is returned via `git describe --tags --abbrev=0`.

### Mismatch warning

When both the fobos version and a git tag are present and they disagree, FoBiS.py emits a warning with two actionable fix suggestions:

```
Warning: project version mismatch!
  fobos [project] version : v1.2.3
  git tag version         : v1.2.4
  To fix, either:
    - update fobos: set  version = v1.2.4  under [project]
    - create a matching tag: git tag v1.2.3 && git push --tags
```

### Version file example

```ini
[project]
version = VERSION
```

`VERSION` (at the git repository root):

```
1.2.3
```

FoBiS.py reads the file and normalises the result to `v1.2.3`.

## Full example

```ini
[project]
name       = PENF
summary    = Portability Environment for Fortran
version    = VERSION
repository = https://github.com/szaghi/PENF
website    = https://szaghi.github.io/PENF
email      = stefano.zaghi@cnr.it
year       = 2015
authors    = Stefano Zaghi

[modes]
modes = debug release

[debug]
compiler  = gnu
cflags    = -c -O0 -g -Wall
build_dir = ./build/debug/

[release]
compiler  = gnu
cflags    = -c -O3
build_dir = ./build/release/
```
