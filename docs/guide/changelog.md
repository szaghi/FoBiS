# Changelog

All notable changes to FoBiS.py are documented here.
Versions follow [Semantic Versioning](https://semver.org/).
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [3.7.2] — 2026-03-16
### Added
- **cli**: Add --json structured output flag to build, clean, and fetch


## [3.7.1] — 2026-03-16
### Documentation
- **advanced**: Add architecture guide with module map and data-flow diagrams


## [3.7.0] — 2026-03-16
### Changed
- Drop Python 3.9, modernize type hints to PEP 604/585 syntax ⚠ BREAKING CHANGE


## [3.6.13] — 2026-03-16
### Fixed
- **cli**: Resolve ruff lint failures in fobis/cli sub-package


## [3.6.12] — 2026-03-16
### Changed
- **cli**: Split monolithic cli_parser.py into per-command subpackage


## [3.6.11] — 2026-03-16
### Fixed
- **cliff**: Fix regex and catch-all parser silencing all git-cliff warnings


## [3.6.10] — 2026-03-16
### Fixed
- Replace X | None union syntax with Optional for Python 3.9 compat


## [3.6.9] — 2026-03-16
### Changed
- Remove Python 2 dead code, add type hints, and enable coverage


### Documentation
- **changelog**: Make git-cliff write directly to docs/guide/changelog.md


### Fixed
- Eliminate shell injection, resource leaks, and stale test artifacts


## [3.6.8] — 2026-03-16
### Fixed
- **cli**: Restore -v / --version flag broken since version migration


## [3.6.6] — 2026-03-16
### Fixed
- **release**: Handle pipx-installed build module in release script


## [3.6.5] — 2026-03-16
### Changed
- Flatten source layout to standard Python conventions


## [3.6.2] — 2026-03-15
### Fixed
- **deps**: Remove deprecated typer[all] extra


## [3.6.0] — 2026-03-15
### Added
- **cli**: Replace argparse with Typer; add shell autocomplete ⚠ BREAKING CHANGE


## [3.5.4] — 2026-03-05
### Fixed
- **builder**: Include transitive deps of submodules in link command


## [3.5.3] — 2026-02-27
### Fixed
- **fetch**: Fix deps_dir treated as dependency and missing update


## [3.5.2] — 2026-02-27
### Added
- **fetch**: Add per-dependency use=sources|fobos integration mode


## [3.5.1] — 2026-02-27
### Added
- **builder**: Add configurable archiver and ranlib for static libraries


## [3.5.0] — 2026-02-27
### Added
- **fobos**: Support multiple templates and detect circular references


## [3.4.1] — 2026-02-27
### Added
- **fobos**: Add optional [project] section with name and authors

- **fobos**: Add version option to [project] section with git tag sync

- **fobos**: Add summary option to [project] section

- **fobos**: Add repository option to [project] section for remote url

- **fobos**: Add website option to [project] section

- **fobos**: Add email option to [project] section


### Documentation
- **fobos**: Add [project] section reference page with all options


## [3.4.0] — 2026-02-27
### Added
- **install**: Add GitHub-hosted project install via fobis install `repo`


## [3.3.4] — 2026-02-26
### Documentation
- **readme**: Add link to github pages documentation site


## [3.3.3] — 2026-02-26
### Documentation
- **readme**: Rewrite readme to mirror the vitepress landing page


## [3.3.2] — 2026-02-26
### Documentation
- Add vitepress documentation site with gh pages deployment


## [3.3.1] — 2026-02-26
### Fixed
- **ci**: Fix FoBiS.py command not found on Windows runners


## [3.3.0] — 2026-02-26
### Added
- **fetch**: Add fetch subcommand for GitHub Fortran dep management


## [3.2.2] — 2026-02-26
### Added
- **setup**: Add fobis console script entry point


## [3.2.1] — 2026-02-20
### Fixed
- **gcov**: Remove unused past.utils import that broke CI

- **bump.sh**: Prevent mid-release failure due to stale branches and PyPI filename change


## [3.2.0] — 2026-02-20
### Added
- **gcov**: Add mermaid pie charts to markdown coverage reports


## [3.1.0] — 2025-05-20
### Added
- Add AMD flang support

- **fobos**: Refactor fobos templates handling



