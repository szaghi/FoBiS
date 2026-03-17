# Quick Start

## Your first build

Given a project tree:

```
└── src
    ├── main.f90
    └── nested-1
        ├── first_dep.f90
        └── nested-2
            └── second_dep.inc
```

where `main.f90` contains a Fortran `program` that `use`s `nested_1`, and `first_dep.f90` defines `module nested_1` which `include`s `second_dep.inc`.

Just run:

```bash
fobis build
```

![Zero-config build demo](/gifs/01_basic_build.gif)

::: tip Legacy command name
The `FoBiS.py` command is preserved as a backward-compatible alias. Both `fobis` and `FoBiS.py` invoke the same tool — existing scripts using `FoBiS.py` continue to work without changes.
:::

FoBiS.py will:
1. Recursively scan `./` for all Fortran source files
2. Parse each file, extracting `use`, `include`, and `module` statements
3. Resolve the full dependency hierarchy automatically
4. Compile in the correct order (include → module → program)
5. Place compiled objects in `./obj/`, module interfaces in `./mod/`, and the executable in `./`

After the build your tree looks like:

```
├── main           ← the executable
├── mod/
│   └── nested_1.mod
├── obj/
│   ├── first_dep.o
│   └── main.o
└── src/
    ├── main.f90
    └── nested-1/
        ├── first_dep.f90
        └── nested-2/
            └── second_dep.inc
```

## Customising output directories

Override any directory with CLI flags:

```bash
fobis build --obj-dir my-objs --mod-dir my-mods --build-dir my-build
```

The `obj` and `mod` directories are always relative to the build directory, so the tree becomes:

```
└── my-build/
    ├── my-mods/
    ├── my-objs/
    └── main
```

## Cleaning the project

```bash
fobis clean
```

This removes all compiled objects (`*.o`) and module files (`*.mod`) from the `obj/` and `mod/` directories. If you used custom paths during the build, repeat them:

```bash
fobis clean --obj-dir my-objs --mod-dir my-mods --build-dir my-build
```

Clean only compiled objects (keep executable):

```bash
fobis clean --only-obj
```

Clean only the executable (keep objects for faster incremental rebuild):

```bash
fobis clean --only-target
```

![Clean and incremental rebuild demo](/gifs/05_clean.gif)

## Parsed file extensions

By default FoBiS.py parses files with these extensions:

| Category       | Extensions |
|----------------|-----------|
| Modern Fortran | `.f90` `.F90` `.f95` `.F95` `.f03` `.F03` `.f08` `.F08` `.f2k` `.F2K` |
| Legacy Fortran | `.f` `.F` `.for` `.FOR` `.fpp` `.FPP` `.fortran` `.f77` `.F77` |
| Include files  | `.inc` `.INC` `.h` `.H` |

Add custom include extensions (tab-completable):

```bash
fobis build --inc .cmn .icp
```

## Selecting a specific target

Build only one program instead of all programs found:

```bash
fobis build -t src/main.f90
```

With a custom output name:

```bash
fobis build -t src/main.f90 -o myapp
```

## Using a fobos configuration file

For anything beyond a one-off build, create a `fobos` file in the project root. FoBiS.py loads it automatically:

```ini
[default]
compiler  = gnu
cflags    = -c -O2
src       = ./src/
build_dir = ./build/
obj_dir   = ./obj/
mod_dir   = ./mod/
target    = src/main.f90
output    = myapp
```

Then simply:

```bash
fobis build
fobis clean
```

![fobos build modes demo](/gifs/02_fobos_build.gif)

See the [fobos section](/fobos/) for the full reference.

::: tip Quoted string arguments
Flag values that start with `-` should be prefixed with a leading space to prevent the parser from misinterpreting them as option names:

```bash
# problematic:
fobis build --cflags "-c -fPIC"

# correct:
fobis build --cflags " -c -fPIC"
```
:::
