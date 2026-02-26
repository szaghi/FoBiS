# PreForM Preprocessing

This example shows how to use [PreForM.py](https://github.com/szaghi/PreForM) with FoBiS.py to expand templates before compilation.

## Prerequisites

PreForM.py must be installed and available in `PATH`:

```bash
pip install PreForM.py
```

## Source layout

```
src/
├── main.f90
└── templates/
    ├── vector_real.pfm
    └── vector_int.pfm
```

Template files use `.pfm` (or `.F90`, `.F03`, etc.) as their extension. Regular Fortran sources use `.f90`.

## Example template

A simple PreForM.py template that generates typed vector operations:

```fortran
! vector_real.pfm
#:def VECTOR_TYPE(TYPENAME, KIND)
module vector_${TYPENAME}$
  implicit none
  type :: vector
    ${KIND}$, allocatable :: data(:)
  contains
    procedure :: norm
  end type
contains
  function norm(self) result(n)
    class(vector), intent(in) :: self
    ${KIND}$ :: n
    n = sqrt(sum(self%data**2))
  end function
end module vector_${TYPENAME}$
#:enddef
$:VECTOR_TYPE('real32', 'real(kind=4)')
```

## Building with preprocessing

```bash
# Preprocess all files, delete intermediates after compilation
FoBiS.py build -preprocessor

# Keep preprocessed sources in ./preprocessed/
FoBiS.py build -preprocessor -dpp ./preprocessed/

# Preprocess only .pfm files, pass the rest directly to the compiler
FoBiS.py build -preprocessor -dpp ./preprocessed/ -epp .pfm

# Pass extra flags to PreForM.py
FoBiS.py build -preprocessor -app "-DNDEBUG"
```

## fobos configuration

```ini
[modes]
modes = gnu

[gnu]
compiler         = gnu
cflags           = -c -O2
src              = ./src/
build_dir        = ./build/
obj_dir          = ./build/obj/
mod_dir          = ./build/mod/
target           = main.f90
output           = myapp
preprocessor     = PreForM.py
preprocessor_dir = ./build/preprocessed/
preprocessor_ext = .pfm .F90
```

```bash
FoBiS.py build -mode gnu
```

## What happens

1. FoBiS.py scans sources and builds the dependency graph.
2. For each `.pfm` (and `.F90`) file, `PreForM.py` is called first to expand templates.
3. The expanded source is saved to `./build/preprocessed/` (or discarded if `-dpp` is not set).
4. The expanded source is compiled by gfortran.

## Keeping preprocessed files for distribution

```ini
preprocessor_dir = ./dist/
preprocessor_ext = .pfm
```

After the build, `./dist/` contains standard Fortran `.f90` files ready to compile without PreForM.py — useful when distributing to users who don't have it installed.

## Combining with the fobos-examples pattern

```ini
[modes]
modes = gnu gnu-preform

[gnu]
compiler = gnu
cflags   = -c -O2
src      = ./src/
target   = main.f90
output   = myapp

[gnu-preform]
compiler         = gnu
cflags           = -c -O2
src              = ./src/
target           = main.f90
output           = myapp
preprocessor     = PreForM.py
preprocessor_ext = .pfm
```

```bash
# Build without preprocessing
FoBiS.py build -mode gnu

# Build with preprocessing
FoBiS.py build -mode gnu-preform
```

## Preprocessor option reference

| Option | Description |
|---|---|
| `-preprocessor [CMD]` | Enable preprocessing; optional custom command |
| `-dpp DIR`, `--preprocessor_dir` | Store preprocessed files in `DIR` |
| `-epp EXT…`, `--preprocessor_ext` | Only preprocess files with these extensions |
| `-app FLAGS`, `--preprocessor_args` | Extra flags for the preprocessor |
| `-p FLAGS`, `--preproc` | Preprocessor flags for the main compiler |
| `-npp`, `--preprocessor_no_o` | Omit `-o` from the preprocessor command |

See [PreForM Preprocessing](/advanced/preform) for the full guide.
