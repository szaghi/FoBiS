# Building a Library

FoBiS.py can build both static and shared Fortran libraries using the `-mklib` option.

::: warning Target required
Library building always requires specifying a `-target` file. Only the target and its dependencies are compiled and archived.
:::

## Source layout

```
src/
├── mylib.f90      ← library entry point (no `program` statement)
└── utils/
    └── helpers.f90
```

`mylib.f90` might look like:

```fortran
module mylib
  use helpers
  implicit none
  public :: compute
contains
  function compute(x) result(y)
    real, intent(in) :: x
    real :: y
    y = helpers_process(x)
  end function
end module mylib
```

## Static library

```bash
FoBiS.py build -t src/mylib.f90 -mklib static -o libmylib.a
```

Result: `libmylib.a` in the build directory, plus `*.mod` files in `mod/`.

## Shared library

```bash
FoBiS.py build -t src/mylib.f90 -mklib shared -o libmylib.so \
  -cflags " -c -fPIC" -lflags " -shared"
```

Result: `libmylib.so` in the build directory.

## Using the library in another project

Once built, the library can be linked into another project. With `-libs` (full path):

```bash
FoBiS.py build -libs /path/to/libmylib.a -i /path/to/mod/
```

Or with `-ext_libs` (by name):

```bash
FoBiS.py build -ext_libs mylib -dlib /path/to/ -i /path/to/mod/
```

## fobos examples

### Static and shared variants

```ini
[modes]
modes = static shared

[static]
compiler  = gnu
cflags    = -c -O2
build_dir = ./build/
obj_dir   = ./build/obj/
mod_dir   = ./build/mod/
src       = ./src/
target    = mylib.f90
mklib     = static
output    = libmylib.a

[shared]
compiler  = gnu
cflags    = -c -fPIC -O2
lflags    = -shared
build_dir = ./build/
obj_dir   = ./build/obj/
mod_dir   = ./build/mod/
src       = ./src/
target    = mylib.f90
mklib     = shared
output    = libmylib.so
```

```bash
FoBiS.py build -mode static
FoBiS.py build -mode shared
```

### Consumer project fobos

```ini
[default]
compiler  = gnu
cflags    = -c -O2
src       = ./src/
build_dir = ./build/
libs      = /path/to/libmylib.a
include   = /path/to/mod/
target    = main.f90
output    = myapp
```

## Volatile library (rebuild on change)

If the library is rebuilt externally (e.g. by CI), use `-vlibs` so that your project recompiles when the library changes:

```bash
FoBiS.py build -vlibs /shared/build/libmylib.a -i /shared/build/mod/
```

See [Volatile Libraries](/advanced/volatile-libs) for details.

## Interdependent build

For a more automated approach — where `FoBiS.py build` on the consumer project also rebuilds the library if its sources have changed — use `-dependon`:

```ini
[default]
compiler = gnu
cflags   = -c -O2
src      = ./src/
target   = main.f90
dependon = ./libs/mylib/fobos:static
```

See [Interdependent Projects](/advanced/interdependent) for details.
