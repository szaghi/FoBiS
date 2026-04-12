# scaffold

Manage project boilerplate via bundled scaffold templates.

## Synopsis

```bash
fobis scaffold <action> [options]
```

## Actions

| Action | Description |
|--------|-------------|
| `status` | Show drift report: OK, OUTDATED, or MISSING for each managed file |
| `sync` | Update divergent files (shows diff + asks confirmation, or `--yes` to auto-accept) |
| `init` | Create all missing boilerplate in a new or existing repo |
| `list` | List all managed template files and their categories |

## Options

### Common options

| Option | Description |
|--------|-------------|
| `-f, --fobos` | Path to fobos configuration file (default: `fobos`) |

### `status` options

| Option | Description |
|--------|-------------|
| `--files <glob>` | Limit scope to files matching this glob pattern |
| `--strict` | Exit non-zero if any drift is detected (for CI use) |

### `sync` options

| Option | Description |
|--------|-------------|
| `--dry-run` | Show what would change without writing any files |
| `-y, --yes` | Apply all changes without interactive prompts |
| `--files <glob>` | Limit scope to files matching this glob pattern |

### `init` options

| Option | Description |
|--------|-------------|
| `-y, --yes` | Skip interactive confirmation prompts |

## Description

`fobis scaffold` automates creation and maintenance of project boilerplate across Fortran repositories. All templates are bundled inside FoBiS.py — no external dependencies required.

### Template categories

**Verbatim** files are copied as-is; drift is detected via SHA-256 comparison against the bundled canonical version:

- `.github/workflows/ci.yml`
- `.github/workflows/docs.yml`
- `.github/actions/setup-build-env/action.yml`
- `.github/actions/run-coverage-analysis/action.yml`
- `scripts/release.sh`
- `scripts/run_tests.sh`
- `scripts/install.sh`
- `scripts/compute-coverage.sh`
- `docs/package.json`
- `cliff.toml`
- `CONTRIBUTING.md`
- `LICENSE.gpl3.md`

**Templated** files have `{{VAR}}` placeholders substituted with project metadata before comparison:

- `.github/workflows/release.yml`
- `docs/.vitepress/config.mts`
- `docs/ford.md`
- `fpm.toml`

**Init-only** files are created by `fobis scaffold init` if absent, but are never overwritten by `fobis scaffold sync` — they are yours to customise:

- `fobos` — a minimal annotated multi-mode fobos skeleton with `debug` and `release` modes
- `docs/.vitepress/config.mts`
- `docs/ford.md`
- `fpm.toml`

### Variable resolution

Each template variable is resolved in a fixed priority order:

| Variable | fobos `[project]` key | Fallback |
|----------|-----------------------|---------|
| `{{NAME}}` | `name` | repository slug, then `''` |
| `{{SUMMARY}}` | `summary` | `''` |
| `{{REPOSITORY}}` | `repository` | `git remote get-url origin` |
| `{{REPOSITORY_NAME}}` | *(derived)* | last path segment of `{{REPOSITORY}}` — never stored in fobos |
| `{{WEBSITE}}` | `website` | `''` |
| `{{AUTHORS}}` | `authors` (newline-separated → joined with `', '`) | `git config user.name` |
| `{{EMAIL}}` | `email` | `git config user.email` |
| `{{YEAR}}` | `year` | current calendar year |

**`AUTHORS` format note:** fobos stores authors one-per-line (configparser continuation syntax). Scaffold joins them with `', '` for template substitution. When `fobis scaffold init` prompts for `AUTHORS`, enter authors comma-separated (e.g. `Jane Doe, John Smith`).

**`YEAR` note:** set `year = 2020` in `[project]` to fix the copyright year across all generated files; omit it to always use the current year.

| Variable | Example value |
|----------|---------------|
| `{{NAME}}` | `PENF` |
| `{{SUMMARY}}` | `Portability Environment for Numerical Framework` |
| `{{REPOSITORY}}` | `https://github.com/szaghi/PENF` |
| `{{REPOSITORY_NAME}}` | `PENF` |
| `{{WEBSITE}}` | `https://szaghi.github.io/PENF` |
| `{{AUTHORS}}` | `Stefano Zaghi, Jane Doe` |
| `{{EMAIL}}` | `stefano.zaghi@gmail.com` |
| `{{YEAR}}` | `2020` |

## Examples

### Check drift across all managed files

```bash
fobis scaffold status
```

Output:
```
  OK       .github/workflows/docs.yml
  OUTDATED .github/actions/setup-build-env/action.yml
  MISSING  scripts/release.sh
  ...
```

### Preview what sync would change (no writes)

```bash
fobis scaffold sync --dry-run
```

### Sync a single file without prompting

```bash
fobis scaffold sync --files "cliff.toml" --yes
```

### Bootstrap a new Fortran project

```bash
mkdir MyProject && cd MyProject
git init
fobis scaffold init
```

Prompts for any missing project variables, creates directory structure (`src/`, `docs/`, `.github/`, `scripts/`), and writes all managed files.

### CI drift check

```bash
fobis scaffold status --strict
```

Exits with code 1 if any file is outdated or missing — suitable for a CI step that enforces boilerplate consistency.

## fobos integration

Scaffold reads project metadata from the `[project]` section of your fobos file:

```ini
[project]
name       = MyProject
summary    = A short description
repository = https://github.com/jane/MyProject
website    = https://jane.github.io/MyProject
email      = jane@example.com
year       = 2020
authors    = Jane Doe
             John Smith
```

`authors` is newline-separated (configparser continuation); scaffold joins them with `', '` for template substitution.
`year` is optional — omit it to use the current calendar year.

See [Project Metadata](/fobos/project) for full details.
