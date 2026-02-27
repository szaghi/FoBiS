# External Libraries

FoBiS.py supports two approaches for linking external libraries: direct linking by full path, and indirect linking by name with a library search path.

## Direct linking (full path)

Use `-libs` to specify the full path to one or more library files:

```bash
FoBiS.py build -libs /path/to/foo.a /path/to/bar.so
```

Multiple libraries can be listed separated by spaces.

## Indirect linking (library name + search path)

Use `-ext_libs` together with `-dlib`/`--lib_dir` to link by library base-name:

```bash
FoBiS.py build -ext_libs foo sao -dlib /path/to/my_libraries/
```

This is equivalent to passing `-L/path/to/my_libraries/ -lfoo -lsao` to the linker. The library files in `lib_dir` must follow the `lib<name>.[a|so]` naming convention.

## Libraries that contain Fortran modules

When an external library exposes Fortran modules (`.mod` files), the compiler needs to find those files during the compile phase. Add the directory containing the `.mod` files with `-i`/`--include`:

```bash
FoBiS.py build -libs /path/to/libmylib.a -i /path/to/mylib/mod/
```

## fobos options

All library options are available in a fobos file:

```ini
[default]
compiler = gnu
cflags   = -c -O2
libs     = /path/to/foo.a /path/to/bar.a
ext_libs = baz qux
lib_dir  = /path/to/libs/
include  = /path/to/libs/mod/
```

## Custom archiver and ranlib

By default FoBiS.py uses the system `ar -rcs` to create static libraries and `ranlib` to index them. Alternative toolchains — LLVM (`llvm-ar`, `llvm-ranlib`), Intel, AMD AOCC, cross-compilation environments — can be selected with three options:

| Option | Default | Description |
|---|---|---|
| `-ar AR` | `ar` | Archiver executable |
| `-arflags ARFLAGS` | `-rcs` | Archiver flags |
| `-ranlib RANLIB` | `ranlib` | Ranlib executable; set to empty string to skip |

### LLVM toolchain example

```bash
fobis build -t src/mylib.f90 -mklib static -ar llvm-ar -ranlib llvm-ranlib
```

`llvm-ar` updates the symbol table internally, so the ranlib step can be skipped entirely:

```bash
fobis build -t src/mylib.f90 -mklib static -ar llvm-ar -ranlib ""
```

### fobos example

```ini
[llvm-static]
compiler = custom
fc       = flang-new
ar       = llvm-ar
ranlib   = llvm-ranlib
mklib    = static
target   = src/mylib.f90
output   = libmylib.a
build_dir = ./build/
obj_dir   = ./obj/
mod_dir   = ./mod/
```

## Volatile libraries

Libraries that may change between builds (e.g. CI-generated artifacts) can be declared as *volatile*. FoBiS.py saves an MD5 hash on first use and forces a full recompile whenever the library file changes.

See [Volatile Libraries](/advanced/volatile-libs) for details.

## Summary of library options

| Option | Description |
|---|---|
| `-libs PATH…` | External libraries — full paths |
| `-vlibs PATH…` | Volatile external libraries — full paths |
| `-ext_libs NAME…` | External libraries — by name (linker path) |
| `-ext_vlibs NAME…` | Volatile external libraries — by name |
| `-dlib DIR…`, `--lib_dir DIR…` | Library search directories |
| `-i DIR…`, `--include DIR…` | Include directories (for `.mod` and `.h` files) |
