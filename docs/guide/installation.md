# Installation

## Requirements

- **Python** 3.9 or later
- **A Fortran compiler** in `PATH` (e.g. `gfortran`, `ifort`, `ifx`)
- Optional: [PreForM.py](https://github.com/szaghi/PreForM) for source preprocessing
- Optional: [FORD](https://github.com/Fortran-FOSS-Programmers/ford) for the `-ford` intrinsic rule
- Optional: [graphviz](https://graphviz.org/) Python package for dependency graph generation

## From PyPI (recommended)

```bash
pip install FoBiS.py
```

Or with `pipx` for an isolated installation:

```bash
pipx install FoBiS.py
```

Verify the installation:

```bash
FoBiS.py -v
FoBiS.py -h
```

::: tip Windows
On Windows the entry point is created as `FoBiS.py.exe` in the Python `Scripts` directory. Use PowerShell (the default shell) rather than Git Bash, or invoke via `fobis` (the lower-case console entry point that resolves correctly in all shells).
:::

## From source

```bash
git clone https://github.com/szaghi/FoBiS.git
cd FoBiS
pip install -e .
```

### Build from source with pybuilder

```bash
pip install pybuilder
pyb
cd release/FoBiS-<branch>/
pip install -e .
```

## Programmatic use

FoBiS.py can be invoked from Python code without the CLI:

```python
from fobis.fobis import run_fobis

# Equivalent to: FoBiS.py build -mode release
run_fobis(fake_args=['build', '-mode', 'release'])
```

The `fake_args` list accepts any arguments that would appear on the command line.
