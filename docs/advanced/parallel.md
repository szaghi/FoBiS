# Parallel Compiling

FoBiS.py can compile independent source files concurrently, giving a significant speedup on multi-core machines.

## The `-j` flag

```bash
FoBiS.py build -j 4
```

The `-j N` (or `--jobs N`) flag enables a pool of `N` concurrent compile jobs. Files that have no dependency on each other are compiled simultaneously; files that depend on others are compiled after their dependencies are ready.

The pool size should roughly match the number of physical CPU cores available:

```bash
# 8-core machine
FoBiS.py build -j 8

# Use all available cores (Linux/macOS)
FoBiS.py build -j $(nproc)
```

## fobos option

```ini
[release]
compiler = gnu
cflags   = -c -O3
jobs     = 8
```

## How it works

FoBiS.py resolves the full dependency graph before starting compilation. Only sources that are ready (all their `USE`d modules already compiled) are submitted to the pool. This ensures correct ordering while maximising concurrency for independent files.

::: info Note
The pool is not dynamically balanced based on file count — it simply submits all ready files at once. For very uneven dependency trees the speedup is proportional to the width of the graph.
:::

## Example

```bash
# Debug build, single job (default)
FoBiS.py build -compiler gnu -cflags "-c -O0 -g"

# Release build, parallel
FoBiS.py build -compiler gnu -cflags "-c -O3" -j 8
```

With a fobos file:

```ini
[modes]
modes = debug release

[debug]
compiler = gnu
cflags   = -c -O0 -g
jobs     = 1

[release]
compiler = gnu
cflags   = -c -O3
jobs     = 8
```

```bash
FoBiS.py build -mode debug
FoBiS.py build -mode release
```
