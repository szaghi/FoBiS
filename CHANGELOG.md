# Changelog

All notable changes to FoBiS.py are documented here.
Versions follow [Semantic Versioning](https://semver.org/).
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [3.6.5] — 2026-03-16
### Changed
- Flatten source layout to standard Python conventions


### release
- Modernise bump.sh and add git-cliff changelog


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
- **install**: Add GitHub-hosted project install via fobis install <repo>


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


## [3.0.6] — 2024-11-05
### bugfix
- Open file encoding options differences python 2.X vs 3.X

- Fix bug of preprocessing parsed files



