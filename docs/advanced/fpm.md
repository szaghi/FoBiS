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

| fpm.toml | fobos |
|----------|-------|
| `name`, `version`, `author`, `description`, `homepage` | `[project]` name, version, authors, summary, repository |
| `[library] source-dir` (default `src`), `[[executable]]`/`app/`, `[[test]]`/`test/`, `[[example]]`/`example/` | `src` of every mode |
| — | modes `<compiler>-debug` and `<compiler>-release` with FoBiS's own `build_profile = debug/release` |
| a module named after the package | a library mode `lib-<compiler>` with that module as `target` (FoBiS builds a library from one target module) |
| test directory | `[test] test_dir` |
| git dependencies (`tag`/`branch`/`rev`), dev-dependencies | `[dependencies]` (`fobis fetch`) |
| path dependencies | their library sources added to `src` |
| metapackages `mpi = "*"`, `openmp = "*"` | `mpi = True`, `openmp = True` |
| `[build] link` | `ext_libs` |
| `[preprocess.cpp] macros` | `preproc = -D...` |

Notes report what is not translated: registry versions and other metapackages, `external-modules`, the `[fortran]`
settings (implicit typing, source form), fpm's `[features]`/`[profiles]` flag sets, and the fact that fpm's own
compiler flags differ from FoBiS's profiles.

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
files: `fobis fetch` cloned FACE and PENF, `fobis build --mode lib-gnu` built `libflap.a` from `src/lib/flap.f90`
(the module named after the package), and `fobis test --mode gnu-debug` ran the 70 tests: 70 passed.

**Export.** StringiFor's fobos exported in a copy of its tracked files: library `src/lib`, three git dependencies,
151 tests from `src/tests` (all its doctest programs are called `volatile_doctest`, so they are named after their
files), version `1.8.0` from its `VERSION` file. fpm 0.12.0 built it (`Project compiled successfully`). Its
`fpm test` stops on `stringifor_test_differential.f90:357` (`-Werror=implicit-interface` of fpm's profiles, with
gfortran 15.2 and 16 alike, on a contained function referenced in an `allocate` type-spec) — a property of that
test under fpm's flags, not of the manifest.

**The TOML reader** (used when Python lacks `tomllib`) gives the same result as `tomllib` on the 14 `fpm.toml`
files of the maintainer's repositories, fpm's own included.
