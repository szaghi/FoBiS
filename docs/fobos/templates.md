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

## How templates work

- A mode that contains a `template = <name>` option inherits all options from the named template section.
- Options explicitly defined in the mode take **precedence** over template options — they are not overwritten.
- Templates can themselves reference another template (one level of nesting).
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
