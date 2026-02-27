# Templates

Templates let you define a shared set of options once and inherit them into multiple modes, reducing repetition in many-mode fobos files.

## The problem without templates

```ini
[modes]
modes = shared-lib1 static-lib1 shared-lib2 static-lib2

[shared-lib1]
compiler  = gnu
cflags    = -c -fPIC -O2
lflags    = -shared
build_dir = ./build/
target    = lib1.f90

[static-lib1]
compiler  = gnu
cflags    = -c -O2
build_dir = ./build/
target    = lib1.f90

[shared-lib2]
compiler  = gnu
cflags    = -c -fPIC -O2
lflags    = -shared
build_dir = ./build/
target    = lib2.f90

[static-lib2]
compiler  = gnu
cflags    = -c -O2
build_dir = ./build/
target    = lib2.f90
```

## With templates

Define template sections (any section name works as a template):

```ini
[modes]
modes = shared-lib1 static-lib1 shared-lib2 static-lib2

# --- templates ---
[template-shared]
compiler  = gnu
cflags    = -c -fPIC -O2
lflags    = -shared
build_dir = ./build/

[template-static]
compiler  = gnu
cflags    = -c -O2
build_dir = ./build/

# --- main modes ---
[shared-lib1]
template = template-shared
target   = lib1.f90

[static-lib1]
template = template-static
target   = lib1.f90

[shared-lib2]
template = template-shared
target   = lib2.f90

[static-lib2]
template = template-static
target   = lib2.f90
```

## Multiple templates

A mode can inherit from more than one template by listing names separated by spaces:

```ini
[template-gnu]
compiler = gnu
cflags   = -c -O2

[template-mpi]
mpi = True

[release-mpi]
template  = template-gnu template-mpi
build_dir = ./build/release-mpi/
target    = src/main.f90
```

Templates are applied **left-to-right**: the mode itself wins over all templates, and earlier templates take precedence over later ones. In the example above the precedence order is:

```
release-mpi > template-gnu > template-mpi
```

## Template-of-template (chaining)

A template section can itself reference one or more templates. Inheritance is resolved **depth-first**, so a template's own parents are expanded immediately after it:

```ini
[template-base]
compiler  = gnu
build_dir = ./build/

[template-debug]
template = template-base
cflags   = -c -O0 -g -Wall

[mymode]
template = template-debug
target   = src/main.f90
```

Resolution order for `mymode`: `template-debug` → `template-base`.

## How templates work

- A mode that contains a `template = <name> [<name> …]` option inherits all options from the listed template sections.
- Options explicitly defined in the mode take **precedence** over template options — they are never overwritten.
- Multiple templates are applied left-to-right; earlier templates take precedence over later ones.
- Template-of-template inheritance is expanded depth-first.
- Circular template references (A → B → A) are detected at startup and cause an error.
- Template sections that are not referenced as a `template` value are ignored during the build — they are never used as modes themselves.

## Combining templates with variables

Templates and [variables](/fobos/variables) compose well:

```ini
[modes]
modes = shared-lib1 static-lib1

[vars]
$BUILD = ./build/
$OBJ   = ./obj/
$MOD   = ./mod/

[template-shared]
compiler  = gnu
cflags    = -c -fPIC -O3
lflags    = -shared
build_dir = $BUILD
obj_dir   = $OBJ
mod_dir   = $MOD

[template-static]
compiler  = gnu
cflags    = -c -O3
build_dir = $BUILD
obj_dir   = $OBJ
mod_dir   = $MOD

[shared-lib1]
template = template-shared
target   = lib1.f90
mklib    = shared

[static-lib1]
template = template-static
target   = lib1.f90
mklib    = static
```
