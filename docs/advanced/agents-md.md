# Instructions for agents

Coding agents (Claude Code, Codex, Cursor, Copilot...) read a project's `AGENTS.md` (Claude Code: `CLAUDE.md`)
before working on it. Written by hand, that file goes stale: a mode is renamed, a case is added, the tests move,
and the agent builds the wrong thing with confidence. `fobis agents-md` generates the part of it that is fact —
how to build, test and verify, what the code looks like — from the fobos and the sources.

```bash
fobis agents-md                    # write (or update) the generated block of AGENTS.md
fobis agents-md -o CLAUDE.md       # the same block in CLAUDE.md (repeatable: -o AGENTS.md -o CLAUDE.md)
fobis agents-md --check            # CI: exit 1 when the block is stale, with the diff
fobis agents-md --print            # print the block, write nothing
fobis agents-md --print --json     # the facts, for scripts and agents
```

## The block

The generated text lives between two markers; everything outside them is yours and is never changed:

```markdown
# My project

Our conventions, the physics, who to ask...

<!-- fobis:begin agents-md -->
... generated ...
<!-- fobis:end agents-md -->

More hand-written notes.
```

A new file gets a title and the block; a file without markers gets the block appended; an existing block is
replaced in place. Markers that are unbalanced or repeated stop the command (exit 2) instead of guessing.

What the block says, and where each fact comes from:

| Section | Facts | Source |
|---------|-------|--------|
| Modes | compiler, what the mode builds (program, static/shared library, every program), optimisation level, debug information, runtime checks, parallel models (OpenMP, OpenACC, CUDA Fortran, coarrays, MPI), `-D` defines; the default mode; environment setup lines | fobos modes (templates, `$variables`, build profiles applied), `[verification] setup` |
| Commands | fetch, build, tests (when the test directory has programs), doctests (when sources carry them), runtime-check shadows, lint (with the `[lint]` settings), review, code queries, the fobos rules with their help | fobos, test directory, sources |
| Verifying a change | the declared cases: what they run, ranks and threads, quantities, tolerances, whether the committed reference exists, assessment families and budgets; or a note that no case is declared | `[case:*]`, `[assess:*]`, references directory |
| Code facts | sources of the analysed mode (files by extension, modules), programs, dependencies, the kinds of `real`/`integer`/`complex`/`logical` declarations as written (with their decimal precision and the module that defines or exports them), units without `implicit none`, OpenMP/OpenACC files, device-resident module variables, MPI binding (`mpi_f08`, `mpi`, `mpif.h`) and number of MPI calls | the static analysis of the mode's sources |

**Only the repository, never the machine.** Every fact comes from the fobos and from the files git tracks (or
would track: ignored files are left out), never from what is installed: no compiler versions, no fetched
dependencies (the `[dependencies]` directory is not analysed), no build directories, no date. So `--check` gives
the same answer on a laptop and in CI, and a stale block always means a real change: a mode, a case, a module.

Files included by another file (`include 'kernels.inc'` inside a module) belong to their includer: their
procedures are not reported as lacking `implicit none`.

## In CI

```yaml
- run: fobis agents-md --check
```

Exit 0 when every file's block is current; 1 when one is stale (the unified diff is printed), has no block or
does not exist; 2 for broken markers or a fobos error. `--check --json` gives the per-file status and diff.

## Real output

StringiFor (153 files), abridged:

```markdown
| Mode | Compiler | Builds | Flags | Parallel | Defines |
|---|---|---|---|---|---|
| `tests-gnu` | gnu | every program in the sources | -O2 | - | - |
| `tests-gnu-debug` | gnu | every program in the sources | -O0, debug info, runtime checks | - | - |
| `stringifor-static-gnu` | gnu | static library `libstringifor.a` from `stringifor.F90` | -O2 | - | - |
...

- Sources (mode `tests-gnu`): `src`; 153 files (2 `.F90`, 151 `.f90`), 2 modules.
- Programs: 151 programs (`src/tests/stringifor_string_t/` 145, `src/tests/stringifor/` 6).
- `real` declarations by kind: `R8P` 9 (15 digits, from `penf`), `R4P` 8 (6 digits, from `penf`), `R16P` 5 (33 digits, from `penf`), `default` 2.
- Units without `implicit none`: 147 units (`src/tests/stringifor_string_t/` 145, `src/tests/stringifor/` 2).
```

The 147 units are the generated doctest programs, which have no `implicit none` (checked against `grep`: 6 of the
153 files carry it); the kinds come from PENF, a fetched dependency, through `use penf, only: ...`.

**A large code.** On a private 251-file MPI + OpenACC application (2.2 s): 94 modes (gnu, nvfortran and amd
compilers; OpenACC, OpenMP and MPI flagged per mode from its flags), 102 files with OpenMP directives, 76 with
OpenACC, 144 module variables declared on the device, 223 MPI calls through `use mpi`, `real(R8P)` in 9742
declarations. The first version reported 33 procedures without `implicit none`: they sat in `.INC` files included
inside modules that have it. Fixed; the 4 left are real: two procedures of an `.INC` file that nothing includes,
an alias module with no declarations, a compiler-bug reproducer program.

## Limits

- The block describes; it does not judge. Conventions it cannot measure (naming, error handling, the physics)
  belong in your hand-written part.
- A project with many modes gets one table row per mode (94 rows above): long, but complete.
- A kind's origin is found when it is a named constant of a project module, or when a single module exports it
  through only-lists; a kind reaching the code through a plain `use` is listed without origin.
- The analysed sources are those of one mode (`--mode`, default the first): a mode with other sources or defines
  gives other code facts.

The MCP server exposes the facts and the block as the `agents_md` tool (read-only). See
[JSON output](/advanced/json-output#fobis-agents-md-json).
