# Single-mode fobos

A single-mode fobos file defines exactly one build configuration in a section named `[default]`.

## Structure

```ini
[default]
help      = Debug build with GNU gfortran
colors    = True
quiet     = False
jobs      = 2
compiler  = gnu
cflags    = -c -O0 -g -Wall
lflags    = -O0
preproc   = -DDEBUG
mod_dir   = ./mod/
obj_dir   = ./obj/
build_dir = ./build/
src       = ./src/
exclude   = ./src/experimental.f90
target    = ./src/main.f90
output    = myapp
log       = False
```

## Key rules

- The section **must** be named `[default]`. Any other name is ignored.
- The `[default]` section can appear anywhere in the file — it does not need to be first.
- If no `[default]` section is found and no `[modes]` section exists, FoBiS.py prints:

  ```
  Warning: fobos file has not "modes" section neither "default" one
  ```

## Example: project with external libraries

```ini
[default]
compiler  = gnu
cflags    = -c -O3
lflags    = -lhdf5 -lz
src       = ./src/
build_dir = ./build/
obj_dir   = ./obj/
mod_dir   = ./mod/
lib_dir   = /usr/local/lib /opt/hdf5/lib
include   = /usr/local/include /opt/hdf5/include
libs      = /opt/mylib/build/libmylib.a
ext_libs  = hdf5 z
target    = ./src/solver.f90
output    = solver
```

## Example: library build

```ini
[default]
compiler  = gnu
cflags    = -c -fPIC -O3
src       = ./src/
build_dir = ./build/
obj_dir   = ./obj/
mod_dir   = ./mod/
target    = ./src/mylib.f90
mklib     = shared
output    = libmylib.so
```

## Calling with a custom fobos name

```bash
FoBiS.py build -f fobos.debug
FoBiS.py clean -f fobos.debug
```

::: tip Multiple fobos files
A common pattern is to maintain several fobos files side-by-side — `fobos.debug`, `fobos.release`, `fobos.intel` — and select them with `-f`. For a single-file approach with multiple configurations, see [many-mode fobos](/fobos/many-modes).
:::
