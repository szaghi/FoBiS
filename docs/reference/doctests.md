# `doctests` command

Find, compile, and run inline doctest snippets embedded in Fortran source comments.

```bash
FoBiS.py doctests [options]
```

The `doctests` command accepts the same compiler, directory, file, fobos, and preprocessor options as [`build`](/reference/build), plus the doctest-specific options listed below.

## Doctest-specific options

| Option | Description |
|---|---|
| `--keep-volatile-doctests` | Keep generated test programs after execution (useful for debugging) |
| `--exclude-from-doctests FILE…` | Exclude specific source files from doctest scanning (repeatable) |
| `--doctests-preprocessor {cpp,fpp}` | Preprocessor used when parsing doctest sources (default: `cpp`) — tab-completable |

## Compiler options

Same as [`build`](/reference/build#compiler-options): `--compiler`, `--fc`, `--cflags`, `--lflags`, `--modsw`, `--mpi`, `--openmp`, etc.

## Directory options

Same as [`build`](/reference/build#directory-options): `-s`, `--build-dir`, `--obj-dir`, `--mod-dir`, `--lib-dir`, `-i`, `--exclude-dirs`, `--drs`.

## fobos options

| Option | Description |
|---|---|
| `-f`, `--fobos` | Specify a fobos file |
| `--fci`, `--fobos-case-insensitive` | Case-insensitive parsing |
| `--mode` | Select a fobos mode — tab-completable from the active fobos file |
| `--lmodes` | List available modes |
| `--print-fobos-template` | Print a fobos template |

## Fancy options

| Option | Description |
|---|---|
| `--colors` | Coloured terminal output |
| `-l`, `--log` | Write a log file |
| `-q`, `--quiet` | Less verbose output |
| `--verbose` | Maximum verbosity |
| `-j`, `--jobs` | Parallel compile jobs |

## Examples

```bash
# Run all doctests found in the source tree
FoBiS.py doctests

# Run doctests using a fobos mode
FoBiS.py doctests -f project.fobos --mode gnu

# Keep volatile test programs for inspection
FoBiS.py doctests --keep-volatile-doctests

# Exclude a file from doctest scanning
FoBiS.py doctests --exclude-from-doctests src/legacy.f90

# Store doctests build output under ./build/
FoBiS.py doctests --build-dir ./build/
```

## Doctest syntax

Embed tests directly in Fortran comments using the FORD snippet syntax:

```fortran
function add(a, b) result(c)
!< Add two integers.
!<```fortran
!< print*, add(a=12, b=33)
!<```
!=> 45 <<<
integer, intent(IN) :: a, b
integer             :: c
c = a + b
end function add
```

The delimiter character (`<` above) can be any character you use for FORD documentation. The test body is enclosed between `` !$```fortran `` and `` !$``` ``, and the expected result follows with `!=> expected <<<`.

See the [Doctests](/advanced/doctests) advanced guide for the full syntax reference.
