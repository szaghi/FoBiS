---
title: Contributing
---

# Contributing

This is a FOSS project — anyone interested in using, developing, or contributing
is welcome. The project follows a KISS (Keep It Simple and Stupid) philosophy.

## Reporting Issues

- Open a ticket on the repository **GitHub Issues** page
- Clearly describe the problem, including steps to reproduce for bugs
- Note the earliest version you know has the issue

## Pull Requests

1. Fork the repository on GitHub
2. Create a topic branch from the default branch (`main` or `master`):
   ```bash
   git checkout -b fix/my_contribution
   ```
3. Test your changes with `fobis build && bash scripts/run_tests.sh`
4. Check for unnecessary whitespace: `git diff --check`
5. Submit a pull request with a clear commit message

## Fortran Coding Style

- **Clarity over brevity**: `real :: gas_ideal_air` is better than `real :: gia`
- Single-character variable names only for loop counters
- Name all constants
- `implicit none` in every module and program
- Declare `intent` for all procedure arguments, ordered: pass arg → `inout` → `in` → `out` → optional
- Indent with spaces (not tabs), consistently with the surrounding code
- No trailing whitespace; blank lines must contain no spaces
- Use `>, <, ==` instead of `.gt., .lt., .eq.`
- Avoid Windows-style CRLF line endings

### Recommended git whitespace settings

```ini
[color]
  ui = true
[color "diff"]
  whitespace = red reverse
[core]
  whitespace = fix,-indent-with-non-tab,trailing-space,cr-at-eol
```

## Commit style

Use [Conventional Commits](https://www.conventionalcommits.org/) so that `CHANGELOG.md` is generated automatically from the git log:

| Prefix | Purpose | Changelog section |
|--------|---------|-------------------|
| `feat:` | New feature or capability | New features |
| `fix:` | Bug fix | Bug fixes |
| `perf:` | Performance improvement | Performance |
| `refactor:` | Code restructuring | Refactoring |
| `docs:` | Documentation only | Documentation |
| `test:` | Tests | Testing |
| `build:` | Build system | Build system |
| `ci:` | CI/CD pipeline | CI/CD |
| `chore:` | Maintenance | Miscellaneous |

Append `!` for breaking changes (`feat!:`, `fix!:`). Reference issues with `#123` — they are auto-linked.

```
feat: add a parallel reader for binary files
fix(io): handle empty input files (#42)
feat!: rename the init procedure to initialize
```

---

## Creating a release

Releases are fully automated via `scripts/release.sh` and GitHub Actions. The only steps needed are:

```bash
# Install git-cliff once (or download it from https://github.com/orhun/git-cliff/releases)
cargo install git-cliff

# Then, to release:
scripts/release.sh --patch   # v1.2.3 → v1.2.4
scripts/release.sh --minor   # v1.2.3 → v1.3.0
scripts/release.sh --major   # v1.2.3 → v2.0.0
scripts/release.sh v2.1.0    # explicit version
```

`release.sh` will ask for confirmation, then:

1. Regenerate `CHANGELOG.md` from the git log via [git-cliff](https://git-cliff.org/)
2. Update `VERSION`
3. Commit with `chore(release): vX.Y.Z`
4. Create an annotated git tag
5. Push commit + tag

Pushing the tag triggers the GitHub Actions release workflow, which automatically:
- Packages a versioned tarball
- Publishes a GitHub release with the changelog section as release notes, attaching the tarball and `scripts/install.sh`

Tests, coverage and this documentation site are not part of the release workflow: they run
on every branch push (`ci.yml`, `docs.yml`), so the tagged commit has already been tested
and its documentation deployed.
