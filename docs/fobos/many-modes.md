# Many-mode fobos

A many-mode fobos file bundles multiple build configurations into a single file. Each configuration is a *mode*, selected at build time with `-mode`.

## Structure

The key addition over a single-mode file is the `[modes]` section, which must list all available mode names:

```ini
[modes]
modes = debug-gnu release-gnu debug-intel

[debug-gnu]
help     = GNU gfortran debug build
compiler = gnu
cflags   = -c -O0 -g -Wall -Wextra
build_dir = ./build/debug-gnu/

[release-gnu]
help     = GNU gfortran optimised build
compiler = gnu
cflags   = -c -O3 -march=native
build_dir = ./build/release-gnu/

[debug-intel]
help     = Intel ifort debug build
compiler = intel
cflags   = -c -O0 -debug all -warn all
build_dir = ./build/debug-intel/
```

## Selecting a mode

```bash
FoBiS.py build -mode release-gnu
FoBiS.py clean -mode release-gnu
```

If `-mode` is omitted, the **first mode listed** in `[modes]` is used.

## Listing modes

```bash
FoBiS.py build -lmodes
```

Output:

```
The fobos file defines the following modes:
  - "debug-gnu"    GNU gfortran debug build
  - "release-gnu"  GNU gfortran optimised build
  - "debug-intel"  Intel ifort debug build
```

## Invalid mode error

```bash
FoBiS.py build -mode unknown-mode
```

```
Error: the mode "unknown-mode" is not defined into the fobos file. Defined modes are:
  - "debug-gnu"    GNU gfortran debug build
  - "release-gnu"  GNU gfortran optimised build
  - "debug-intel"  Intel ifort debug build
```

## Multi-line mode lists

The `modes` value can span multiple lines:

```ini
[modes]
modes = shared-lib1 static-lib1
        shared-lib2 static-lib2
```

## Full example

```ini
[modes]
modes = gnu intel custom

# variables shared across modes
[vars]
$SRC      = ./src/
$BLDDIR   = ./build/
$OBJDIR   = ./obj/
$MODDIR   = ./mod/
$TARGET   = ./src/cumbersome.f90

[gnu]
help      = Build with GNU gfortran
compiler  = gnu
cflags    = -c -O2
lflags    = -O2
src       = $SRC
build_dir = $BLDDIR
obj_dir   = $OBJDIR
mod_dir   = $MODDIR
target    = $TARGET
output    = Cumbersome

[intel]
help      = Build with Intel ifort
compiler  = intel
cflags    = -c -O2
lflags    = -O2
src       = $SRC
build_dir = $BLDDIR
obj_dir   = $OBJDIR
mod_dir   = $MODDIR
target    = $TARGET
output    = Cumbersome

[custom]
help      = Build with g95
compiler  = custom
fc        = g95
modsw     = -fmod=
cflags    = -c -O2
src       = $SRC
build_dir = $BLDDIR
obj_dir   = $OBJDIR
mod_dir   = $MODDIR
target    = $TARGET
output    = Cumbersome
```

::: tip Reducing repetition
Use [templates](/fobos/templates) to share common options across modes, and [variables](/fobos/variables) to avoid repeating path strings. Together they make large fobos files much easier to maintain.
:::
