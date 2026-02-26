# Basic Build

This example walks through building the *cumbersome* project — a program with nested module and include dependencies — using progressively more features of FoBiS.py.

## Source tree

```
src/
├── cumbersome.f90
└── nested-1/
    ├── first_dep.f90
    └── nested-2/
        └── second_dep.inc
```

`cumbersome.f90` uses module `nested_1` (from `first_dep.f90`), which includes `second_dep.inc`. The correct compilation order is:

1. Compile `first_dep.f90` (which incorporates `second_dep.inc`)
2. Compile and link `cumbersome.f90`

## Step 1: Build all programs

```bash
FoBiS.py build
```

FoBiS.py:
- Recursively scans `./` for all Fortran files
- Identifies `cumbersome.f90` as the program (it contains the `program` statement)
- Resolves the dependency graph
- Compiles in the correct order

Default output layout:

```
mod/          ← module interface files (.mod)
obj/          ← compiled object files (.o)
cumbersome    ← the built executable
src/
```

## Step 2: Custom directories

```bash
FoBiS.py build -dobj my-objs -dmod my-mods -dbld my-build
```

The `obj` and `mod` directories are always placed **relative to the build directory**:

```
my-build/
├── my-mods/
└── my-objs/
cumbersome    ← executable placed in build_dir
src/
```

## Step 3: Specify compiler and flags

```bash
FoBiS.py build -compiler gnu -cflags " -c -O2 -Wall" -j 4
```

Note the leading space before `-c` — this avoids an `argparse` quirk with quoted strings that start with `-`.

## Step 4: Build a specific target

```bash
FoBiS.py build -t src/cumbersome.f90 -o myapp
```

Builds only `cumbersome.f90` (and its dependencies), naming the executable `myapp`.

## Step 5: Clean

```bash
FoBiS.py clean
```

Removes `obj/`, `mod/`, and the built executable. If you used custom directories, pass them again:

```bash
FoBiS.py clean -dobj my-objs -dmod my-mods -dbld my-build
```

Or clean selectively:

```bash
FoBiS.py clean -only_obj      # remove objects, keep executable
FoBiS.py clean -only_target   # remove executable, keep objects
```

## Using a fobos file

Place this fobos file in the project root to avoid repeating options:

```ini
[modes]
modes = debug release

[debug]
compiler        = gnu
cflags          = -c -O0 -g
mod_dir         = ./mod/
obj_dir         = ./obj/
build_dir       = ./
src             = ./src/
target          = cumbersome.f90
output          = cumbersome
cflags_heritage = True

[release]
compiler        = gnu
cflags          = -c -O3
mod_dir         = ./mod/
obj_dir         = ./obj/
build_dir       = ./
src             = ./src/
target          = cumbersome.f90
output          = cumbersome
cflags_heritage = True
```

```bash
FoBiS.py build -mode debug
FoBiS.py build -mode release
FoBiS.py clean -mode release
```

## Excluding files

```bash
FoBiS.py build -e src/experimental.f90
```

Or in fobos:

```ini
[default]
...
exclude = ./src/experimental.f90
```

## Dependency graph

Generate a graphviz `.dot` file to visualise dependencies:

```bash
FoBiS.py build -graph
```
