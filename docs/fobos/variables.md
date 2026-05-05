# Variables

fobos variables let you define reusable values with a `$` prefix and substitute them anywhere in the file, eliminating repetition of paths and flag strings.

## Defining variables

Variables are defined in any section by prefixing the option name with `$`:

```ini
[vars]
$SRC    = ./src/
$BUILD  = ./build/
$OBJ    = ./obj/
$MOD    = ./mod/
$CFLAGS = -c -O2 -Wall
```

::: tip Section name
The section containing variables can have any name — `[vars]`, `[common-variables]`, or any other name. The section name is irrelevant; FoBiS.py collects all `$`-prefixed options from every section.
:::

## Using variables

Substitute a variable by referencing its name on the right-hand side of any option:

```ini
[modes]
modes = debug release

[vars]
$SRC    = ./src/
$BUILD  = ./build/
$TARGET = ./src/main.f90

[debug]
compiler  = gnu
cflags    = -c -O0 -g
src       = $SRC
build_dir = $BUILD
target    = $TARGET

[release]
compiler  = gnu
cflags    = -c -O3
src       = $SRC
build_dir = $BUILD
target    = $TARGET
```

## Full example

```ini
[modes]
modes = shared-lib1 static-lib1 shared-lib2 static-lib2

[common-variables]
$CFLAGS_SHARED = -c -fPIC -O2
$CFLAGS_STATIC = -c -O2
$LFLAGS_SHARED = -shared
$BUILD         = ./build/
$OBJ           = ./obj/
$MOD           = ./mod/

[shared-lib1]
compiler  = gnu
cflags    = $CFLAGS_SHARED
lflags    = $LFLAGS_SHARED
build_dir = $BUILD
obj_dir   = $OBJ
mod_dir   = $MOD
target    = lib1.f90
mklib     = shared

[static-lib1]
compiler  = gnu
cflags    = $CFLAGS_STATIC
build_dir = $BUILD
obj_dir   = $OBJ
mod_dir   = $MOD
target    = lib1.f90
mklib     = static

[shared-lib2]
compiler  = gnu
cflags    = $CFLAGS_SHARED
lflags    = $LFLAGS_SHARED
build_dir = $BUILD
obj_dir   = $OBJ
mod_dir   = $MOD
target    = lib2.f90
mklib     = shared

[static-lib2]
compiler  = gnu
cflags    = $CFLAGS_STATIC
build_dir = $BUILD
obj_dir   = $OBJ
mod_dir   = $MOD
target    = lib2.f90
mklib     = static
```

## Rules and limitations

- Variable names are **global** — they are collected from all sections before
  substitution. The one exception is `[varset:NAME]` sections, whose
  `$`-prefixed keys apply only when the named varset is selected; see
  [Varsets](/advanced/varsets).
- **Recursion is not allowed** — a variable value may not reference another variable.
- **Multiple variables** can appear in a single option value.
- Variables are substituted via simple string replacement; there is no expression evaluation.
- **Overlapping prefixes are safe** — substitution respects identifier
  boundaries, so `$HDF5` and `$HDF5_PREFIX` can coexist in the same fobos
  without one corrupting the other.

## Choosing a binding at invocation time

When several modes differ only in the *value* a variable should take (cluster
paths, GPU architectures, install prefixes), reach for **varsets** instead of
duplicating mode blocks. A varset is a named bundle of `$variable` bindings
selected via `--varset NAME` on the CLI; the mode block stays cluster-agnostic
and binds variables it needs by name. See [Varsets](/advanced/varsets) for the
full reference.

## Splitting variables across files

Variables defined in an [included](/advanced/includes) fobos file are merged
into the implicit global pool exactly as if they had been declared in the main
file. This enables patterns like a committed `defaults.fobos` for project
defaults plus an optional, gitignored `?fobos.local` for per-developer
overrides, layered via a `[include]` directive.
