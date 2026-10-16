---
layout: home

hero:
  name: FoBiS
  text: The Fortran Building System
  tagline: Builds modern Fortran projects with no makefile, by reading the sources. Then tests them, checks their numerical results, lints and reviews them, and gives an AI assistant the facts to work on them, with every claim checked.
  actions:
    - theme: brand
      text: Tutorials
      link: /tutorial/
    - theme: alt
      text: Install
      link: /guide/installation
    - theme: alt
      text: Cookbook
      link: /cookbook/
    - theme: alt
      text: Reference
      link: /reference/
    - theme: alt
      text: View on GitHub
      link: https://github.com/szaghi/FoBiS

features:
  - icon: ⚡
    title: Builds with no makefile
    details: FoBiS parses every source for modules, uses and includes, and compiles in dependency order, incrementally, in parallel, C files included. fobis new starts a project; a fobos file names the modes (debug, release, a library); editors get a compile_commands.json.
    link: /tutorial/first-steps/01-first-build
    linkText: A first build
  - icon: 📦
    title: Dependencies from GitHub
    details: Declare FoBiS projects in [dependencies]; fobis fetch clones them at a tag, branch, commit or semver range and locks the commits. Build them with your sources, or as libraries with their own fobos; use a local directory as is, or a dependency for the tests only.
    link: /tutorial/first-steps/05-dependencies
    linkText: Dependencies
  - icon: 🧪
    title: Tests, doctests, coverage
    details: Every program in test/ is a test, run in parallel or through mpirun; checks in the documentation comments are doctests; an instrumented mode and fobis coverage give the report, and a threshold for CI.
    link: /tutorial/first-steps/04-tests
    linkText: Tests
  - icon: 🎯
    title: Verified numerical results
    details: Declare cases and the quantities they print; compare them with references within tolerances, across compilers and checked builds, against the previous revision, with confidence intervals on timings and estimates of rounding and discretisation error.
    link: /cookbook/verification#accept-results-then-catch-a-change
    linkText: Verification
  - icon: 🩺
    title: A linter that sees the build
    details: Bug-prone, obsolescent and non-portable constructs, OpenMP data races, OpenACC and MPI defects, analysed with the defines of the mode you build. Baselines, inline suppressions with reasons, automatic fixes, SARIF, reviews of the lines a change touches.
    link: /cookbook/analysis
    linkText: Linting
  - icon: 🤖
    title: AI assistance on facts
    details: Explanations of failed builds and crashes, answers cited from the standards and your sources, tests kept only when they build, run and check. Local open models; an MCP server gives any agent the same tools.
    link: /ai/
    linkText: Analysis and AI
  - icon: 🧭
    title: Many repositories as one
    details: A dashboard of releases due, CI, drift and stale pins across your projects; commands in dependency order; a check of everything downstream before you release; the release train.
    link: /cookbook/ecosystem
    linkText: Ecosystem
  - icon: 🖥️
    title: From a laptop to a cluster
    details: The same cases, tests and benchmarks submitted through Slurm, with the node's facts in the provenance; profiles from gprof, callgrind and Nsight Systems mapped to your procedures. One offline file for air-gapped machines.
    link: /cookbook/hpc#declare-the-scheduler
    linkText: Clusters
---

## Quick start

```bash
pip install FoBiS.py
cd my-fortran-project
fobis build
```

FoBiS finds the sources (in `src/`, `source/`, `app/`, or the current directory), resolves the modules every file
uses, compiles them in order and links every program it found. The [first tutorial](/tutorial/first-steps/01-first-build)
starts here; the [tutorials](/tutorial/) go on, track by track, to verified results, code review and AI assistance.

| **a first build** | **a project and its dependencies** |
|:---:|:---:|
| ![basic build](/gifs/01_basic_build.gif) | ![dependent build](/gifs/04_dependent_build.gif) |
| **fetching dependencies** | **an ecosystem's dashboard** |
| ![fetch](/gifs/07_fetch.gif) | ![ecosystem dashboard](/gifs/09_ecosystem_dashboard.gif) |

## Projects built with FoBiS

- **[ADAM](https://szaghi.github.io/adam/)** — Accelerated fluid Dynamics on Adaptive Mesh refinement grids
- **[BeFoR64](https://szaghi.github.io/BeFoR64/)** — Base64 encoding/decoding library for Fortran
- **[FACE](https://szaghi.github.io/FACE/)** — Fortran ANSI Colors and Escape sequences
- **[FiNeR](https://szaghi.github.io/FiNeR/)** — Fortran INI ParseR and generator
- **[FLAP](https://szaghi.github.io/FLAP/)** — Fortran command Line Arguments Parser
- **[foresight](https://szaghi.github.io/foresight/)** — gnuplot-like interactive plots from pure Fortran
- **[FUNDAL](https://szaghi.github.io/FUNDAL/)** — Fortran UNified Device Acceleration Library
- **[FOSSIL](https://szaghi.github.io/FOSSIL/)** — FOrtran Stereo (si) Litography parser
- **[MORTIF](https://szaghi.github.io/MORTIF/)** — MORTon Indexer (Z-order) Fortran environment
- **[MOTIOn](https://szaghi.github.io/MOTIOn/)** — Modular (HPC) Optimized Toolkit (for) IO (in fortra)n
- **[PENF](https://szaghi.github.io/PENF/)** — Portability Environment for Fortran
- **[StringiFor](https://szaghi.github.io/StringiFor/)** — Strings Fortran Manipulator with steroids
- **[VecFor](https://szaghi.github.io/VecFor/)** — Vector algebra class for Fortran
- **[VTKFortran](https://szaghi.github.io/VTKFortran/)** — pure Fortran VTK (XML) API

## Author

**Stefano Zaghi** — [stefano.zaghi@cnr.it](mailto:stefano.zaghi@cnr.it) · [GitHub](https://github.com/szaghi)

## Copyrights

FoBiS.py is distributed under the [GPL v3](http://www.gnu.org/licenses/gpl-3.0.html) license. Contributions are
welcome: see [Contributing](/guide/contributing).
