---
name: fobis
description: >
  Expert knowledge of FoBiS.py (Fortran Building System for poor men) — an automatic Fortran build tool that resolves module dependency hierarchies without manual makefiles. Use this skill whenever the user asks about: writing or editing a fobos file; running any fobis subcommand (build, clean, fetch, install, rule, doctests, scaffold, check, test, coverage, tree, introspect, run, cache, commit); Fortran project build configuration; diagnosing FoBiS build errors; adding GitHub dependencies to a Fortran project; the --json output flag; multi-mode builds; templates; variables and varsets; library builds (static/shared); MPI/OpenMP/coarray/OpenMP-offload builds; feature flags and conditional compilation; build profiles; the build cache; external-library auto-detection and pkg-config (.pc) generation; multi-target builds; convention-based source auto-discovery; the lock file and semver dependency constraints; the first-class test runner and coverage reports; LLM-assisted commit messages; the cflags-heritage feature; parallel compilation; or any question that mentions "fobos", "FoBiS", or building Fortran projects. When in doubt, trigger this skill — it is better to consult it unnecessarily than to miss it.
---

# FoBiS.py Expert Knowledge

FoBiS.py is a CLI tool that auto-builds modern Fortran projects by parsing source files and resolving inter-module dependency hierarchies. It eliminates manual makefile dependency tracking.

> **Currency:** This reflects FoBiS.py 3.8.x (15-subcommand Typer CLI). The canonical CLI binary is `fobis`; `FoBiS.py` remains a legacy alias. Flags use **double-dash long form** (`--mode`, `--ex`, `--ls`, `--lmodes`). Legacy single-dash multi-char forms (`-mode`, `-ex`) are auto-normalized but should not be written in new scripts/docs.

## Core Concept

FoBiS.py scans your source directories, parses every `.f90` (and related) file for `module`, `use`, and `include` statements, builds a dependency graph, and compiles in the correct order. The only file you need is `fobos` — the project configuration file (INI format, auto-loaded from the current directory).

---

## CLI Commands

15 subcommands, grouped by purpose. Every command except `commit` and the `cache`/`scaffold`
sub-apps accepts `--fobos`/`-f <path>` (non-default fobos file) and `--mode <name>` (select a build mode).

### Build & run

```bash
fobis build              # compile and link (the default workhorse)
fobis run [TARGET] [-- ARGS...]   # build if needed, then execute (passthrough args after --)
fobis test [-- ARGS...]  # discover, build, run Fortran test programs (passthrough)
fobis coverage           # generate coverage reports from instrumented runs
fobis check              # validate the dependency graph without building
```

- `build`: every compiler/dir/file/preproc option plus profiles, features, varsets, cache,
  multi-target, hooks, externals — see the fobos option table below. Supports `--json`.
- `run`: positional `TARGET` optional (defaults to the mode's output). `--no-build`, `--dry-run`,
  `--example NAME`. Args after `--` are forwarded to the executed binary.
- `test`: `--suite NAME`, `--filter GLOB`, `--timeout SEC` (default 60), `--no-build`, `--list`,
  `--coverage`. Args after `--` forwarded to test binaries.
- `coverage`: `--format html|xml|text|all` (repeatable, default html), `--output-dir`,
  `--source-dir`, `--exclude GLOB`, `--fail-under N`, `--tool gcovr|lcov`.
- `check`: `--strict` (warnings → errors, exit 1), `--varset`, `--src`.

### Project

```bash
fobis fetch              # clone + build GitHub deps from the [dependencies] section
fobis install [REPO]     # install built local files, or clone+build+install a GitHub repo
fobis introspect         # emit machine-readable project metadata (JSON/TOML)
fobis tree               # print the resolved inter-project dependency tree
fobis cache <list|clean|show>   # manage the build-artifact cache
```

- `fetch`: `--deps-dir`, `--update`, `--no-build`, `--frozen` (enforce lockfile), `--no-cache`.
  Supports `--json`.
- `install`: positional `REPO` (`user/repo` or full URL) optional. Local mode (no REPO) installs
  previously built artifacts to `--prefix/-p` (default `./`) under `--bin`/`--lib`/`--include`.
  GitHub mode: `--branch`, `--tag`, `--rev`, `--update`, `--no-build`, `--deps-dir` (default `~/.fobis/`).
- `introspect`: `--sources`, `--compiler`, `--dependencies`, `--targets`, `--include-dirs`,
  `--buildoptions`, `--projectinfo`, `--varsets`, `--all`, `--write` (to `.fobis-info/`),
  `--format json|toml`, `--varset`.
- `tree`: `--depth/-d N`, `--no-dedupe`.
- `cache list` (`--cache-dir`); `cache clean --older-than N` (`--cache-dir`); `cache show DEP_NAME`
  (positional required, `--cache-dir`).

### Utilities

```bash
fobis clean              # remove compiled objects/mods (use carefully)
fobis rule --ex <name>   # run a custom shell rule from fobos (and intrinsic rules)
fobis doctests           # build & run inline Fortran doctests
fobis scaffold <status|sync|init|list>   # manage project boilerplate from bundled templates
fobis commit             # generate a Conventional-Commits message via a local LLM
```

- `clean`: `--only-obj` and `--only-target` (mutually exclusive). Supports `--json`.
- `rule`: `--ex/--execute NAME`, `--ls/--list`, plus intrinsic rules: `--get KEY`,
  `--get-output-name`, `--ford project.md`, `--gcov-analyzer DIR [SUMMARY]`,
  `--is-ascii-kind-supported`, `--is-ucs4-kind-supported`, `--is-float128-kind-supported`.
- `doctests`: `--keep-volatile-doctests`, `--exclude-from-doctests`, `--doctests-preprocessor cpp|fpp`.
- `scaffold`: subcommands `status` (`--strict` for CI), `sync` (`--dry-run`, `--yes/-y`),
  `init` (`--yes/-y`), `list`. All take `--fobos/-f`; `status`/`sync` take `--files GLOB`.
- `commit`: `--backend/-b ollama|openai`, `--url/-u`, `--model/-m`, `--max-diff`, `--refine-passes`,
  `--apply` (runs `git commit`), `--config/-c`, `--show-config`, `--init-config`. **No `--fobos`/`--mode`.**

### Cross-cutting facts

- **`--json`** exists on exactly three commands: `build`, `clean`, `fetch`. (`introspect`/`coverage`
  use `--format` instead.)
- **Passthrough** (forward extra args after `--`): `run`, `test` only.
- **Global:** `--version`/`-v`.

---

## fobos File Format

INI-format, auto-loaded from the current directory.

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

Select a mode: `fobis build --mode release`. List modes: `fobis build --lmodes`. The first listed
mode is used when `--mode` is omitted.

### Templates (DRY across modes)

```ini
[modes]
modes = debug release

[template-common]
compiler  = gnu
src       = ./src/
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
- Templates can chain; circular references are an error.

### Variables (`$`) and varsets

Any `$NAME = value` in any section (except `[varset:*]`) joins a **global** pool and is substituted
into the active mode's values. No recursion. A `[vars]` section is just a conventional home — it is
not special-cased; the `$`-prefix rule is what matters.

```ini
[vars]
$SRC    = ./src/
$HDF5   = /opt/hdf5

[debug]
src    = $SRC
cflags = -c -I$HDF5/include
```

**Varsets** are *named, selectable* bundles. Unlike plain `$vars`, a `[varset:NAME]` block is applied
only when chosen — via `--varset name1,name2` (last write wins) or a `[varsets] default = ...`
fallback. Introspect with `fobis introspect --varsets`.

```ini
[varset:local]
$HDF5 = /usr/local/hdf5
[varset:cluster]
$HDF5 = /apps/hdf5/1.14
```
`fobis build --varset cluster`

### Rules (custom tasks)

```ini
[rule-makedoc]
help  = Build documentation
quiet = True
rule  = ford doc/ford.md

[rule-maketar]
help    = Create archive
rule_rm = rm -f project.tar
rule_mk = tar cf project.tar src/ fobos
```

Run: `fobis rule --ex makedoc`. List: `fobis rule --ls`. Use unique keys starting with `rule`
(e.g. `rule`, `rule_rm`, `rule1`) for multiple commands in one rule.

---

## Key fobos Options Reference

These are *mode* keys (valid in `[default]` or any `[mode-X]`). A mode recognizes any key whose name
matches a `build`-command option (underscored form).

| Option | Description |
|---|---|
| `compiler` | `gnu`, `intel`, `intel_nextgen`, `g95`, `opencoarrays-gnu`, `pgi`, `ibm`, `nag`, `nvfortran`, `amd`, `lfortran`, `custom` |
| `fc` | Fortran compiler executable (for `compiler = custom`) |
| `modsw` | Module-path compiler switch (for `compiler = custom`, e.g. `-J`, `-module`) |
| `cflags` / `lflags` | Compile / link flags (fobos + CLI are concatenated) |
| `preproc` | Preprocessor macro flags (e.g. `-DDEBUG`) |
| `src` | Source root directory/directories (space-separated) |
| `build_dir` / `obj_dir` / `mod_dir` | Output / object / `.mod` directories |
| `lib_dir` / `include` | Library / include search directories |
| `target` / `output` | Build target source file / output name |
| `exclude` / `exclude_dirs` | Files / directories to exclude from the build |
| `libs` / `vlibs` | Local library files (full paths) / volatile (md5-tracked, rebuild on change) |
| `ext_libs` / `ext_vlibs` | External libs by name (`-l`) / volatile by name |
| `dependon` | Interdependent fobos projects (`path/fobos[:mode]`) |
| `mklib` | Build a library: `static` or `shared` |
| `ar` / `arflags` / `ranlib` | Archiver / flags (`-rcs`) / ranlib (empty string = skip) |
| `mpi` / `openmp` / `openmp_offload` / `coarray` | Enable MPI wrapper / OpenMP / OpenMP offload / coarrays |
| `coverage` / `profile` | Coverage instrumentation / profiling instrumentation |
| `jobs` | Parallel compile jobs |
| `cflags_heritage` | Persist cflags; force full rebuild when they change |
| `track_build` | Record built artifacts for `install` |
| `build_profile` | Named flag preset: `debug`, `release`, `asan`, `coverage` |
| `features` / `no_default_features` | Activate feature flags / suppress `[features] default` |
| `varset` | Apply named `[varset:NAME]` bindings |
| `externals` | Space-separated external library names to auto-resolve (from `[externals]`) |
| `pkgconfig`, `pkgconfig_name`, `pkgconfig_desc`, `pkgconfig_url`, `pkgconfig_req`, `pkgconfig_req_priv` | Generate a `.pc` file |
| `target_filter` / `examples` | Multi-target build controls |
| `pre_build` / `post_build` | Rule names to run before / after the build |
| `no_auto_discover` | Disable convention-based source-dir discovery |
| `no_cache` / `cache_dir` | Disable the build cache / override its directory |

---

## Feature Areas

### Build profiles

Built-in compiler-flag presets, selected with `build_profile = NAME` (fobos) or `--build-profile NAME`
(CLI). Profiles: `debug`, `release`, `asan`, `coverage`. Tuned per compiler (gnu, intel, intel_nextgen,
nvfortran, nag, amd, lfortran); unknown compiler falls back to the gnu preset with a warning. Profile
flags are prepended so your explicit `cflags` win. `fobis build --list-profiles` prints the full table.

### Feature flags (conditional compilation)

```ini
[features]
default = prod                 ; reserved key: the default feature set
hdf5    = -DUSE_HDF5            ; leaf feature → flags
prod    = -DNDEBUG @hdf5        ; @hdf5 composes another feature (recursive, cycle-safe)

[feature:gpu]                  ; Tier-2 block with constraints
flags     = -DUSE_GPU
requires  = openmp_offload     ; auto-pulls prerequisites
conflicts = debug              ; hard error if both active

[feature-group:precision]      ; mutual exclusivity
members = single double
default = double               ; with default → exactly-one; without → at-most-one
```

Resolution order: `[features] default` (unless `--no-default-features`) → mode `features = ...` →
CLI `--features 'prod,-coverage'` (a `-name` token deactivates). Well-known *implicit* features need
no `[features]` section and just flip the matching bool: `openmp`/`omp`, `mpi`, `coarray`, `coverage`,
`profile`, `openmp_offload`/`omp_offload`. Active set is reported in `introspect`.

### External libraries & pkg-config

Declare in `[externals]` (`name = auto | /prefix`); activate per mode with `externals = name1 name2`.
`auto` probes via pkg-config / wrapper scripts for `mpi`, `hdf5`, `netcdf`, `blas`, `openblas`,
`lapack`, `fftw`/`fftw3`; a prefix probes `<prefix>/include` and `<prefix>/lib`. Resolved flags are
appended to `cflags`/`lflags`. **There is no `--pkg-config`/`--with-mpi-auto` CLI flag** — it is
fobos-only.

```ini
[externals]
mpi  = auto
hdf5 = /opt/hdf5-1.14

[default]
cflags    = -c
externals = mpi hdf5
```

To *publish* a `.pc` file for your own library, set `pkgconfig = true` (+ optional `pkgconfig_name`,
`pkgconfig_desc`, `pkgconfig_url`, `pkgconfig_req`, `pkgconfig_req_priv`; defaults from `[project]`).

### Multi-target builds

```ini
[target.solver]
source = src/solver.f90
output = solver

[example.demo]
source = examples/demo.f90
output = demo
```

`[target.NAME]` and `[example.NAME]` define independently-built artifacts. A mode-level `target` and
`[target.*]` are mutually exclusive. CLI: `--target-filter solver,foo` restricts which targets build;
`--examples` also builds `[example.*]`. (`fobos` help writes the section as `[[target.*]]`; configparser
strips the outer brackets, so both forms produce `target.NAME`.)

### Auto-discovery

When `src` is unset (fobos and CLI) and `--no-auto-discover` is off, FoBiS scans `src/`, `source/`,
`app/` for Fortran sources and uses the directories it finds as scan roots.

### Build cache

`BuildCache` content-addresses built `use=fobos` dependency artifacts; key = SHA-256 of
`source_commit | compiler | cflags_hash | fobis_version`. Default dir `$FOBIS_CACHE_DIR` or
`~/.fobis/cache`. Manage with `fobis cache list|clean --older-than N|show DEP`. Disable per build with
`--no-cache`; relocate with `--cache-dir`.

### Includes (`[include]`)

```ini
[include]
paths = base.fobos ?optional.fobos
```

Pulls sibling fobos files (relative to the including file; `${ENV}`/`~` expanded). A leading `?` marks
an include optional (missing → skipped); otherwise a missing file aborts. Merge is **parent-wins**,
except list-typed keys (`[modes] modes`, `[features] default`, `[varsets] default`) which are
token-merged. Cycle-detected, depth-capped.

---

## Fetch Dependencies & Lock File

The `fetch` command pulls GitHub-hosted Fortran libraries declared in `[dependencies]`.

```ini
[dependencies]
deps_dir = .fobis_deps     ; optional clone dir (default .fobis_deps)

penf     = https://github.com/szaghi/PENF :: tag=v1.5.0
stdlib   = fortran-lang/stdlib :: semver=^0.5 :: use=fobos :: mode=gnu   ; user/repo shorthand
jsonfort = https://github.com/jacobwilliams/json-fortran :: branch=main :: use=fobos
```

Spec: `name = URL [:: branch=X | tag=X | rev=X | semver=EXPR] [:: mode=X] [:: use=sources|fobos]`.
`semver` is **mutually exclusive** with branch/tag/rev and resolves the highest matching git tag
(Cargo-style `^`, `~`, `=`, `>=`/`<=`/`>`/`<`, `*`, comma-AND).

| `use=` | fetch behaviour | build behaviour |
|---|---|---|
| `sources` (default) | clone only | dep dir added to source scan inline |
| `fobos` | clone + `fobis build` in dep | dep fobos added to `dependon`; dep dir excluded from scan |

Workflow:

```bash
fobis fetch              # initial clone; pre-build use=fobos deps
fobis fetch --update     # re-pull and re-build
fobis fetch --no-build   # clone only
fobis fetch --frozen     # enforce exact fobos.lock state; abort on drift or missing lock
fobis build              # auto-reads .fobis_deps/.deps_config.ini — no extra flags
```

---

## Test Runner & Coverage

`fobis test` discovers, builds, and runs Fortran test programs; `fobis coverage` turns instrumented
runs into HTML/XML/text reports. Both read optional fobos sections:

```ini
[test]
test_dir = tests          ; directory scanned for test programs (default test)
suite    = unit           ; only run tests tagged ! fobis: suite=unit
timeout  = 120            ; seconds before a test is killed (default 60)
compiler = gnu            ; override compiler for test builds
cflags   = -c -O0 -g

[coverage]
format     = html         ; html xml text (list; default html)
output_dir = coverage     ; report directory (default coverage)
fail_under = 75           ; exit 1 if line coverage < N%
exclude    = tests/*      ; glob(s) to exclude
```

`fobis test --coverage` runs the suite then generates the report. `fobis test --list` shows discovered
tests; `--suite`, `--filter`, `--timeout`, `--no-build` refine the run.

---

## LLM Commit Messages

`fobis commit` drafts a Conventional-Commits message from your **staged** diff via a local LLM.
Backends: `ollama` (default, `http://localhost:11434`) and `openai` (any OpenAI-compatible endpoint).
Config: `~/.config/fobis/config.ini` (`$XDG_CONFIG_HOME` honoured), `[llm]` section keys `backend`,
`url`, `model` (default `qwen3-coder:30b-a3b-q4_K_M`), `max_diff_chars` (12000), `refine_passes` (0).

```bash
fobis commit --init-config            # write a commented config template
fobis commit --show-config            # print effective config
fobis commit --refine-passes 2        # critique-and-rewrite iterations
fobis commit --apply                  # run `git commit` with the generated message
```

---

## JSON Output (scripting / CI)

Add `--json` to **`build`, `clean`, or `fetch`** for structured stdout. Exit codes are unchanged
(0 ok / 1 fail); JSON is always printed, even on failure.

```bash
fobis build --mode release --json
```

```json
{ "status": "ok", "target": "all", "objects_compiled": 3, "errors": [] }
```

```bash
result=$(fobis build --mode release --json)
[ "$(echo "$result" | jq -r '.status')" != "ok" ] && { echo "$result" | jq -r '.errors[]'; exit 1; }
```

For richer machine-readable project metadata (sources, compiler, targets, varsets), use
`fobis introspect --all --format json` instead.

---

## Library Builds

### Static library

```ini
[default]
compiler  = gnu
cflags    = -c -O3
src       = ./src/
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
mklib     = shared
output    = libmylib.so
```

Static-library tooling is configurable: `ar`, `arflags` (default `-rcs`), `ranlib` (set to empty to
skip — e.g. with `llvm-ar`, which updates the symbol table itself).

---

## Interdependent Projects (`dependon`)

```ini
[default]
# project B's fobos
dependon = ../projectA/fobos
src      = ./src/
```

FoBiS rebuilds project A if needed, then adds its `mod_dir` and built library to B's build. Spec form:
`path/fobos[:mode]`.

---

## Diagnosing Common Errors

### "Module 'xyz' not found"

1. **Missing source path** — the file defining `module xyz` is not in any `src` directory. Add it to `src`.
2. **Wrong `mod_dir`** — `.mod` written one place, compiler looking elsewhere. Keep `mod_dir` consistent.
3. **Dependency not fetched** — run `fobis fetch` if the module comes from a GitHub dep.
4. **Name-case / filename mismatch** — most compilers lowercase the `.mod` filename; verify on disk.
5. **Unresolvable graph** — run `fobis tree` to see the resolved dependency tree, or `fobis check`
   (`--strict`) to validate the graph without building.
6. **Wrong `dependon` path** — must point at the dep's *fobos file*, not its directory.

### Build produces no output / does nothing
- Sources may be up-to-date — `fobis build --force-compile` forces a full rebuild.
- Confirm `target` points to a file with a `program` statement, and `src` actually has `.f90` files.
- Check auto-discovery: with no `src`, FoBiS only scans `src/`, `source/`, `app/` (disable via
  `--no-auto-discover`).

### Flags not taking effect after change
Set `cflags_heritage = True` to auto-detect cflag changes and trigger a full rebuild; otherwise only
changed sources recompile.

### "The mode X is not defined into the fobos file"
`--mode` must exactly match a name in `[modes] modes = ...`. Run `fobis build --lmodes`.

### Library build not linking
- Static: `mklib = static` (output ends `.a`). Shared: `mklib = shared` + `-fPIC` in `cflags`.
- System libraries: prefer the `[externals]` section (auto-resolves flags) over hand-written `-L`/`-l`.

---

## Parsed File Extensions

- Modern Fortran: `.f90 .F90 .f95 .F95 .f03 .F03 .f08 .F08 .f2k .F2K`
- Legacy: `.f .F .for .FOR .fpp .FPP .fortran .f77 .F77`
- Include: `.inc .INC .h .H`

Add custom include extensions: `fobis build --inc .cmn`.

---

## Special Sections Summary

| Section | Purpose |
|---|---|
| `[default]` | Single-mode build configuration |
| `[modes]` | `modes = a b c` — lists named modes (first = default) |
| `[mode-name]` | One section per named mode |
| `[template-*]` (any name) | Template for mode inheritance (`template = ...`) |
| `[vars]` (any name) | Conventional home for `$NAME = value` globals |
| `[varset:NAME]` / `[varsets]` | Named `$variable` bundles / `default = ...` selection |
| `[features]` / `[feature:NAME]` / `[feature-group:NAME]` | Feature flags, per-feature constraints, mutual-exclusion groups |
| `[include]` | `paths = ...` — pull in sibling fobos files |
| `[externals]` | External library map (`name = auto \| /prefix`) |
| `[target.NAME]` / `[example.NAME]` | Multi-target / example build sections |
| `[test]` / `[coverage]` | `fobis test` / `fobis coverage` defaults |
| `[rule-NAME]` | Custom shell rule for `fobis rule --ex NAME` |
| `[dependencies]` | GitHub-hosted build dependencies (used by `fetch`) |
| `[project]` | Metadata: `name`, `authors`, `version`, `summary`, `repository`, `website`, `email`, `year` |

---

## Further Reading

Full documentation at **https://szaghi.github.io/FoBiS/**:

- [fobos reference](https://szaghi.github.io/FoBiS/fobos/) · [Complete example](https://szaghi.github.io/FoBiS/fobos/complete-example)
- [Command reference](https://szaghi.github.io/FoBiS/reference/build) (all 15 subcommands)
- [Feature flags](https://szaghi.github.io/FoBiS/advanced/features) · [Build profiles](https://szaghi.github.io/FoBiS/advanced/build-profiles) · [Varsets](https://szaghi.github.io/FoBiS/advanced/varsets)
- [External libraries](https://szaghi.github.io/FoBiS/advanced/externals) · [Build cache](https://szaghi.github.io/FoBiS/advanced/cache) · [Auto-discovery](https://szaghi.github.io/FoBiS/advanced/auto-discovery)
- [Fetch dependencies](https://szaghi.github.io/FoBiS/advanced/fetch) · [Lock file & semver](https://szaghi.github.io/FoBiS/advanced/lock-file) · [Interdependent builds](https://szaghi.github.io/FoBiS/advanced/interdependent)
- [Test runner](https://szaghi.github.io/FoBiS/advanced/testing) · [Coverage](https://szaghi.github.io/FoBiS/reference/coverage) · [JSON output](https://szaghi.github.io/FoBiS/advanced/json-output)
- [Source code](https://github.com/szaghi/FoBiS)
