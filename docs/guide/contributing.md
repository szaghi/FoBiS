# Contributing

Thank you for contributing to FoBiS.py! This guide covers everything you need to go from idea to merged pull request.

## Quick start

```bash
# 1. Fork on GitHub, then clone your fork
git clone https://github.com/<your-username>/FoBiS.git
cd FoBiS

# 2. Install in editable mode with all dev tools
make dev          # equivalent to: pip install -e ".[dev]"

# 3. Verify the setup
make test         # 51 tests, 1 skipped (opencoarrays)
make lint         # ruff check + format check
```

::: tip System requirement
The test suite compiles real Fortran code. **`gfortran` must be in `PATH`** before running tests.
On Debian/Ubuntu: `sudo apt-get install gfortran`
On macOS: `brew install gcc`
:::

## Branching model

```
master   ← stable, tagged releases only
develop  ← integration branch — open PRs here
release/vX.Y.Z  ← short-lived, created by release.sh
```

- Branch off `develop` for all new work
- Use descriptive branch names: `fix/version-callback`, `feat/nvfortran-coarray`, `docs/contributing`

## Commit messages

FoBiS.py uses [Conventional Commits](https://www.conventionalcommits.org/). The `CHANGELOG.md` is generated automatically from commit messages by `git-cliff`, so the format matters.

```
<type>(<scope>): <description>

[optional body — explain the why, not the what]

[optional footers: Closes #N, BREAKING CHANGE: ...]
```

| Type | When to use | Appears in changelog |
|------|-------------|----------------------|
| `feat` | New feature | ✅ Added |
| `fix` | Bug fix | ✅ Fixed |
| `perf` | Performance improvement | ✅ Performance |
| `refactor` | Code restructure, no feature/fix | ✅ Changed |
| `docs` | Documentation only | ✅ Documentation |
| `test` | Tests only | — |
| `ci` | CI/CD pipeline | — |
| `build` | Build system | — |
| `chore` | Tooling, maintenance | — |

**Examples:**
```
fix(cli): restore -v flag broken since version migration
feat(compiler): add nvfortran coarray support
docs(fetch): clarify use=fobos vs use=sources behaviour
```

## Development workflow

### Running the test suite

```bash
# Full suite
make test

# Single test module
pytest tests/test_build.py

# Single parametrized case
pytest tests/test_build.py::test_build[12]

# Run with coverage report
pytest --cov=fobis --cov-report=term-missing

# Skip slow build tests, run only unit tests
pytest tests/test_fetch.py
```

Test fixtures live in `tests/<type>-test<N>/` directories. Each contains a `fobos` file and Fortran sources. The test runs `fobis build`, checks the result, then `fobis clean`.

### Adding a new test scenario

1. Create `tests/build-test<N>/` with a `fobos` and minimal Fortran source
2. The parametrized range in `tests/test_build.py` picks it up automatically — bump `range(1, N+1)`
3. Run `pytest tests/test_build.py::test_build[N]` to verify

### Linting and formatting

```bash
make lint         # check only — safe to run anytime
make fmt          # auto-fix lint issues and apply formatting
```

FoBiS.py uses [Ruff](https://docs.astral.sh/ruff/) for both linting and formatting. Configuration lives in `pyproject.toml` under `[tool.ruff]`. The CI `lint` job will fail if either check reports errors.

## CI pipeline

Every push to `master` (and every PR targeting `master`) runs four jobs:

```
lint ──┐
       ├──► publish  (tag v* only)
test ──┤
       │
build ─┘  (3 OS × 4 Python versions)
```

| Job | Runs on | What it checks |
|-----|---------|----------------|
| `lint` | ubuntu, Python 3.12 | `ruff check` + `ruff format --check` |
| `test` | ubuntu, Python 3.12 + gfortran | full `pytest` suite |
| `build` | ubuntu / macOS / Windows × Python 3.10–3.12 | `pip install -e .` + entry-point smoke test |
| `publish` | ubuntu, Python 3.12 | builds wheel/sdist, pushes to PyPI via OIDC |

`publish` only runs when the commit is a `v*` tag **and** all three other jobs pass.

::: tip Before opening a PR
Run `make lint && make test` locally. The CI will reject PRs that fail either check, and fixing them after the fact costs extra round-trips.
:::

## Pull request process

1. **Open an issue first** for anything non-trivial — this avoids duplicate work and aligns expectations before you invest time coding
2. Fork the repo and push your branch to your fork
3. Open a PR **against `develop`**, not `master`
4. Fill in the PR description:
   - What problem does this solve?
   - How was it tested?
   - Any breaking changes?
5. Ensure all CI jobs are green
6. A maintainer will review and merge; small fixes may be squashed

## Reporting bugs

Use the [GitHub issue tracker](https://github.com/szaghi/FoBiS/issues). Include:

- FoBiS.py version (`fobis -v`)
- Python version (`python --version`)
- Compiler and version (`gfortran --version`)
- Operating system
- Minimal reproducer (fobos + Fortran source if possible)

## Creating a release (maintainers only)

Releases are created from the `develop` branch with `release.sh`. The script handles everything: version bump, changelog generation, tests, git flow, and tag push. PyPI publish is triggered automatically by the tag.

```bash
# Ensure develop is clean and up to date
git checkout develop
git pull origin develop

# Bump patch / minor / major — or set an explicit version
./release.sh --patch        # 3.6.x → 3.6.x+1
./release.sh --minor        # 3.6.x → 3.7.0
./release.sh 4.0.0          # explicit

# What release.sh does automatically:
# 1. Creates release/vX.Y.Z branch
# 2. Bumps __version__ in fobis/__init__.py
# 3. Regenerates docs/guide/changelog.md via git-cliff (CHANGELOG.md symlinks to it)
# 4. Runs the full test suite (pytest)
# 5. Commits, merges to master, tags vX.Y.Z, pushes
# 6. Merges master back to develop, pushes
# 7. Deletes the local release branch
# → Tag push triggers CI: lint → test → build → PyPI publish
```

::: warning Prerequisites
`git-cliff` must be installed: `pipx install git-cliff`
:::

## Project layout

```
fobis/              Python package (source of truth)
tests/              pytest suite + Fortran fixture directories
docs/               VitePress documentation site
  guide/            Installation, quickstart, compilers, contributing
  fobos/            fobos file reference
  reference/        CLI command reference
  advanced/         Advanced topics
  examples/         Worked examples
.github/workflows/  CI/CD (python-package.yml)
pyproject.toml      Package metadata, ruff config, pytest config
cliff.toml          git-cliff changelog configuration
release.sh          Release automation script
Makefile            Developer convenience targets
```
