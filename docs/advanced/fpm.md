# fpm interoperability

The [Fortran Package Manager](https://fpm.fortran-lang.org) and FoBiS describe the same things differently: fpm
by convention (a library directory, `app/`, `test/`, profiles), FoBiS by declaration (modes, templates, flags).
`fobis fpm` translates between the two, keeps what the other side can express, and lists the rest as notes.

```bash
fobis fpm import            # fpm.toml -> fobos
fobis fpm export            # fobos (+ the facts of the sources) -> fpm.toml
fobis fpm import --print    # show the translation, write nothing
```

Neither command overwrites an existing file without `--force`.

## Import: fpm.toml to fobos

The import translates the whole build configuration for one compiler, `--compiler` (default `gnu`), on the operating
system it runs on: the fobos holds fpm's own flags, so the project compiles as `fpm build` compiles it.

| fpm.toml | fobos |
|----------|-------|
| `name`, `version`, `author`, `description`, `homepage` | `[project]` name, version, authors, summary, repository |
| `[library] source-dir` (default `src`), `[[executable]]`/`app/`, `[[test]]`/`test/`, `[[example]]`/`example/` | `src` of every mode |
| `[library] include-dir` | `include` |
| each profile of `[profiles]`, plus `debug` and `release` | a mode `<compiler>-<profile>` with `features = ...` |
| each feature of `[features]` | a `[feature:NAME]` section, its flags resolved for the compiler and the OS |
| fpm's built-in `debug`/`release` flags, when the manifest defines no such feature | `[feature:debug]`, `[feature:release]` |
| the `[fortran]` table (defaults included), cpp in use, Intel's `-fPIC` | the template's `cflags` |
| `[library] type`: `monolithic`/`static`, `shared` (one or several) | modes `lib-static`, `lib-shared` (`-fPIC`) with the module named after the package as `target` |
| test directory | `[test] test_dir` |
| git dependencies (`tag`/`branch`/`rev`) | `[dependencies]` (`fobis fetch`) |
| path dependencies, and theirs | `name = path=DIR/<its source-dir>` ([local directories](/advanced/fetch#local-directories-path)) |
| `[dev-dependencies]` | the same, with `:: dev` ([test-only dependencies](/advanced/fetch#test-only-dependencies-dev)) |
| metapackages `mpi = "*"`, `openmp = "*"` | `mpi = True`, `openmp = True`; inside a feature `@mpi`, `@openmp` |
| `[build] link` | `ext_libs` |
| `[preprocess.cpp] macros` (`NAME={version}` expanded as fpm does) | `preproc = -D...`, and `c_preproc` for the C files |
| C files among the sources | built by FoBiS ([mixed-language projects](/advanced/mixed-language)); `c-flags` -> `c_cflags` |
| `link-time-flags` of a profile's features | the mode's `lflags` |

### Features and profiles

fpm's model: a **feature** is a named set of flags, macros and metapackages, with variants per compiler
(`name.gfortran.flags`), per OS (`name.linux.flags`) or both; a **profile** is a list of features. fpm merges a
feature's part for all platforms first, then each variant that matches, in the manifest's order; the import does the
same and writes the result:

```toml
[features]
checks.flags = "-g"
checks.gfortran.flags = "-fcheck=all"
checks.ifx.flags = "-check all"
checks.linux.preprocess.cpp.macros = "ON_LINUX"
[profiles]
careful = ["checks"]
```

```ini
[gnu-careful]
template = template-common
features = checks
build_dir = ./build/careful/

[feature:checks]
flags = -g -fcheck=all -DON_LINUX
```

- `debug` and `release` always exist, as in fpm: their features are the manifest's `debug`/`release` features when
  it defines them, fpm's built-in flags otherwise (`-Wall -Wextra -Wimplicit-interface ... -g -fcheck=bounds ...` for
  gfortran; the table of fpm `5fa4649`, February 2026).
- The `default` profile's features come first in `debug` and `release` only, as in fpm.
- `--features NAME` works on every imported feature, as on any FoBiS feature ([feature flags](/advanced/features)).
- A feature named like a FoBiS one (`openmp`, `omp`, `mpi`, `coarray`, `coverage`, `profile`, `default`) is renamed
  `fpm-NAME`: otherwise it would replace FoBiS's own.
- Every Fortran compile gets the flags of fpm's `[fortran]` table for that compiler, defaults included: for gfortran
  `-fimplicit-none -Werror=implicit-interface -ffree-form`, plus `-cpp` when the manifest uses cpp anywhere; ifort and
  ifx get `-fPIC` too.

**Checked against fpm.** fpm 0.13.0 built from its sources (`5fa4649`) compiled fpm's own example packages
(`features_per_compiler`, `features_demo`, `features_default_profile`, `implicit-typing`, `implicit-external`,
`fixed-form`, `preprocess_cpp`, `metapackage_openmp`, `app_with_c`, `hello_complex`) and the test fixture
`tests/fpm/packages/mixed` in every profile; the imported fobos compiled each file with the same flags (as sets: fpm
repeats some of them), with gfortran and gcc, with ifx 2025.3 and with nvfortran 26.5. The fixture's genuine commands
are in `tests/fpm/mixed-fpm-0.13.0.txt`, and the test suite compares against them.

**Differences that remain.**

- A dependency compiled with the project (a path dependency, or a git one with `use=sources`) gets the project's
  macros: FoBiS has one flag set per build, fpm one per package.
- One compiler per import: the notes name the features with flags for other compilers and the `--compiler` value to
  import them (`--compiler intel_nextgen` for ifx).

### Notes

Notes list what is not translated: registry versions and other metapackages, `external-modules`, an unknown
`source-form`, the parts of a feature that are not flags (executables, dependencies other than `mpi`/`openmp`,
`build`, `install`...), a profile naming a feature that does not exist, `[profiles]` in fpm's older table syntax, and
a feature's flags for another OS.

## Export: fobos to fpm.toml

The manifest is written from the fobos and from the analysis of the mode's sources (the fetched dependencies
directory left out):

- `[library] source-dir`: the common directory of the files holding modules; a note when it also holds programs
  (fpm compiles every file of `source-dir` into the library);
- `[[test]]`: the programs under the fobos `[test]` directory (or, without one, under a `test`/`tests` directory);
  `[[executable]]`: the other programs; each named after its program, or after its file when several programs share
  a name; `auto-*` discovery is turned off;
- `[dependencies]`: the fobos dependencies as git dependencies with their pin; `mpi = "*"`/`openmp = "*"` when the
  mode uses MPI/OpenMP;
- `[preprocess.cpp] macros`: the mode's `-D` macros;
- the version from `[project] version` (a file is read, also outside a git repository), without a leading `v`.

Modes, templates, flags and rules are not exported: fpm uses its profiles.

## Real runs

**Import.** FLAP's `fpm.toml` (70 `[[test]]` entries, two git dependencies) imported into a copy of its tracked
files: `fobis fetch` cloned FACE and PENF, `fobis build --mode lib-static` built `libflap.a` from `src/lib/flap.f90`
(the module named after the package), and `fobis test --mode gnu-debug` ran the 70 tests with fpm's debug flags
for gfortran and its `[fortran]` defaults (`-fimplicit-none -Werror=implicit-interface -ffree-form`): 70 passed.

**Export.** StringiFor's fobos exported in a copy of its tracked files: library `src/lib`, three git dependencies,
151 tests from `src/tests` (all its doctest programs are called `volatile_doctest`, so they are named after their
files), version `1.8.0` from its `VERSION` file. fpm 0.12.0 built it (`Project compiled successfully`). Its
`fpm test` stops on `stringifor_test_differential.f90:357` (`-Werror=implicit-interface` of fpm's profiles, with
gfortran 15.2 and 16 alike, on a contained function referenced in an `allocate` type-spec) — a property of that
test under fpm's flags, not of the manifest.

**The TOML reader** (used when Python lacks `tomllib`) gives the same result as `tomllib` on the 14 `fpm.toml`
files of the maintainer's repositories, fpm's own included.
