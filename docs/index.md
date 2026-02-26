---
layout: home

hero:
  name: FoBiS
  text: Fortran Building System for poor people
  tagline: Automatic dependency-resolving build tool for modern Fortran projects — no makefiles, no boilerplate.
  actions:
    - theme: brand
      text: Quick Start
      link: /guide/quickstart
    - theme: alt
      text: Guide
      link: /guide/
    - theme: alt
      text: View on GitHub
      link: https://github.com/szaghi/FoBiS

features:
  - icon: ⚡
    title: Zero-configuration builds
    details: Drop FoBiS into any Fortran project and run `fobis build`. It recursively scans sources, resolves all `use` and `include` dependencies, and compiles in the correct order — automatically.
  - icon: 🔗
    title: Automatic dependency resolution
    details: Parses every source file for module definitions, use statements, and include directives. Builds and updates the full dependency hierarchy on each run, skipping up-to-date objects.
  - icon: ⚙️
    title: Multi-compiler support
    details: First-class support for GNU gfortran, Intel ifort/ifx, AMD flang, g95, IBM XL, NAG, PGI, NVIDIA nvfortran, and fully custom compilers. MPI, OpenMP, coarray, and coverage variants included.
  - icon: 📄
    title: fobos — the FoBiS makefile
    details: A concise INI-style configuration file replaces makefiles entirely. Define multiple build modes, templates, variables, and custom rules — all in one readable file.
  - icon: 🚀
    title: Parallel compilation
    details: Compile independent translation units concurrently with `-j N`. Dependency ordering is respected automatically; only the safe parallel frontier is compiled in parallel.
  - icon: 🌐
    title: Fetch GitHub dependencies
    details: Declare external FoBiS projects in a `[dependencies]` fobos section. Run `fobis fetch` to clone, pin to branch/tag/rev, and build — then `fobis build` picks them up automatically.
  - icon: 🔬
    title: Introspective doctests
    details: Embed micro-unit-tests directly inside Fortran comment docstrings. FoBiS generates, compiles, and runs volatile test programs automatically — inspired by Python's doctest module, no test harness needed.
  - icon: 🆓
    title: Free and open source
    details: Released under the GNU GPL v3 license. Free to use, study, modify, and distribute. Contributions welcome — see the contributing guidelines on GitHub.
---

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

## Projects using FoBiS

FoBiS is used to build a wide range of Fortran projects:

- **[ADAM](https://szaghi.github.io/adam/)** — Accelerated fluid Dynamics on Adaptive Mesh refinement grids &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/adam)
- **[BeFoR64](https://szaghi.github.io/BeFoR64/)** — Base64 encoding/decoding library for Fortran &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/BeFoR64)
- **[FACE](https://szaghi.github.io/FACE/)** — Fortran ANSI Colors and Escape sequences &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/FACE)
- **[FiNeR](https://szaghi.github.io/FiNeR/)** — Fortran INI ParseR and generator &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/FiNeR)
- **[FLAP](https://szaghi.github.io/FLAP/)** — Fortran command Line Arguments Parser for poor people &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/FLAP)
- **[FUNDAL](https://szaghi.github.io/FUNDAL/)** — Fortran UNified Device Acceleration Library &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/FUNDAL)
- **[FOSSIL](https://szaghi.github.io/FOSSIL/)** — FOrtran Stereo (si) Litography parser &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/FOSSIL)
- **[MORTIF](https://szaghi.github.io/MORTIF/)** — MORTon Indexer (Z-order) Fortran environment &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/MORTIF)
- **[MOTIOn](https://szaghi.github.io/MOTIOn/)** — Modular (HPC) Optimized Toolkit (for) IO (in fortra)n &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/MOTIOn)
- **[PENF](https://szaghi.github.io/PENF/)** — Portability Environment for Fortran poor people &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/PENF)
- **[StringiFor](https://szaghi.github.io/StringiFor/)** — Strings Fortran Manipulator with steroids &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/StringiFor)
- **[VecFor](https://szaghi.github.io/VecFor/)** — Vector algebra class for Fortran poor people &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/VecFor)
- **[VTKFortran](https://szaghi.github.io/VTKFortran/)** — pure Fortran VTK (XML) API &nbsp;|&nbsp; [GitHub](https://github.com/szaghi/VTKFortran)

## Author

**Stefano Zaghi** — [stefano.zaghi@cnr.it](mailto:stefano.zaghi@cnr.it) · [GitHub](https://github.com/szaghi)

## Copyrights

FoBiS.py is an open source project distributed under the [GPL v3](http://www.gnu.org/licenses/gpl-3.0.html) license. Anyone interested in using, developing, or contributing to FoBiS.py is welcome — see the [contributing guidelines](https://github.com/szaghi/FoBiS/blob/master/CONTRIBUTING.md).
