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

- Variable names are **global** — they are collected from all sections before substitution.
- **Recursion is not allowed** — a variable value may not reference another variable.
- **Multiple variables** can appear in a single option value.
- Variables are substituted via simple string replacement; there is no expression evaluation.
