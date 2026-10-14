# PreForM Preprocessing

FoBiS.py integrates seamlessly with [PreForM.py](https://github.com/szaghi/PreForM), a powerful yet simple preprocessor designed for Fortran. PreForM.py provides template expansion and `cpp`-compatible preprocessing, making it easy to generate repetitive Fortran code.

## Basic usage

Activate preprocessing with `--preprocessor` (or the legacy `-pfm`/`--preform` alias):

```bash
fobis build --preprocessor
```

By default, `PreForM.py` is invoked as the preprocessor. Each source file is passed through PreForM.py before compilation. The intermediate preprocessed files are deleted immediately after compilation.

To use a different preprocessor, specify its command:

```bash
fobis build --preprocessor my_preprocessor
```

## Keeping preprocessed files

To retain the preprocessed sources (useful for debugging or distribution), specify an output directory with `--dpp`/`--preprocessor-dir`:

```bash
fobis build --preprocessor --dpp ./preprocessed/
```

The directory is relative to the build path, similar to `obj/` and `mod/`.

## Preprocessing only selected files

To preprocess only files with certain extensions (rather than all sources), use `--epp`/`--preprocessor-ext`:

```bash
fobis build --preprocessor --dpp ./preprocessed/ --epp .F90 --epp .F95 --epp .F03
```

Only files ending in `.F90`, `.F95`, or `.F03` are passed through PreForM.py; all other files are compiled directly.

## Preprocessor arguments

Pass extra flags to the preprocessor command with `--app`/`--preprocessor-args`:

```bash
fobis build --preprocessor --app "-DDEBUG=1"
```

Compiler-level preprocessor flags (e.g. `-DFEATURE`) go to `--preproc`:

```bash
fobis build --preprocessor --preproc "-DUSE_MPI"
```

To suppress the `-o` output flag in the preprocessor invocation:

```bash
fobis build --preprocessor --npp
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
| `--app`, `--preprocessor-args` | Flags passed to the preprocessor |
| `--npp`, `--preprocessor-no-o` | Omit `-o` from the preprocessor command |
| `--dpp`, `--preprocessor-dir` | Directory for preprocessed sources (kept if set) |
| `--epp`, `--preprocessor-ext` | Extensions of files to preprocess |

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
fobis build \
  --preprocessor \
  --dpp ./preprocessed/ \
  --epp .pfm \
  --cflags "-c -O2" \
  --src ./src/
```

FoBiS.py expands `vector.pfm` and `matrix.pfm` through PreForM.py, saves the results in `./preprocessed/`, then compiles everything together.

