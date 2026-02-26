# Interdependent Projects

When a program depends on one or more separately-managed library projects, FoBiS.py can automatically rebuild those libraries before building the main program.

## The `-dependon` option

```bash
FoBiS.py build -t program.f90 \
  -dependon ./libs/foo/fobos:static ./libs/bar/fobos:static \
  -o myprogram
```

Each `-dependon` entry has the form:

```
relative/path/to/fobos[:mode][((direct|indirect))]
```

| Part | Description |
|---|---|
| `relative/path/to/fobos` | **Relative** path to the fobos file of the dependency project |
| `:mode` | fobos mode to build with (optional; defaults to `default` or first defined mode) |
| `((direct))` | Link the library by its full path (default) |
| `((indirect))` | Link the library by name via `-L` / `-l` flags |

## Direct vs indirect linking

**Direct linking** (`((direct))`, the default) is equivalent to passing the full path of the built library to `-libs`. The `mod_dir` from the dependency's fobos is automatically added to the include search path.

**Indirect linking** (`((indirect))`) is equivalent to passing the library base-name to `-ext_libs` and its `build_dir` to `-lib_dir`. Again, `mod_dir` is automatically included.

## fobos syntax

```ini
[main-program]
compiler  = gnu
cflags    = -c -O2
target    = program.f90
output    = myprogram
dependon  = ./libs/foo/fobos:static((direct)) ./libs/bar/fobos:static((indirect))
```

Valid `dependon` value examples:

```ini
# Direct link, specific mode
dependon = ./path_to_lib/fobos:static((direct))

# Indirect link, specific mode
dependon = ./path_to_lib/fobos:static((indirect))

# Direct link assumed, default mode
dependon = ./path_to_lib/fobos

# The order of :mode and ((mechanism)) is interchangeable
dependon = ./path_to_lib/fobos((direct)):static
```

## How it works

For each dependency listed in `-dependon`:

1. FoBiS.py changes to the directory containing the dependency fobos file.
2. FoBiS.py runs itself against that fobos file and mode, rebuilding the dependency if necessary.
3. FoBiS.py returns to the original directory and continues building the main project, with the dependency's build artefacts automatically wired in.

This means that if the library source has changed, it is rebuilt; if it is up to date, nothing extra happens.

## Multi-project example

Suppose you have:

```
project/
├── fobos
├── src/
│   └── program.f90
├── libs/
│   ├── lib_a/
│   │   ├── fobos
│   │   └── src/
│   └── lib_b/
│       ├── fobos
│       └── src/
```

`project/fobos`:

```ini
[modes]
modes = gnu

[gnu]
compiler = gnu
cflags   = -c -O2
src      = ./src/
target   = program.f90
output   = myprogram
dependon = ./libs/lib_a/fobos:gnu ./libs/lib_b/fobos:gnu
```

Running `FoBiS.py build -mode gnu` from `project/` builds `lib_a`, then `lib_b`, then links `myprogram` against both.

## Relationship with `fetch`

The [`fetch` command](/advanced/fetch) automates the process of obtaining and building external dependencies from GitHub and then wires them in via the same `-dependon` mechanism. For dependencies you manage manually in the repo, use `-dependon` directly.
