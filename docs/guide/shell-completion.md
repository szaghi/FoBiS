# Shell Completion

FoBiS.py provides native tab completion for **bash**, **zsh**, **fish**, and **PowerShell**. Once installed, pressing <kbd>Tab</kbd> completes subcommands, option names, and many option *values*.

## Installing completion

Run the one-time installation command for your shell:

::: code-group

```bash [bash]
fobis --install-completion bash
# then reload your shell (or open a new terminal)
source ~/.bashrc
```

```bash [zsh]
fobis --install-completion zsh
source ~/.zshrc
```

```bash [fish]
fobis --install-completion fish
# fish picks up completions from ~/.config/fish/completions/ automatically
```

```powershell [PowerShell]
fobis --install-completion powershell
# follow any additional instructions printed by the command
```

:::

To preview the completion script without installing it:

```bash
fobis --show-completion bash    # or zsh / fish / powershell
```

## What gets completed

### Subcommands

```
fobis <Tab>
build    clean    rule    doctests    fetch    install
```

### Option names

All long option names complete after `--`:

```
fobis build --<Tab>
--compiler   --cflags   --lflags   --mode   --mklib   --src   ...
```

### Option values with smart completion

Several options offer *value* completion — the completions are filtered as you type:

| Option | Completions |
|---|---|
| `--compiler` | `gnu`, `intel`, `intel_nextgen`, `g95`, `opencoarrays-gnu`, `pgi`, `ibm`, `nag`, `nvfortran`, `amd`, `custom` |
| `--mklib` | `static`, `shared` |
| `--mode` | modes read **live** from the active fobos file |
| `--extensions` | all built-in Fortran file extensions |
| `--inc` | all built-in include file extensions |
| `--doctests-preprocessor` | `cpp`, `fpp` |

#### `--compiler` completion example

```
fobis build --compiler <Tab>
gnu   intel   intel_nextgen   g95   opencoarrays-gnu   pgi   ibm   nag   nvfortran   amd   custom

fobis build --compiler in<Tab>
intel   intel_nextgen
```

#### `--mode` live completion example

Given a fobos file with modes `debug`, `release`, and `coverage`:

```
fobis build --mode <Tab>
debug   release   coverage

fobis build --mode r<Tab>
release
```

The completion reads the fobos file named by `--fobos` (or the default `fobos` in the current directory) at completion time, so the list always reflects your actual project.

## Verifying completion is active

```bash
# Should show the completion function / script path
type _FoBiS_py_completion   # bash / zsh
```

If completion does not activate after reloading your shell, re-run the install command — it will show where the completion script was written.

## Uninstalling completion

The completion script is written to a shell-specific location. To remove it:

::: code-group

```bash [bash]
# The install command reports the path; typically:
rm ~/.bash_completions/FoBiS.py.sh
# and remove the source line from ~/.bashrc
```

```bash [zsh]
rm ~/.zfunc/_FoBiS.py
# and remove the fpath entry from ~/.zshrc if present
```

```bash [fish]
rm ~/.config/fish/completions/FoBiS.py.fish
```

:::

## Troubleshooting

**Completion not working after install**
- Make sure you sourced your shell config (`source ~/.bashrc`, etc.) or opened a new terminal.
- For zsh, ensure `autoload -Uz compinit && compinit` appears in `~/.zshrc` **after** the fpath entry added by FoBiS.py.

**`--mode` shows no completions**
- A `fobos` file must exist in the current directory, or you must pass `--fobos path/to/fobos` before `--mode` on the command line.

**No completions in a virtual environment**
- Completion is installed for the Python environment that is active when you run `--install-completion`. Activate the same environment before using FoBiS.py in your shell.
