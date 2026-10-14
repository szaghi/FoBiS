# How a build works

What `fobis build` does, in order, and what decides whether a file is compiled again. The
[first tutorial track](/tutorial/first-steps/01-first-build) shows it on a real project; this page is the model
behind it.

## 1. Settings: the command line, then the mode

FoBiS starts from the command line's options and, when a fobos file is present, reads one of its modes: the one
named by `--mode`, else the first listed in `[modes]`, else the `[default]` section. The mode's templates are
applied first (its own keys win), then its `$variables` are substituted.

A key the mode sets **replaces** the command line's value, with these exceptions:

- `cflags`, `lflags` and `preproc` given on the command line are **appended** to the mode's;
- an explicit `--target` keeps its target and output, and an explicit `--build-dir` its build directory;
- a key FoBiS does not know is ignored without a word: the [fobos reference](/fobos/#every-mode-key) lists every
  key a mode can hold.

`--build-profile` flags are put before the mode's own, so the mode's flags win on a conflict.

## 2. Sources: scanned, not declared

FoBiS walks the source directories (`src`; without it the first of `src/`, `source/`, `app/` holding Fortran
sources, else the current directory), minus `exclude_dirs` and `exclude`, plus the fetched dependencies used as
sources, and reads every Fortran file. It does not parse Fortran: it reads
the statements that matter to a build:

- `module` and `submodule` definitions;
- `use` statements, except intrinsic modules (`iso_fortran_env`, `omp_lib`, `mpi`, a compiler's own modules, and
  the names a mode lists in `intrinsic_modules`);
- `include` lines;
- `program` statements.

The files are read in the same order on every machine, so the compile order does not depend on how the file
system lists a directory.

## 3. The dependency graph

A `use` of a module defined in the project makes the file depend on the file defining it, an `include` on the
included file. The files are sorted so that every module is compiled before the files that use it; the files of
one level do not depend on each other and are compiled in parallel with `-j`.

A `use` of a module that no project file defines is left to the compiler: it must find the `.mod` file in an
include directory (`include`, a `dependon` project, a library). When it does not, `fobis build --explain` says
whether the module is excluded, hidden by a preprocessor branch, misspelt or never defined
([explaining failures](/ai/explain)).

## 4. What is compiled again

A file is compiled when its object is missing, or older than its source, or when anything it depends on changed:

| Change | Recompiled |
|---|---|
| A source file | the file, and every file that uses its modules, directly or not |
| An included file | the files including it |
| A `.mod` of a module from outside the project (a `dependon` project, a library), newer than the object | the files using that module |
| The compiler behind the mode's command (another path, or another `--version`: a module swap) | everything, once |
| The flags | **nothing**, unless the mode sets `cflags_heritage = True` ([flag heritage](/advanced/cflags-heritage)) |
| `--force-compile` | everything |

The cascade follows timestamps: a change to a low-level module recompiles every file above it, even when its
interface did not change.

## 5. Linking

Each program is linked with the objects of the files it reaches through `use`, directly or not, plus the
project's files that define no module (external procedures). A module no program uses is compiled but not
linked. With `mklib = static|shared` and a `target`, the mode builds a library of the target file and the files
it reaches instead.

## 6. Where the outputs go

Objects go to `obj_dir`, module files to `mod_dir`, both inside `build_dir`; the program or library to
`build_dir` (`output` renames it). Shadow builds (`--shadow`) and the build variants of `fobis assess` keep their
objects apart, under `.fobis/`, so they never mix with your build's.

## Further reading

- [Templates and variables](/tutorial/growing/01-templates), [profiles and features](/tutorial/growing/02-profiles)
- [Dependencies](/tutorial/first-steps/05-dependencies) and [a project using another](/tutorial/growing/04-dependon)
- [The build command](/reference/build), [every mode key](/fobos/#every-mode-key)
- [Architecture](/advanced/architecture), for contributors: the modules behind each step
