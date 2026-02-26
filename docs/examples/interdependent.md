# Interdependent Projects

This example shows how to manage a multi-repository Fortran project where a main program depends on two separately-built libraries, using the `-dependon` feature.

## Project layout

```
project/
├── fobos
├── src/
│   └── main.f90
└── libs/
    ├── lib_io/
    │   ├── fobos
    │   └── src/
    │       └── io_module.f90
    └── lib_math/
        ├── fobos
        └── src/
            └── math_module.f90
```

### `main.f90`

```fortran
program main
  use io_module
  use math_module
  implicit none
  real :: result
  result = compute(3.14)
  call print_result(result)
end program main
```

### `libs/lib_math/fobos`

```ini
[modes]
modes = gnu

[gnu]
compiler  = gnu
cflags    = -c -O2
src       = ./src/
build_dir = ./build/
obj_dir   = ./build/obj/
mod_dir   = ./build/mod/
target    = math_module.f90
mklib     = static
output    = libmath.a
```

### `libs/lib_io/fobos`

```ini
[modes]
modes = gnu

[gnu]
compiler  = gnu
cflags    = -c -O2
src       = ./src/
build_dir = ./build/
obj_dir   = ./build/obj/
mod_dir   = ./build/mod/
target    = io_module.f90
mklib     = static
output    = libio.a
```

### `project/fobos`

```ini
[modes]
modes = gnu

[gnu]
compiler  = gnu
cflags    = -c -O2
src       = ./src/
build_dir = ./build/
obj_dir   = ./build/obj/
mod_dir   = ./build/mod/
target    = main.f90
output    = myapp
dependon  = ./libs/lib_math/fobos:gnu ./libs/lib_io/fobos:gnu
```

## Building

```bash
# From project/
FoBiS.py build -mode gnu
```

FoBiS.py:
1. Enters `libs/lib_math/`, runs `FoBiS.py build -f fobos -mode gnu` — builds `libmath.a` if needed.
2. Enters `libs/lib_io/`, runs `FoBiS.py build -f fobos -mode gnu` — builds `libio.a` if needed.
3. Returns to `project/`, compiles `main.f90` with both libraries linked, and produces `build/myapp`.

If neither library has changed since the last build, step 1 and 2 are no-ops.

## Cleaning

```bash
FoBiS.py clean -mode gnu
```

Cleans only the main project artefacts. To also clean the libraries, run `FoBiS.py clean` in each library directory, or add a fobos rule:

```ini
[rule-clean-all]
help    = Clean main project and all dependencies
rule_1  = FoBiS.py clean -mode gnu -f ./libs/lib_math/fobos
rule_2  = FoBiS.py clean -mode gnu -f ./libs/lib_io/fobos
rule_3  = FoBiS.py clean -mode gnu
```

## Direct vs indirect linking

The default is **direct** linking (full library path):

```ini
dependon = ./libs/lib_math/fobos:gnu((direct))
```

For **indirect** linking (by library name via `-L` / `-l`):

```ini
dependon = ./libs/lib_math/fobos:gnu((indirect))
```

Both mechanisms automatically add the dependency's `mod_dir` to the include path so module files are found during compilation.

## Using `fetch` for GitHub-hosted dependencies

If the libraries live in separate GitHub repositories, use the `fetch` command instead:

```ini
[dependencies]
lib_math = https://github.com/user/lib_math :: tag=v1.0 :: mode=gnu
lib_io   = https://github.com/user/lib_io   :: branch=main :: mode=gnu
```

```bash
FoBiS.py fetch
FoBiS.py build -mode gnu
```

See [Fetch Dependencies](/advanced/fetch) for details.
