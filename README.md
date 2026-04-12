<div align="center">

# FoBiS — Fortran Building System

[![Latest Version](https://img.shields.io/pypi/v/FoBiS.py.svg)](https://pypi.org/project/FoBiS.py/)
[![GitHub tag](https://img.shields.io/github/tag/szaghi/FoBiS.svg)]()
[![Build Status](https://github.com/szaghi/FoBiS/actions/workflows/python-package.yml/badge.svg)](https://github.com/szaghi/FoBiS/actions)
[![Coverage](https://img.shields.io/endpoint?url=https://szaghi.github.io/FoBiS/coverage-badge.json)](https://szaghi.github.io/FoBiS/)
[![GitHub issues](https://img.shields.io/github/issues/szaghi/FoBiS.svg)]()
[![Supported Python versions](https://img.shields.io/badge/Py-%203.10,%203.11,%203.12-blue.svg)]()

[![License](https://img.shields.io/badge/license-GNU%20GeneraL%20Public%20License%20v3,%20GPLv3-blue.svg)]()

> Automatic dependency-resolving build tool for modern Fortran projects — no makefiles, no boilerplate.
> Package manger highly integrated with GitHub, install and fetch project dependencies.
> Add instrospective doctests to your Fortran project and exploit AI-powered programmatic buildings with the provided AI skill.

<div>
<table>
<tr>
<td><b>⚡ Zero-configuration builds</b><br><sub>Drop FoBiS into any Fortran project and run <code>fobis build</code>. It scans sources, resolves all <code>use</code>, <code>include</code>, and module dependencies automatically, and compiles in the correct order — no makefiles, no boilerplate. Convention-based discovery finds <code>src/</code>, <code>source/</code>, and <code>app/</code> directories automatically. <a href="https://szaghi.github.io/FoBiS/guide/quickstart">Quick start</a></sub></td>
<td><b>📄 fobos — the FoBiS makefile</b><br><sub>A concise INI-style configuration file replaces makefiles entirely. Define multiple build modes, templates, variables, custom rules, feature flags, multi-target sections, and hooks — all in one readable file. <a href="https://szaghi.github.io/FoBiS/fobos/">fobos reference</a></sub></td>
</tr>
<tr>
<td><b>🌐 GitHub integration</b><br><sub>Declare dependencies in a <code>[dependencies]</code> fobos section — <code>fobis fetch</code> clones, pins to branch/tag/rev/semver, and pre-builds them; <code>fobis build</code> picks them up automatically. Reproducible builds via <code>fobos.lock</code>. Install any GitHub-hosted FoBiS project directly with <code>fobis install user/repo</code>. <a href="https://szaghi.github.io/FoBiS/advanced/fetch">Fetch deps</a> · <a href="https://szaghi.github.io/FoBiS/advanced/lock-file">Lock file</a></sub></td>
<td><b>🏗️ Named build profiles &amp; feature flags</b><br><sub>One-word compiler flag presets (<code>debug</code>, <code>release</code>, <code>asan</code>, <code>coverage</code>) for every supported compiler. Feature flags let you activate named compile-time options without separate build modes — mix and match freely. <a href="https://szaghi.github.io/FoBiS/advanced/build-profiles">Build profiles</a> · <a href="https://szaghi.github.io/FoBiS/advanced/features">Feature flags</a></sub></td>
</tr>
<tr>
<td><b>🧪 Integrated test runner &amp; coverage</b><br><sub><code>fobis test</code> discovers, compiles, and runs all Fortran test programs — no external harness needed. <code>fobis coverage</code> generates HTML/XML reports via gcovr or lcov and can fail CI when coverage drops below a threshold. <a href="https://szaghi.github.io/FoBiS/advanced/testing">Test runner</a> · <a href="https://szaghi.github.io/FoBiS/reference/coverage">Coverage</a></sub></td>
<td><b>🔬 Introspective doctests</b><br><sub>Embed micro-unit-tests directly inside Fortran comment docstrings. FoBiS generates, compiles, and runs volatile test programs automatically — inspired by Python's doctest module, no test harness needed. <a href="https://szaghi.github.io/FoBiS/advanced/doctests">Doctests</a></sub></td>
</tr>
<tr>
<td><b>⚡ Build cache</b><br><sub>Content-addressed cache keyed on source commit, compiler, and flags — reuses object files across clean builds and branch switches. <code>fobis cache list/clean</code> for housekeeping. <a href="https://szaghi.github.io/FoBiS/advanced/cache">Build cache</a></sub></td>
<td><b>🤖 Introspect &amp; Claude Code skill</b><br><sub><code>fobis introspect --all</code> emits machine-readable JSON of the full project graph — sources, compiler flags, dependencies, targets. Powers the bundled <code>/fobis</code> Claude Code skill for AI-assisted builds right in your editor. <a href="https://szaghi.github.io/FoBiS/reference/introspect">introspect</a> · <a href="https://szaghi.github.io/FoBiS/guide/claude-skill">Claude skill</a></sub></td>
</tr>
<tr>
<td><b>📋 Scaffold — boilerplate sync</b><br><sub>Keep CI workflows, docs configs, license files, and scripts identical across all your Fortran repos. <code>fobis scaffold status</code> shows drift; <code>fobis scaffold sync</code> fixes it; <code>fobis scaffold init</code> bootstraps new projects. All templates bundled inside FoBiS — no extra dependencies. <a href="https://szaghi.github.io/FoBiS/reference/scaffold">Scaffold reference</a></sub></td>
<td><b>🧠 LLM commit messages</b><br><sub>Generate well-formed <a href="https://www.conventionalcommits.org/">Conventional Commits</a> messages for staged changes via a local LLM. Supports <a href="https://ollama.com">Ollama</a> and any OpenAI-compatible endpoint (LM Studio, vLLM, llama.cpp) — no cloud account, no API key, no data leaving your machine. <a href="https://szaghi.github.io/FoBiS/advanced/commit">LLM commit guide</a></sub></td>
</tr>
</table>
</div>

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

| **zero-configuration build** | **simplify complex dependency** |
|:---:|:---:|
| ![basic build](docs/public/gifs/01_basic_build.gif) | ![complex dependancy](docs/public/gifs/04_dependent_build.gif) |
| **GH integration, project install** | **GH integration, dependancies fetch** |
| ![project install](docs/public/gifs/06_install.gif) | ![dependancies fetch](docs/public/gifs/07_fetch.gif) |

## Scaffold — boilerplate management

`fobis scaffold` keeps CI workflows, docs configs, license files, and other boilerplate in sync across all your Fortran repos. All templates are bundled inside FoBiS — no external dependencies.

```bash
fobis scaffold status          # drift report: OK / OUTDATED / MISSING per file
fobis scaffold sync --dry-run  # preview diffs without writing
fobis scaffold sync --yes      # apply all updates silently
fobis scaffold init            # bootstrap a new project (creates src/, docs/, .github/, …)
fobis scaffold list            # list all managed files and their categories
```

Project variables (`{{NAME}}`, `{{AUTHORS}}`, `{{REPOSITORY}}`, …) are resolved from the fobos `[project]` section, the git remote URL, and `git config`. See the [scaffold reference](https://szaghi.github.io/FoBiS/reference/scaffold) for full details.

## LLM-assisted commit messages

`fobis commit` generates [Conventional Commits](https://www.conventionalcommits.org/) messages for your staged changes using a local LLM — no cloud account, no API key, no data leaving your machine.

```bash
# Stage your changes as usual
git add fobis/Commit.py fobis/cli/commit.py

# Generate the message (print only — you review before committing)
fobis commit

# Generate and commit in one step after interactive review
fobis commit --apply

# Persist your LLM settings
fobis commit --init-config     # creates ~/.config/fobis/config.ini
fobis commit --show-config     # inspect effective settings
```

Works with [Ollama](https://ollama.com) (default) and any OpenAI-compatible server (LM Studio, vLLM, llama.cpp). The default model is `qwen3-coder:30b-a3b-q4_K_M` — a fast mixture-of-experts model that produces excellent commit messages.

See the [LLM commit messages guide](https://szaghi.github.io/FoBiS/advanced/commit) for setup instructions, model recommendations, and worked examples.

## Showcases

> Projects using FoBiS:

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

## Author

**Stefano Zaghi** — [stefano.zaghi@gmail.com](mailto:stefano.zaghi@gmail.com) · [GitHub](https://github.com/szaghi)

## Copyrights

FoBiS is an open source project distributed under the [GPL v3](http://www.gnu.org/licenses/gpl-3.0.html) license. Anyone interested in using, developing, or contributing to FoBiS is welcome — see the [contributing guidelines](CONTRIBUTING.md).
