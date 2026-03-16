<div align="center">

# FoBiS — Fortran Building System

[![Latest Version](https://img.shields.io/pypi/v/FoBiS.py.svg)](https://pypi.org/project/FoBiS.py/)
[![GitHub tag](https://img.shields.io/github/tag/szaghi/FoBiS.svg)]()
[![Build Status](https://github.com/szaghi/FoBiS/actions/workflows/python-package.yml/badge.svg)](https://github.com/szaghi/FoBiS/actions)
[![codecov](https://codecov.io/gh/szaghi/FoBiS/graph/badge.svg)](https://codecov.io/gh/szaghi/FoBiS)
[![GitHub issues](https://img.shields.io/github/issues/szaghi/FoBiS.svg)]()
[![Supported Python versions](https://img.shields.io/badge/Py-%203.9,%203.10,%203.11,%203.12-blue.svg)]()

[![License](https://img.shields.io/badge/license-GNU%20GeneraL%20Public%20License%20v3,%20GPLv3-blue.svg)]()

> Automatic dependency-resolving build tool for modern Fortran projects — no makefiles, no boilerplate.

| ⚡ Zero-configuration builds | 🔗 Automatic dependency resolution | ⚙️ Multi-compiler support | 📄 fobos — the FoBiS makefile |
|---|---|---|---|
| Drop FoBiS into any Fortran project and run `fobis build`. It recursively scans sources, resolves all `use` and `include` dependencies, and compiles in the correct order — automatically. | Parses every source file for module definitions, use statements, and include directives. Builds and updates the full dependency hierarchy on each run, skipping up-to-date objects. | First-class support for GNU gfortran, Intel ifort/ifx, AMD flang, g95, IBM XL, NAG, PGI, NVIDIA nvfortran, and fully custom compilers. MPI, OpenMP, coarray, and coverage variants included. | A concise INI-style configuration file replaces makefiles entirely. Define multiple build modes, templates, variables, and custom rules — all in one readable file. |
| 🚀 Parallel compilation | 🌐 Fetch GitHub dependencies | 🔬 Introspective doctests | 🆓 Free and open source |
| Compile independent translation units concurrently with `-j N`. Dependency ordering is respected automatically; only the safe parallel frontier is compiled in parallel. | Declare external FoBiS projects in a `[dependencies]` fobos section. Run `fobis fetch` to clone, pin to branch/tag/rev, and build — then `fobis build` picks them up automatically. | Embed micro-unit-tests directly inside Fortran comment docstrings. FoBiS generates, compiles, and runs volatile test programs automatically — inspired by Python's doctest module, no test harness needed. | Released under the GNU GPL v3 license. Free to use, study, modify, and distribute. Contributions welcome — see the [contributing guidelines](CONTRIBUTING.md). |

**[Full documentation](https://szaghi.github.io/FoBiS/)**

</div>

## Why FoBiS?

Modern Fortran's module system is powerful — but tracking inter-module compilation order by hand in a makefile quickly becomes a nightmare as project size grows. Every time you add a module, rename a file, or restructure directories, the makefile needs manual updates.

**FoBiS solves this completely.** It parses source files on every invocation, rebuilds the dependency graph from scratch, and compiles in the correct order — with no configuration required for simple projects.

```bash
# That's it. FoBiS finds all programs, resolves all dependencies, compiles.
fobis build
```

For complex projects, a single `fobos` file in the project root replaces makefiles entirely:

```ini
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

```bash
fobis build -mode release
```

---

## Projects using FoBiS

- **[ADAM](https://szaghi.github.io/adam/)** — Accelerated fluid Dynamics on Adaptive Mesh refinement grids &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/adam)
- **[BeFoR64](https://szaghi.github.io/BeFoR64/)** — Base64 encoding/decoding library for Fortran &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/BeFoR64)
- **[FACE](https://szaghi.github.io/FACE/)** — Fortran ANSI Colors and Escape sequences &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/FACE)
- **[FiNeR](https://szaghi.github.io/FiNeR/)** — Fortran INI ParseR and generator &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/FiNeR)
- **[FLAP](https://szaghi.github.io/FLAP/)** — Fortran command Line Arguments Parser &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/FLAP)
- **[FUNDAL](https://szaghi.github.io/FUNDAL/)** — Fortran UNified Device Acceleration Library &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/FUNDAL)
- **[FOSSIL](https://szaghi.github.io/FOSSIL/)** — FOrtran Stereo (si) Litography parser &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/FOSSIL)
- **[MORTIF](https://szaghi.github.io/MORTIF/)** — MORTon Indexer (Z-order) Fortran environment &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/MORTIF)
- **[MOTIOn](https://szaghi.github.io/MOTIOn/)** — Modular (HPC) Optimized Toolkit (for) IO (in fortra)n &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/MOTIOn)
- **[PENF](https://szaghi.github.io/PENF/)** — Portability Environment for Fortran &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/PENF)
- **[StringiFor](https://szaghi.github.io/StringiFor/)** — Strings Fortran Manipulator with steroids &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/StringiFor)
- **[VecFor](https://szaghi.github.io/VecFor/)** — Vector algebra class for Fortran &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/VecFor)
- **[VTKFortran](https://szaghi.github.io/VTKFortran/)** — pure Fortran VTK (XML) API &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/VTKFortran)

---

## Author

**Stefano Zaghi** — [stefano.zaghi@cnr.it](mailto:stefano.zaghi@cnr.it) · [GitHub](https://github.com/szaghi)

## Copyrights

FoBiS is an open source project distributed under the [GPL v3](http://www.gnu.org/licenses/gpl-3.0.html) license. Anyone interested in using, developing, or contributing to FoBiS is welcome — see the [contributing guidelines](CONTRIBUTING.md).

---

![Screencast](examples/cumbersome_dependency_program_interdepent/cumbersome-cast.gif)
