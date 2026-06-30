# Scaffold — Boilerplate Management

The `scaffold` command keeps CI workflows, documentation configs, license files, and shell scripts **identical across all your Fortran repositories**. A canonical set of templates is bundled inside FoBiS.py itself — no extra tool, no separate template repository, no external dependency.

## The problem scaffold solves

If you maintain several Fortran projects you have probably noticed how boilerplate drifts:

- GitHub Actions workflow names diverge (`run-coverage-analysis` vs `run-coverage`)
- `cliff.toml` in older repos still hardcodes the repository slug instead of auto-detecting it
- `install.sh` is outdated in half the repos
- A new `docs.yml` workflow was added to some repos but not others

Every fix has to be manually copied to every affected repository. `fobis scaffold` automates that.

## Quick start

### Check for drift

```bash
fobis scaffold status
```

Output:
```
  OK       .github/workflows/docs.yml
  OUTDATED .github/actions/setup-build-env/action.yml
  MISSING  scripts/release.sh
  MISSING  scripts/compute-coverage.sh
  OK       CONTRIBUTING.md
  OK       LICENSE.gpl3.md
  OUTDATED cliff.toml
  ...
```

Each managed file is reported as `OK`, `OUTDATED`, or `MISSING`.

### Apply updates

```bash
fobis scaffold sync
```

For each outdated or missing file, scaffold prints the unified diff and asks for confirmation:

```
--- cliff.toml ---
--- a/cliff.toml
+++ b/cliff.toml
@@ -78,3 +78,4 @@
 sort_commits = "oldest"
+
+[remote.github]
+# auto-detected from git remote — no hardcoded repo slug

Apply changes to cliff.toml? [Y/n]:
```

Use `--yes` to accept all without prompting, or `--dry-run` to preview changes without writing any file.

## Template categories

Scaffold manages four categories of files, distinguished by how drift is detected and how updates are applied.

### Verbatim files

Verbatim files are copied as-is from the bundled canonical version. Drift detection is a plain SHA-256 comparison between the bundled file and the on-disk file. Any difference — even a single trailing newline — is reported as `OUTDATED`.

| File | Purpose |
|------|---------|
| `.github/workflows/ci.yml` | Build-and-test CI workflow |
| `.github/workflows/docs.yml` | VitePress docs deployment + coverage-badge publish workflow |
| `.github/workflows/install.yml` | Post-release smoke test of the install methods (make/cmake/fpm; legs self-skip when inapplicable) |
| `.github/actions/run-coverage-analysis/action.yml` | Composite action: lcov coverage + JSON badge |
| `scripts/release.sh` | Bump the `VERSION` file |
| `scripts/run_tests.sh` | Build and run the project test suite (serial, or `--np N` for MPI) |
| `scripts/install.sh` | Repo-agnostic install script |
| `scripts/compute-coverage.sh` | Compute gcov coverage and emit JSON badge |
| `docs/package.json` | VitePress npm configuration |
| `cliff.toml` | git-cliff changelog configuration (auto-detecting, no hardcoded repo slug) |
| `LICENSE.gpl3.md` | GNU GPL v3 license text |

### Templated files

Templated files contain `{{VAR}}` placeholders. Before comparing or writing, scaffold renders the template by substituting project-specific values. Drift detection compares the **rendered** content against the on-disk file.

| File | Placeholders used |
|------|------------------|
| `.github/workflows/release.yml` | `{{NAME}}` |
| `.github/actions/setup-build-env/action.yml` | `{{SCAFFOLD_APT_PACKAGES}}` (empty by default → renders identically to the unparametrised action) |
| `docs/.vitepress/config.mts` | `{{NAME}}`, `{{SUMMARY}}`, `{{REPOSITORY_NAME}}`, `{{REPOSITORY}}`, `{{AUTHORS}}`, `{{YEAR}}` |
| `docs/ford.md` | `{{NAME}}`, `{{SUMMARY}}`, `{{WEBSITE}}`, `{{AUTHORS}}`, `{{EMAIL}}`, `{{REPOSITORY}}` |
| `fpm.toml` | `{{NAME}}`, `{{SUMMARY}}`, `{{AUTHORS}}`, `{{EMAIL}}`, `{{YEAR}}` |

### Init-only files

Init-only files are created once by `fobis scaffold init` and then **owned by the project** — `sync` never touches them and `status` reports them `OK` whenever present (never `OUTDATED`), so a repo can freely extend them.

| File | Purpose |
|------|---------|
| `docs/guide/contributing.md` | Contributing guide (projects add repo-specific sections) |
| `docs/.vitepress/config.mts` | VitePress site config |
| `docs/ford.md` | FORD API-doc config |
| `fpm.toml` | fpm package manifest |
| `fobos` | FoBiS build configuration |

### Symlink files

A symlink entry ensures a repo-root path is a symbolic link to a canonical managed file (so GitHub and the docs site share one source). `sync` creates or repairs the link and **never writes through it**; if a regular file is found in its place it is replaced by the link.

| Link | Target |
|------|--------|
| `CONTRIBUTING.md` | `docs/guide/contributing.md` |

## Variable resolution

Template placeholders are filled from project metadata using a fixed priority order:

| Variable | fobos `[project]` key | Fallback |
|----------|-----------------------|---------|
| `{{NAME}}` | `name` | repository slug, then `''` |
| `{{SUMMARY}}` | `summary` | `''` |
| `{{REPOSITORY}}` | `repository` | `git remote get-url origin` (SSH URLs normalised to HTTPS) |
| `{{REPOSITORY_NAME}}` | *(derived)* | last path segment of `{{REPOSITORY}}` — not a fobos option |
| `{{WEBSITE}}` | `website` | `''` |
| `{{AUTHORS}}` | `authors` | `git config user.name` |
| `{{EMAIL}}` | `email` | `git config user.email` |
| `{{YEAR}}` | `year` | current calendar year |

### Typical fobos `[project]` section

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
```

With this in place, `fobis scaffold status` and `fobis scaffold sync` know exactly what to put in `fpm.toml`, `docs/.vitepress/config.mts`, and the other templated files.

### Optional fobos `[scaffold]` section

Some templated artifacts read extra knobs from a `[scaffold]` section. The section is entirely optional — when absent, the affected artifacts render to their defaults (byte-identical to the unparametrised version, so no spurious drift).

| Key | Drives | Example |
|-----|--------|---------|
| `apt_packages` | extra system packages installed in `setup-build-env` (space-separated) | `apt_packages = libopenmpi-dev openmpi-bin` |

```ini
[scaffold]
apt_packages = zlib1g-dev
```

A project that needs MPI or a system library (HDF5, NetCDF, zlib, …) in CI declares it here instead of hand-editing the composite action. The packages are appended to the action's `apt install` line; `mpirun`-based test execution is handled separately by `scripts/run_tests.sh --np N`.

### `AUTHORS` format

In fobos, `authors` is written one-per-line using INI continuation syntax:

```ini
authors = Stefano Zaghi
          Jane Doe
          John Smith
```

Scaffold joins them with `', '` when substituting `{{AUTHORS}}` into templates, so the above becomes `Stefano Zaghi, Jane Doe, John Smith`.

### `YEAR`

`year` is optional. Omit it to always use the current calendar year; set it explicitly to pin the copyright year to the project's founding year regardless of when scaffold runs.

### `REPOSITORY_NAME`

`REPOSITORY_NAME` is always derived — it is the last path segment of `REPOSITORY`. It is never stored as a separate fobos option. Example: `https://github.com/szaghi/PENF` → `PENF`.

## Actions in depth

### `fobis scaffold status`

Shows the drift report without making any changes. Useful as a first step before `sync`.

```bash
fobis scaffold status
```

Scope it to a subset of files with `--files`:

```bash
# Check only CI-related files
fobis scaffold status --files ".github/**"

# Check only scripts
fobis scaffold status --files "scripts/*"
```

Exit non-zero on any drift — suitable for use in CI:

```bash
fobis scaffold status --strict
```

### `fobis scaffold sync`

Updates every file that differs from the canonical template. By default it shows the unified diff for each file and prompts for confirmation before writing.

```bash
fobis scaffold sync
```

Accept all changes silently (e.g. in automated scripts):

```bash
fobis scaffold sync --yes
```

Preview changes without touching any file:

```bash
fobis scaffold sync --dry-run
```

Update only a specific file:

```bash
fobis scaffold sync --files "cliff.toml" --yes
```

Update only CI-related files:

```bash
fobis scaffold sync --files ".github/**" --yes
```

### `fobis scaffold init`

Creates **all** missing managed files in a new or existing repository. Files that already exist are left untouched and reported as `exists`.

```bash
fobis scaffold init
```

If project variables cannot be resolved from fobos or git, scaffold prompts interactively:

```
Some project variables are unset. Please provide them (press Enter to skip):
  NAME: MyProject
  SUMMARY: A short description
  REPOSITORY (full URL, e.g. 'https://github.com/user/repo'): https://github.com/me/MyProject
  AUTHORS (comma-separated, e.g. 'Jane Doe, John Smith'): Stefano Zaghi
  EMAIL: stefano.zaghi@gmail.com
```

`init` also creates the standard project directory structure before writing files:

```
src/
docs/
.github/
  workflows/
  actions/
scripts/
```

Use `--yes` to skip prompts (useful when project variables are already in fobos or git config):

```bash
fobis scaffold init --yes
```

### `fobis scaffold list`

Lists all managed files grouped by category, without checking drift or modifying anything:

```bash
fobis scaffold list
```

Output:
```
Verbatim files (copied as-is, SHA-256 drift detection):
  .github/workflows/ci.yml
  .github/workflows/docs.yml
  .github/workflows/install.yml
  .github/actions/run-coverage-analysis/action.yml
  scripts/release.sh
  scripts/run_tests.sh
  scripts/install.sh
  scripts/compute-coverage.sh
  docs/package.json
  cliff.toml
  LICENSE.gpl3.md

Templated files ({{VAR}} substitution, rendered drift detection):
  .github/actions/setup-build-env/action.yml
  .github/workflows/release.yml

Symlinks (repo-root link to a canonical managed file):
  CONTRIBUTING.md → docs/guide/contributing.md
```

## Typical workflows

### Fixing drift across existing repos

Run this sequence in each repo:

```bash
cd ~/fortran/PENF
fobis scaffold status               # 1. see what drifted
fobis scaffold sync --dry-run       # 2. preview diffs
fobis scaffold sync                 # 3. apply, confirming each change
git add -A && git commit -m "chore: sync scaffold boilerplate"
```

### Bulk silent update

When you know the templates are correct and trust the update:

```bash
for repo in ~/fortran/*/; do
  echo "=== $repo ==="
  (cd "$repo" && fobis scaffold sync --yes)
done
```

### Bootstrapping a new Fortran project from scratch

```bash
mkdir MyProject && cd MyProject
git init

# Add project metadata to fobos first (optional — scaffold will prompt if absent):
cat > fobos <<'EOF'
[project]
name       = MyProject
summary    = A new Fortran project
repository = https://github.com/me/MyProject
email      = me@example.com
year       = 2026
authors    = My Name
EOF

# Create all boilerplate:
fobis scaffold init --yes

# The result:
# src/
# docs/.vitepress/config.mts  ← rendered with MyProject metadata
# docs/guide/contributing.md  ← contributing guide (project-owned after creation)
# CONTRIBUTING.md             ← symlink → docs/guide/contributing.md
# .github/workflows/ci.yml
# .github/workflows/docs.yml
# .github/workflows/release.yml
# .github/workflows/install.yml
# .github/actions/setup-build-env/action.yml
# .github/actions/run-coverage-analysis/action.yml
# scripts/release.sh
# scripts/run_tests.sh
# scripts/install.sh
# scripts/compute-coverage.sh
# cliff.toml
# LICENSE.gpl3.md
# fpm.toml
# docs/ford.md
# docs/package.json
```

### CI enforcement

Add a job to your main workflow to fail if boilerplate drifts:

```yaml
- name: Check scaffold boilerplate
  run: fobis scaffold status --strict
```

This catches cases where a template was updated in FoBiS but has not been applied to the repo yet. Only meaningful after upgrading FoBiS — pin the version in your workflow to avoid surprise failures.

## Known canonical resolutions

Scaffold deliberately resolves several inconsistencies that accumulated across older repos:

| Historical issue | Canonical resolution |
|-----------------|---------------------|
| `run-coverage` composite action name | Canonical: `run-coverage-analysis` — `sync` replaces the old `action.yml` |
| Legacy `install.sh` with hardcoded repo slug | Canonical: repo-agnostic `install.sh` — `sync` overwrites |
| `cliff.toml` with hardcoded `[remote.github]` slug | Canonical: empty `[remote.github]` (auto-detected) — `sync` replaces |
| `release.yml` with embedded docs deployment | Canonical: lightweight release-notes only; docs deployment belongs in `docs.yml` — `sync` rewrites |
| Missing `docs.yml` | Reported as `MISSING` by `status`; offered for creation by `sync` and `init` |

## How drift detection works

Scaffold is **stateless** — it does not maintain a tracking file or database.

For **verbatim** files: SHA-256 of the bundled canonical content is compared to SHA-256 of the on-disk file. Any difference is `OUTDATED`; absence is `MISSING`.

For **templated** files: scaffold first renders the template by substituting the current project variables into all `{{VAR}}` placeholders, then compares SHA-256 of the rendered content to SHA-256 of the on-disk file. If the on-disk file was created with different variable values, or if the template itself changed in a newer FoBiS version, it will show as `OUTDATED`.

Files not listed in the manifest are never touched — scaffold only manages what is explicitly listed.

## Error cases

| Situation | Behaviour |
|-----------|-----------|
| No fobos file | Variables fall back to git remote / git config / current year; `init` prompts interactively |
| fobos exists but `[project]` is absent | Same fallbacks as above |
| Git not available or no remote | Affected variables remain empty; `init` prompts for them |
| Template file not writable (permissions) | Python `PermissionError` propagates; the remaining files are still processed |
| `--strict` + any drift | Exits with code 1 after printing the full status report |

## Command reference

See [`scaffold` command](/reference/scaffold) for the complete option reference.
