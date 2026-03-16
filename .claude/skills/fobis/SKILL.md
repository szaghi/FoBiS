---
name: fobis
description: >
  Expert knowledge of FoBiS.py (Fortran Building System for poor men) — an automatic Fortran build tool that resolves module dependency hierarchies without manual makefiles. Use this skill whenever the user asks about: writing or editing a fobos file, running fobis build/clean/fetch/install/rule commands, Fortran project build configuration, diagnosing FoBiS build errors, adding GitHub dependencies to a Fortran project, the --json output flag, multi-mode builds, templates, variables, library builds (static/shared), MPI/OpenMP/coarray builds, the fetch command, the install command, the cflags-heritage feature, parallel compilation, or any question that mentions "fobos", "FoBiS", or building Fortran projects. When in doubt, trigger this skill — it is better to consult it unnecessarily than to miss it.
---

# FoBiS.py Expert Knowledge

FoBiS.py is a CLI tool that auto-builds modern Fortran projects by parsing source files and resolving inter-module dependency hierarchies. It eliminates manual makefile dependency tracking.

## Core Concept

FoBiS.py scans your source directories, parses every `.f90` (and related) file for `module`, `use`, and `include` statements, builds a dependency graph, and compiles in the correct order. The only file you need is `fobos` — the project configuration file.

## CLI Commands

```bash
fobis build              # compile and link
fobis clean              # remove compiled objects/mods
fobis fetch              # clone GitHub dependencies
fobis install            # install built artifacts (or from GitHub)
fobis rule -ex <name>    # run a custom shell rule from fobos
fobis doctests           # run inline Fortran doctests
```

Each command accepts `--fobos <path>` / `-f` to use a non-default fobos file, and `--mode <name>` to select a build mode.

---

## fobos File Format

The `fobos` file is INI-format. FoBiS.py loads it automatically from the current directory.

### Single-mode (simplest)

```ini
[default]
compiler  = gnu
cflags    = -c -O2
src       = ./src/
build_dir = ./build/
obj_dir   = ./obj/
mod_dir   = ./mod/
target    = src/main.f90
output    = myapp
```

The section **must** be named `[default]`.

### Multi-mode

```ini
[modes]
modes = debug release

[debug]
compiler  = gnu
cflags    = -c -O0 -g -Wall
build_dir = ./build/debug/
src       = ./src/
target    = src/main.f90
output    = myapp

[release]
compiler  = gnu
cflags    = -c -O3 -march=native
build_dir = ./build/release/
src       = ./src/
target    = src/main.f90
output    = myapp
```

Select a mode: `fobis build -mode release`
List modes: `fobis build -lmodes`
The first listed mode is used when `-mode` is omitted.

### Templates (DRY across modes)

```ini
[modes]
modes = debug release

[template-common]
compiler  = gnu
src       = ./src/
obj_dir   = ./obj/
mod_dir   = ./mod/
target    = src/main.f90
output    = myapp

[debug]
template  = template-common
cflags    = -c -O0 -g -Wall
build_dir = ./build/debug/

[release]
template  = template-common
cflags    = -c -O3
build_dir = ./build/release/
```

- Mode options override template options.
- Multiple templates: `template = template-gnu template-mpi` (left wins).
- Templates can chain (template of templates).

### Variables (`$`)

```ini
[vars]
$SRC    = ./src/
$BUILD  = ./build/
$TARGET = ./src/main.f90

[debug]
src       = $SRC
build_dir = $BUILD
target    = $TARGET
```

Variables are global, collected from all sections. No recursion allowed.

### Rules (custom tasks)

```ini
[rule-makedoc]
help     = Build documentation
quiet    = True
rule     = ford doc/ford.md

[rule-maketar]
help     = Create archive
rule_rm  = rm -f project.tar
rule_mk  = tar cf project.tar src/ fobos
```

Run: `fobis rule -ex makedoc`
List: `fobis rule -ls`
Use unique names starting with `rule` (e.g. `rule`, `rule_rm`, `rule1`) for multiple commands in one rule.

---

## Key fobos Options Reference

| Option | Description |
|---|---|
| `compiler` | Compiler: `gnu`, `intel`, `intel_nextgen`, `g95`, `opencoarrays-gnu`, `pgi`, `ibm`, `nag`, `nvfortran`, `amd`, `custom` |
| `fc` | Fortran compiler executable (for `compiler = custom`) |
| `cflags` | Compilation flags (always include `-c`) |
| `lflags` | Linker flags |
| `preproc` | Preprocessor macro flags (e.g. `-DDEBUG`) |
| `src` | Source root directory (space-separated list) |
| `build_dir` | Output directory for compiled binaries |
| `obj_dir` | Object files directory |
| `mod_dir` | Module interface `.mod` files directory |
| `lib_dir` | External library search directories |
| `include` | Include-file search directories |
| `target` | Build target file (default: all programs found) |
| `output` | Output executable/library name |
| `exclude` | Files to exclude from build |
| `exclude_dirs` | Directories to exclude from source scan |
| `libs` | External libraries (full paths) |
| `ext_libs` | External libraries by name (linker path) |
| `vlibs` | Volatile external libraries (full paths) |
| `dependon` | Interdependent external fobos files |
| `mklib` | Build a library: `static` or `shared` |
| `mpi` | Enable MPI compiler wrapper |
| `openmp` | Enable OpenMP flags |
| `coarray` | Enable coarray flags |
| `coverage` | Enable coverage instrumentation |
| `jobs` | Parallel compile jobs |
| `cflags_heritage` | Track flag changes; force full rebuild when flags change |

---

## Fetch Dependencies

The `fetch` command pulls in GitHub-hosted Fortran libraries.

### fobos `[dependencies]` section

```ini
[dependencies]
deps_dir = .fobis_deps           # optional: where to clone (default: .fobis_deps)

penf     = https://github.com/szaghi/PENF :: tag=v1.5.0
stdlib   = szaghi/stdlib :: branch=main   # shorthand: user/repo expands to GitHub HTTPS URL
jsonfort = https://github.com/jacobwilliams/json-fortran :: branch=main :: use=fobos :: mode=gnu
```

Spec syntax: `name = URL [:: branch=X | tag=X | rev=X] [:: mode=X] [:: use=sources|fobos]`

### Integration modes

| `use=` | fetch behaviour | build behaviour |
|---|---|---|
| `sources` (default) | clone only | dep dir added to source scan inline |
| `fobos` | clone + `fobis build` in dep | dep fobos added to `dependon`; dep dir excluded from scan |

Use `sources` for small/header-like deps. Use `fobos` for deps that need their own separate build (requires a `fobos` file in the dep repo).

### Typical workflow

```bash
fobis fetch              # initial clone; pre-build use=fobos deps
fobis build              # auto-reads .fobis_deps/.deps_config.ini

fobis fetch --update     # re-pull and re-build all deps
fobis fetch --no-build   # clone only (skip build even for use=fobos)
```

The auto-generated `.fobis_deps/.deps_config.ini` is read by `build` automatically — no extra flags needed.

---

## JSON Output (scripting / CI)

Add `--json` to `build`, `clean`, or `fetch` for structured stdout:

```bash
fobis build --json
fobis build --mode release --json
```

### build JSON schema

```json
{
  "status": "ok",
  "target": "all",
  "objects_compiled": 3,
  "errors": []
}
```

`status` is `"ok"` or `"error"`. `errors` contains compiler error lines even on failure.

### clean JSON schema

```json
{
  "status": "ok",
  "removed": ["build/obj/main.o", "build/mod/mymod.mod"],
  "errors": []
}
```

### fetch JSON schema

```json
{
  "status": "ok",
  "deps_dir": ".fobis_deps",
  "dependencies": [
    {"name": "penf", "path": ".fobis_deps/penf", "use": "sources"}
  ],
  "errors": []
}
```

Exit codes are unchanged: 0 on success, 1 on failure. JSON is always printed, even on failure.

### CI script pattern (bash)

```bash
result=$(fobis build --mode release --json)
status=$(echo "$result" | jq -r '.status')
if [ "$status" != "ok" ]; then
  echo "Build failed:"
  echo "$result" | jq -r '.errors[]'
  exit 1
fi
echo "Compiled $(echo "$result" | jq '.objects_compiled') object(s)"
```

### CI script pattern (Python)

```python
import json, subprocess
result = subprocess.run(["fobis", "build", "--json"], capture_output=True, text=True)
data = json.loads(result.stdout)
if data["status"] != "ok":
    raise RuntimeError("Build failed:\n" + "\n".join(data["errors"]))
print(f"Compiled {data['objects_compiled']} object(s)")
```

---

## Diagnosing Common Errors

### "Module 'xyz' not found"

This is the most common error. Causes and fixes:

1. **Missing source path** — the file defining `module xyz` is not in any `src` directory.
   Fix: add the correct directory to `src` in your fobos file.

2. **Wrong `mod_dir`** — the `.mod` file was written to one directory but the compiler is looking elsewhere.
   Fix: make sure `mod_dir` is consistent across all modes and matches any `-I` include path.

3. **Dependency not fetched** — if the module is from an external library, run `fobis fetch` first.

4. **Name case mismatch** — Fortran module names are case-insensitive in source but the `.mod` filename on disk depends on the compiler. Most compilers lowercase the `.mod` filename. Verify the filename on disk matches.

5. **Circular or unresolvable dependency** — run `fobis build --verbose` to see the dependency resolution order and spot the missing link.

6. **Wrong `dependon` path** — for `use=fobos` deps, the `dependon` entry must point to the dep's fobos file, not just its directory.

### Build produces no output / does nothing

- All sources may be up-to-date. Use `fobis build --force-compile` to force a full rebuild.
- Check that `target` points to a file that actually contains a `program` statement.
- Verify `src` actually contains `.f90` files.

### Flags not taking effect after change

Enable `cflags_heritage = True` in your fobos to auto-detect flag changes and trigger a full rebuild. Without it, FoBiS.py only recompiles files whose source has changed.

### "The mode X is not defined into the fobos file"

The `-mode` value must exactly match a name in `[modes] modes = ...`. Run `fobis build -lmodes` to see available modes.

### Library build not linking

- For static libraries: `mklib = static` (output name should end in `.a`)
- For shared libraries: `mklib = shared` + add `-fPIC` to `cflags`
- External libraries: use `libs` (full path) or `ext_libs` (name only, requires correct `lib_dir`)

---

## Parsed File Extensions

FoBiS.py auto-parses:
- Modern Fortran: `.f90 .F90 .f95 .F95 .f03 .F03 .f08 .F08 .f2k .F2K`
- Legacy: `.f .F .for .FOR .fpp .FPP .fortran .f77 .F77`
- Include: `.inc .INC .h .H`

Add custom include extensions: `fobis build --inc .cmn`

---

## Library Builds

### Static library

```ini
[default]
compiler  = gnu
cflags    = -c -O3
src       = ./src/
build_dir = ./build/
obj_dir   = ./obj/
mod_dir   = ./mod/
mklib     = static
output    = libmylib.a
```

### Shared library

```ini
[default]
compiler  = gnu
cflags    = -c -fPIC -O3
src       = ./src/
build_dir = ./build/
obj_dir   = ./obj/
mod_dir   = ./mod/
mklib     = shared
output    = libmylib.so
```

---

## Interdependent Projects (`dependon`)

When project B depends on a pre-built library from project A:

```ini
[default]
# in project B's fobos
dependon  = ../projectA/fobos
src       = ./src/
```

FoBiS.py will rebuild project A if needed, then add its `mod_dir` and built library to B's build.

---

## Advanced Options

- `--verbose` / `--quiet` — control output verbosity
- `--graph` — generate a dependency graph via graphviz (`.dot` file)
- `--makefile <file>` — generate a GNU Makefile for the project
- `--cflags-heritage` / `--ch` — track flags, force rebuild on change
- `--track-build` / `--tb` — record built artifacts for `install`
- `--force-compile` — recompile everything regardless of timestamps
- `--build-all` — build all sources, not just those reachable from a target
- `--disable-recursive-search` / `--drs` — don't recurse into subdirectories
- `--jobs N` / `-j N` — parallel compilation (default: 1)
- `--print-fobos-template` — print a comprehensive fobos template to stdout

---

## Special Sections Summary

| Section | Purpose |
|---|---|
| `[default]` | Single-mode build configuration |
| `[modes]` | Lists all available named modes |
| `[vars]` or any name | Variable definitions (`$NAME = value`) |
| `[template-*]` or any name | Template for mode inheritance |
| `[rule-NAME]` | Custom shell rule for `fobis rule -ex NAME` |
| `[dependencies]` | GitHub-hosted build dependencies (used by `fetch`) |
| `[project]` | Project metadata: name, authors, version |

---

## Further Reading

Full documentation at **https://szaghi.github.io/FoBiS/**:

- [fobos reference](https://szaghi.github.io/FoBiS/fobos/)
- [Fetch dependencies](https://szaghi.github.io/FoBiS/advanced/fetch)
- [JSON output](https://szaghi.github.io/FoBiS/advanced/json-output)
- [External libraries](https://szaghi.github.io/FoBiS/advanced/libraries)
- [Interdependent builds](https://szaghi.github.io/FoBiS/advanced/interdependent)
- [Parallel compiling](https://szaghi.github.io/FoBiS/advanced/parallel)
- [Architecture](https://szaghi.github.io/FoBiS/advanced/architecture)
- [Source code](https://github.com/szaghi/FoBiS)
