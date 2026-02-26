# PreForM Preprocessing

FoBiS.py integrates seamlessly with [PreForM.py](https://github.com/szaghi/PreForM), a powerful yet simple preprocessor designed for Fortran. PreForM.py provides template expansion and `cpp`-compatible preprocessing, making it easy to generate repetitive Fortran code.

## Basic usage

Activate preprocessing with `-preprocessor` (or the legacy `-pfm`/`--preform` alias):

```bash
FoBiS.py build -preprocessor
```

By default, `PreForM.py` is invoked as the preprocessor. Each source file is passed through PreForM.py before compilation. The intermediate preprocessed files are deleted immediately after compilation.

To use a different preprocessor, specify its command:

```bash
FoBiS.py build -preprocessor my_preprocessor
```

## Keeping preprocessed files

To retain the preprocessed sources (useful for debugging or distribution), specify an output directory with `-dpp`/`--preprocessor_dir`:

```bash
FoBiS.py build -preprocessor -dpp ./preprocessed/
```

The directory is relative to the build path, similar to `obj/` and `mod/`.

## Preprocessing only selected files

To preprocess only files with certain extensions (rather than all sources), use `-epp`/`--preprocessor_ext`:

```bash
FoBiS.py build -preprocessor -dpp ./preprocessed/ -epp .F90 .F95 .F03
```

Only files ending in `.F90`, `.F95`, or `.F03` are passed through PreForM.py; all other files are compiled directly.

## Preprocessor arguments

Pass extra flags to the preprocessor command with `-app`/`--preprocessor_args`:

```bash
FoBiS.py build -preprocessor -app "-DDEBUG=1"
```

Compiler-level preprocessor flags (e.g. `-DFEATURE`) go to `-p`/`--preproc`:

```bash
FoBiS.py build -preprocessor -p "-DUSE_MPI"
```

To suppress the `-o` output flag in the preprocessor invocation:

```bash
FoBiS.py build -preprocessor -npp
```

## fobos options

```ini
[gnu-preform]
compiler        = gnu
cflags          = -c -O2
preprocessor    = PreForM.py
preprocessor_dir = ./pfm/
preprocessor_ext = .pfm .F90 .F03
preprocessor_args = -DDEBUG
src             = ./src/
build_dir       = ./build/
target          = main.f90
output          = myapp
```

## Preprocessor option reference

| Option | Description |
|---|---|
| `-preprocessor [CMD]` | Enable preprocessing; optional custom command (default: `PreForM.py`) |
| `-p`, `--preproc` | Preprocessor flags for the main compiler |
| `-app`, `--preprocessor_args` | Flags passed to the preprocessor |
| `-npp`, `--preprocessor_no_o` | Omit `-o` from the preprocessor command |
| `-dpp`, `--preprocessor_dir` | Directory for preprocessed sources (kept if set) |
| `-epp`, `--preprocessor_ext` | Extensions of files to preprocess |

## Example workflow

Given a source tree using `.pfm` extension for template files:

```
src/
├── main.f90
└── templates/
    ├── vector.pfm
    └── matrix.pfm
```

```bash
FoBiS.py build \
  -preprocessor \
  -dpp ./preprocessed/ \
  -epp .pfm \
  -cflags "-c -O2" \
  -src ./src/
```

FoBiS.py expands `vector.pfm` and `matrix.pfm` through PreForM.py, saves the results in `./preprocessed/`, then compiles everything together.
