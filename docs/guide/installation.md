# Installation

## Requirements

- **Python** 3.9 or later
- **A Fortran compiler** in `PATH` (e.g. `gfortran`, `ifort`, `ifx`)
- [**Typer**](https://typer.tiangolo.com/) — installed automatically as a dependency (provides the CLI and shell completion)
- Optional: [PreForM.py](https://github.com/szaghi/PreForM) for source preprocessing
- Optional: [FORD](https://github.com/Fortran-FOSS-Programmers/ford) for the `--ford` intrinsic rule
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
FoBiS.py --help
```

Enable shell tab completion (bash / zsh / fish / PowerShell):

```bash
FoBiS.py --install-completion bash   # or zsh / fish / powershell
```

See [Shell Completion](/guide/shell-completion) for the full setup guide.

::: tip Windows
On Windows the entry point is created as `FoBiS.py.exe` in the Python `Scripts` directory. Use PowerShell (the default shell) rather than Git Bash, or invoke via `fobis` (the lower-case console entry point that resolves correctly in all shells).
:::

## From source

```bash
git clone https://github.com/szaghi/FoBiS.git
cd FoBiS
pip install -e .
```

For development (editable install with all dev tools):

```bash
pip install -e ".[dev]"
```

## Programmatic use

FoBiS.py can be invoked from Python code without the CLI:

```python
from fobis.fobis import run_fobis

# Equivalent to: FoBiS.py build --mode release
run_fobis(fake_args=['build', '--mode', 'release'])
```

The `fake_args` list accepts any arguments that would appear on the command line (both `--option` and legacy `-option` single-dash forms are accepted).
