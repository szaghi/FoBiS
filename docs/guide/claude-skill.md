# Claude Code Skill

FoBiS.py ships a [Claude Code](https://claude.ai/claude-code) skill that turns Claude into an expert FoBiS.py assistant. Install it once and Claude can answer questions, write `fobos` files, diagnose build errors, and help with every feature — without you needing to look up the documentation.

## Installation

The skill lives at `~/.claude/skills/fobis/SKILL.md`. Clone it:

```bash
mkdir -p ~/.claude/skills/fobis
curl -sSL https://raw.githubusercontent.com/szaghi/FoBiS/master/.claude/skills/fobis/SKILL.md \
  -o ~/.claude/skills/fobis/SKILL.md
```

Or copy it manually from the repository root:

```bash
cp /path/to/FoBiS/.claude/skills/fobis/SKILL.md ~/.claude/skills/fobis/SKILL.md
```

## Using the skill

Once installed, simply invoke it with `/fobis` in any Claude Code session:

```
/fobis write a fobos file for my project with debug and release modes
```

```
/fobis my build fails with "Module 'utils' not found" — how do I debug this?
```

```
/fobis how do I add PENF as a GitHub dependency?
```

```
/fobis show me a CI script that uses fobis build --json
```

Claude also auto-triggers the skill for questions that mention `fobos`, `FoBiS`, or Fortran build configuration — you don't always need the `/fobis` prefix.

## What the skill knows

| Topic | Coverage |
|---|---|
| **fobos file authoring** | Single-mode, multi-mode, templates, variables, rules, `[project]` section |
| **All CLI commands** | `build`, `clean`, `fetch`, `install`, `rule`, `doctests` with correct flags |
| **All compilers** | gnu, intel, intel_nextgen, g95, opencoarrays-gnu, pgi, ibm, nag, nvfortran, amd, custom |
| **Library builds** | Static and shared library configuration; `--mklib`, `--ar`, `--ranlib` |
| **Dependency management** | `[dependencies]` section, `use=sources` vs `use=fobos`, `fetch` workflow |
| **JSON output** | All three schemas (build/clean/fetch), bash and Python CI patterns |
| **Error diagnosis** | Module-not-found decision tree, up-to-date builds, flag heritage issues |
| **Advanced features** | Parallel compilation, `--graph`, `--makefile`, `cflags_heritage`, doctests |
| **Architecture** | Module map, build and fetch data-flow |

## Example interactions

**Write a fobos file:**
```
/fobis I have sources in src/, want debug (-O0 -g -Wall) and release (-O3) modes,
       using gfortran, output goes to build/debug/ and build/release/
```

**Diagnose a build error:**
```
/fobis Fatal Error: Module 'penf_b_size' not found — what's wrong?
```

**Set up GitHub dependencies:**
```
/fobis add PENF v1.5.0 and json-fortran (main branch, use=fobos) as dependencies
```

**CI integration with JSON output:**
```
/fobis write a GitHub Actions step that runs fobis build --json and fails fast
```

## Skill file location

The SKILL.md is in the repository at `.claude/skills/fobis/SKILL.md`. It is a plain Markdown file — you can read and edit it to customize the behaviour for your workflow.
