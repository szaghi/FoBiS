# Installation

## Requirements

- **Python** 3.10 or later
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
fobis -v
fobis --help
```

Enable shell tab completion (bash / zsh / fish / PowerShell):

```bash
fobis --install-completion bash   # or zsh / fish / powershell
```

See [Shell Completion](/guide/shell-completion) for the full setup guide.

::: tip Windows
On Windows the entry point is created as `FoBiS.py.exe` in the Python `Scripts` directory. Use PowerShell (the default shell) rather than Git Bash, or invoke via `fobis` (the lower-case console entry point that resolves correctly in all shells).
:::

::: tip Legacy command name
The `FoBiS.py` command is preserved as a backward-compatible alias. Both `fobis` and `FoBiS.py` invoke the same tool — existing scripts using `FoBiS.py` continue to work without changes.
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

## Standalone offline (air-gapped HPC)

On clusters with no internet access — no `pip`, no `pipx`, no PyPI — where the only way in is to `scp` a file, use the standalone **zipapp** distribution. It bundles FoBiS together with its full Python runtime dependency closure (Typer and friends) into a single self-contained `fobis.pyz`.

Build the archive on a machine that *does* have network access:

```bash
git clone https://github.com/szaghi/FoBiS.git
cd FoBiS
make standalone        # produces dist/fobis.pyz
```

Copy it to the cluster and run it directly with the cluster's Python:

```bash
scp dist/fobis.pyz user@cluster:~/bin/
ssh user@cluster
python3 ~/bin/fobis.pyz build      # or any other subcommand
```

The archive carries a shebang, so you can also make it directly executable:

```bash
chmod +x ~/bin/fobis.pyz
~/bin/fobis.pyz --help
```

Each tagged release also publishes `fobis.pyz` as a [GitHub Release](https://github.com/szaghi/FoBiS/releases) asset, so you can download a prebuilt archive instead of building it yourself.

::: tip Requirements on the target cluster
The `.pyz` ships pure-Python source, so it is OS- and architecture-independent and runs on any **Python 3.10 or later**. It does **not** bundle a Fortran compiler — the cluster must still provide one (`gfortran`, `ifx`, …) on `PATH`, since FoBiS shells out to it.
:::

## Programmatic use

FoBiS.py can be invoked from Python code without the CLI:

```python
from fobis.fobis import run_fobis

# Equivalent to: fobis build --mode release
run_fobis(fake_args=['build', '--mode', 'release'])
```

The `fake_args` list accepts any arguments that would appear on the command line (both `--option` and legacy `-option` single-dash forms are accepted).
